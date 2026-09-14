"""Where a notice actually went, as opposed to where it was aimed.

SES is in sandbox on this account, so a message addressed to a household is
only accepted if that address is a verified identity or sits under a verified
domain. Everything else is routed to the mailbox simulator and the household is
NOT reached.

The tests that matter here are the ones that check the record says so. A
delivery record that reads as success when a family was never contacted is
worse than a failure, because a pantry will file it and stop worrying.
"""

from __future__ import annotations

import pytest

from agent.dispatch import SIMULATOR, _deliverable, notify_all, send_notice


def test_a_verified_address_is_deliverable():
    assert _deliverable("someone@getava.xyz", {"getava.xyz"}) is True


def test_a_verified_domain_covers_every_address_under_it():
    """SES sandbox accepts any recipient at a verified domain identity."""
    assert _deliverable("h0166@getava.xyz", {"getava.xyz"}) is True
    assert _deliverable("H0166@GetAva.XYZ", {"getava.xyz"}) is True


def test_an_unverified_address_is_not_deliverable():
    assert _deliverable("stranger@example.com", {"getava.xyz"}) is False


def test_a_similar_domain_does_not_count_as_verified():
    """notgetava.xyz must not pass because getava.xyz is verified."""
    assert _deliverable("a@notgetava.xyz", {"getava.xyz"}) is False
    assert _deliverable("a@getava.xyz.evil.com", {"getava.xyz"}) is False


def test_a_household_with_no_email_is_a_recorded_failure_not_a_silent_skip(monkeypatch):
    """A family the pantry cannot reach is the single most important record."""
    record = send_notice(
        to=None, subject="s", body="b", household_id="H-0001", case_id="c1"
    )
    assert record["mode"] == "failed"
    assert record["to"] is None
    assert record["household_id"] == "H-0001"
    assert "no usable email" in record["error"]


def test_a_malformed_address_is_a_recorded_failure():
    record = send_notice(
        to="not-an-address", subject="s", body="b", household_id="H-0002", case_id="c1"
    )
    assert record["mode"] == "failed"
    assert "no usable email" in record["error"]


def test_the_notice_is_personalised_per_household(monkeypatch):
    """{household} and {units} are the only substitutions, and both must happen."""
    seen: list[tuple[str, str]] = []

    def fake_send(*, to, subject, body, household_id, case_id):
        seen.append((household_id, body))
        return {"household_id": household_id, "mode": "simulator", "to": SIMULATOR}

    monkeypatch.setattr("agent.dispatch.send_notice", fake_send)

    case = {
        "case_id": "c1",
        "pantry_name": "Riverbend Community Pantry",
        "recall": {"recall_number": "F-0617-2025"},
        "notify": {
            "recipients": [
                {"household_id": "H-0166", "name": "Farhat household", "units": 10, "contact_email": "a@getava.xyz"},
                {"household_id": "H-0214", "name": "Kimathi household", "units": 9, "contact_email": "b@getava.xyz"},
            ]
        },
    }
    notify_all(case, "We gave {household} {units} cans. Recall F-0617-2025.")

    assert seen[0][1] == "We gave Farhat household 10 cans. Recall F-0617-2025."
    assert seen[1][1] == "We gave Kimathi household 9 cans. Recall F-0617-2025."
    assert not any("{household}" in body for _, body in seen)
    assert not any("{units}" in body for _, body in seen)


def test_the_delivery_record_counts_each_mode_separately(monkeypatch):
    """Partial delivery is the normal outcome and must not read as success."""
    modes = iter(["direct", "simulator", "failed"])

    def fake_send(*, to, subject, body, household_id, case_id):
        return {"household_id": household_id, "mode": next(modes), "to": to}

    monkeypatch.setattr("agent.dispatch.send_notice", fake_send)

    case = {
        "case_id": "c1",
        "pantry_name": "P",
        "recall": {"recall_number": "F-0617-2025"},
        "notify": {
            "recipients": [
                {"household_id": f"H-000{i}", "name": "n", "units": 1, "contact_email": "x@y.z"}
                for i in range(3)
            ]
        },
    }
    delivery = notify_all(case, "Recall F-0617-2025.")
    assert delivery["attempted"] == 3
    assert delivery["direct"] == 1
    assert delivery["simulator"] == 1
    assert delivery["failed"] == 1
    assert len(delivery["messages"]) == 3


@pytest.mark.live
def test_ses_really_accepts_a_notice_for_a_verified_domain():
    """The real send. Returns a real MessageId or this path does not work."""
    record = send_notice(
        to="h0166@getava.xyz",
        subject="Best By dispatch path check",
        body="Verifying the SES path.",
        household_id="H-0166",
        case_id="verify",
    )
    assert record["mode"] == "direct", record
    assert record["to"] == "h0166@getava.xyz"
    assert record["message_id"]


@pytest.mark.live
def test_an_unverified_recipient_really_routes_to_the_simulator():
    """The branch the live pantry data has never produced, exercised for real.

    Every household on the real roster is at getava.xyz, a verified domain, so
    every send this project has made so far came back `direct`. That left the
    `simulator` path asserted only by the unit test above, which fakes SES.

    This sends to an address SES sandbox will not accept for delivery and
    checks the three things that have to be true at once: the notice really
    went (a message id exists), it went to the simulator rather than the
    household, and the record says so by keeping `intended` distinct from `to`.
    A pantry reading this case later must be able to tell that this family was
    not reached.
    """
    record = send_notice(
        to="nobody@example.invalid",
        subject="Best By simulator route check",
        body="Verifying that an unreachable household routes to the simulator.",
        household_id="H-TEST",
        case_id="verify-simulator",
    )
    assert record["mode"] == "simulator", record
    assert record["to"] == SIMULATOR
    assert record["intended"] == "nobody@example.invalid"
    assert record["intended"] != record["to"], "the record must not claim the household was reached"
    assert record["message_id"]
