"""A case that already notified households must never come back undecided.

The scheduled pass rebuilds every case from the feed each morning, with a fresh
status of awaiting_approval. Before this, that fresh status overwrote the stored
one, so a case that had already notified fourteen households reappeared in the
coordinator's decision queue holding its real SES message ids. Approving it a
second time would have sent every one of those households a second notice.

It happened in production on case 73a4bb419a7da04b, which is why the test exists.
Nothing here touches AWS: put_case's merge is the unit under test, so the store
is exercised against a stand-in table that records what it was handed.
"""

from __future__ import annotations

import pytest

from agent.store import _TERMINAL_STATUSES, CaseStore, merge_timeline


class Table:
    """Stands in for the DynamoDB table, and only for the merge's sake.

    This is not a mock of the product: put_case's decision about which fields
    survive a rerun is pure, and this makes that decision observable without a
    network round trip. Every other store test runs against the real table.
    """

    def __init__(self, stored: dict | None = None) -> None:
        self.stored = stored
        self.written: dict | None = None

    def get_item(self, Key):  # noqa: N803, matches boto3
        return {"Item": self.stored} if self.stored else {}

    def put_item(self, Item):  # noqa: N803
        self.written = Item


def store_with(previous: dict | None) -> CaseStore:
    store = CaseStore.__new__(CaseStore)
    store.table = Table(previous)
    return store


def fresh_pass_case(status: str = "awaiting_approval") -> dict:
    return {
        "pantry_id": "riverbend-dayton",
        "case_id": "73a4bb419a7da04b",
        "status": status,
        "created_at": "2026-09-14T12:00:00+00:00",
        "timeline": [{"at": "2026-09-14T12:00:00+00:00", "event": "opened", "detail": "swept"}],
    }


@pytest.mark.parametrize("terminal", sorted(_TERMINAL_STATUSES))
def test_a_rerun_cannot_put_finished_work_back_in_the_queue(terminal):
    previous = fresh_pass_case(terminal) | {
        "created_at": "2026-09-01T00:00:00+00:00",
        "delivery": {"households": 14, "message_id": "010001a0-real"},
    }
    merged = store_with(previous).put_case(fresh_pass_case("awaiting_approval"))

    assert merged["status"] == terminal, "a finished case was reopened for approval"
    assert merged["delivery"]["message_id"] == "010001a0-real", "the proof of sending was lost"
    assert merged["created_at"] == "2026-09-01T00:00:00+00:00"


def test_a_case_still_being_worked_is_allowed_to_change():
    """The guard must not freeze everything, only what is finished."""
    previous = fresh_pass_case("needs_evidence")
    merged = store_with(previous).put_case(fresh_pass_case("awaiting_approval"))
    assert merged["status"] == "awaiting_approval"


def test_the_timeline_grows_by_union_rather_than_by_concatenation():
    entry = {"at": "2026-09-14T12:00:00+00:00", "event": "opened", "detail": "swept"}
    assert merge_timeline([entry], [entry]) == [entry]
