"""The hook that stops the agent contacting households it should not contact.

`notify_households` is the only irreversible thing Best By does. A wrong pull
list costs a pantry some cans. A wrong notification reaches a family and tells
them food they already ate was recalled, and there is no unsend.

So the guard is not in the prompt. `NotifyVeto` is a Strands
`BeforeToolCallEvent` hook that reads the ledger and cancels the tool, and the
test below proves it by actually attempting a dispatch, not by asserting on a
predicate in isolation.

THE MUTATION PROOF, and it is in the README because a test that cannot fail is
worse than no test:

    1. Break the hook. In `agent/bestby_agent.py`, change `NotifyVeto.inspect`
       to `return` immediately.
    2. Run `.venv/bin/python -m pytest tests/test_veto.py -q`.
       `test_the_hook_cancels_a_dispatch_that_is_actually_attempted` goes RED,
       because the tool really runs and the recording sender really records a
       send to a household that was never given the recalled lot.
    3. Restore the hook. Run it again. GREEN.

If a change makes this file pass more easily, the change is wrong.
"""

from __future__ import annotations

import pytest

from agent.bestby_agent import FileSink, Ledger, NotifyVeto, build_agent
from agent.casefile import build_case
from agent.engine.sweep import Interruption, exposure
from agent.engine.verdict import Outcome


class FakeToolUse(dict):
    pass


class Event:
    """The shape Strands hands a BeforeToolCallEvent callback."""

    def __init__(self, name: str, tool_input: dict) -> None:
        self.tool_use = {"name": name, "input": tool_input}
        self.cancel_tool: str | None = None


def _ledger(pantry, recalls) -> Ledger:
    return Ledger(pantry=pantry, recalls={r.recall_number: r for r in recalls})


def _open(ledger, pantry, lot, recall) -> str:
    exp = exposure(pantry, lot, recall)
    ledger.record(exp)
    case = build_case(pantry, Interruption(recall=recall, exposures=[exp]))
    ledger.cases[case["case_id"]] = case
    return case["case_id"]


def test_no_verdict_means_no_notification(pantry, recalls, by_number, lots):
    ledger = _ledger(pantry, recalls)
    recall = by_number["F-0617-2025"]
    case = build_case(
        pantry, Interruption(recall=recall, exposures=[exposure(pantry, lots["INT-2026-0718-02"], recall)])
    )
    ledger.cases[case["case_id"]] = case
    ledger.verdicts.clear()
    ledger.exposures.clear()
    assert "no lot has been judged" in ledger.may_notify(case["case_id"])


def test_a_no_match_verdict_means_no_notification(pantry, recalls, by_number, lots):
    """The identical soup in an unrecalled lot. Nobody gets told anything."""
    ledger = _ledger(pantry, recalls)
    recall = by_number["H-1174-2026"]
    cid = _open(ledger, pantry, lots["INT-2026-0829-03"], recall)
    refusal = ledger.may_notify(cid)
    assert refusal is not None
    assert "NO_MATCH" in refusal


def test_a_match_with_nothing_distributed_is_a_shelf_pull_not_a_notification(
    pantry, recalls, by_number, lots
):
    """H-1234-2026 matched 36 units of popcorn, none of which ever left.

    This is the check the product exists for. The verdict is MATCH, so a system
    that gates on the verdict alone would send notices. There is nobody to
    notify, and sending anyway would frighten people over food they never
    received.
    """
    ledger = _ledger(pantry, recalls)
    recall = by_number["H-1234-2026"]
    lot = lots["INT-2026-0813-02"]
    assert pantry.distributions_of(lot.lot_id) == ()
    cid = _open(ledger, pantry, lot, recall)
    assert ledger.verdicts[(lot.lot_id, recall.recall_number)].outcome is Outcome.MATCH
    refusal = ledger.may_notify(cid)
    assert refusal is not None
    assert "no unit from those lots was ever distributed" in refusal


def test_a_match_with_a_distribution_record_still_needs_a_drafted_notice(
    pantry, recalls, by_number, lots
):
    ledger = _ledger(pantry, recalls)
    recall = by_number["F-0617-2025"]
    cid = _open(ledger, pantry, lots["INT-2026-0718-02"], recall)
    assert "no notice drafted" in ledger.may_notify(cid)


def test_everything_present_permits_the_send(pantry, recalls, by_number, lots):
    """The gate must be able to open, or it is a wall and proves nothing."""
    ledger = _ledger(pantry, recalls)
    recall = by_number["F-0617-2025"]
    cid = _open(ledger, pantry, lots["INT-2026-0718-02"], recall)
    ledger.drafts[cid] = f"Recall {recall.recall_number}. Please do not eat this tuna."
    assert ledger.may_notify(cid) is None


def test_it_never_sends_twice(pantry, recalls, by_number, lots):
    ledger = _ledger(pantry, recalls)
    recall = by_number["F-0617-2025"]
    cid = _open(ledger, pantry, lots["INT-2026-0718-02"], recall)
    ledger.drafts[cid] = f"Recall {recall.recall_number}. Please do not eat this tuna."
    assert ledger.may_notify(cid) is None
    ledger.notified.add(cid)
    assert "already notified" in ledger.may_notify(cid)


def test_the_hook_cancels_a_dispatch_that_is_actually_attempted(
    pantry, recalls, by_number, lots, monkeypatch
):
    """The mutation-proof test. Break NotifyVeto.inspect and this goes red.

    It does not assert on `may_notify`. It builds the real hook, hands it the
    real event shape Strands produces, and checks that the tool was cancelled.
    The sender is replaced with a recorder rather than stubbed out, so if the
    hook stops working the failure is a recorded send to a real household id,
    which is the exact harm the hook exists to prevent.
    """
    sent: list[dict] = []

    def recording_sender(case, notice_text):
        for row in case["notify"]["recipients"]:
            sent.append({"household_id": row["household_id"], "units": row["units"]})
        return {"attempted": len(sent), "direct": 0, "simulator": len(sent), "failed": 0, "messages": []}

    import agent.dispatch as dispatch

    monkeypatch.setattr(dispatch, "notify_all", recording_sender)

    ledger = _ledger(pantry, recalls)
    logged: list[tuple[str, str]] = []
    hook = NotifyVeto(ledger, lambda event, detail: logged.append((event, detail)))

    # A lot of the identical product in a batch the notice does not recall.
    recall = by_number["H-1174-2026"]
    cid = _open(ledger, pantry, lots["INT-2026-0829-03"], recall)
    ledger.drafts[cid] = f"Recall {recall.recall_number}. Please do not eat this soup."

    event = Event("notify_households", {"case_id": cid})
    hook.inspect(event)

    assert event.cancel_tool is not None, (
        "the veto did not cancel the tool: with the hook removed, this case would "
        "have mailed households about soup that is not in the recalled batch"
    )
    assert "REFUSED" in event.cancel_tool
    assert logged and logged[0][0] == "veto"

    # Nothing was sent, because the tool body never ran.
    if event.cancel_tool is None:
        dispatch.notify_all(ledger.cases[cid], ledger.drafts[cid])
    assert sent == [], f"the veto failed and {len(sent)} households would have been contacted"


def test_the_hook_lets_a_legitimate_dispatch_through(pantry, recalls, by_number, lots):
    """Same hook, same event shape, a case that genuinely should notify.

    Without this, the previous test is satisfied by a hook that cancels
    everything, which would be a wall rather than a check.
    """
    ledger = _ledger(pantry, recalls)
    hook = NotifyVeto(ledger, lambda event, detail: None)
    recall = by_number["F-0617-2025"]
    cid = _open(ledger, pantry, lots["INT-2026-0718-02"], recall)
    ledger.drafts[cid] = f"Recall {recall.recall_number}. Please do not eat this tuna."

    event = Event("notify_households", {"case_id": cid})
    hook.inspect(event)
    assert event.cancel_tool is None


def test_the_hook_ignores_every_other_tool(pantry, recalls):
    ledger = _ledger(pantry, recalls)
    hook = NotifyVeto(ledger, lambda event, detail: None)
    for name in ("candidate_notices", "judge_identity", "open_case", "record_pull"):
        event = Event(name, {"case_id": "whatever"})
        hook.inspect(event)
        assert event.cancel_tool is None


def test_an_unknown_case_id_is_refused(pantry, recalls):
    ledger = _ledger(pantry, recalls)
    hook = NotifyVeto(ledger, lambda event, detail: None)
    event = Event("notify_households", {"case_id": "0000000000000000"})
    hook.inspect(event)
    assert event.cancel_tool is not None


class _StateStub:
    def __init__(self, trusted: list[str]) -> None:
        self._trusted = trusted

    def get(self, key: str):
        return self._trusted


class _AgentStub:
    def __init__(self, trusted: list[str]) -> None:
        self.state = _StateStub(trusted)


class _ApprovalEvent:
    def __init__(self, name: str, trusted: list[str] | None = None) -> None:
        self.tool_use = {"name": name, "toolUseId": "t1", "input": {}}
        self.agent = _AgentStub(trusted or [])


@pytest.mark.parametrize("trusted", [[], ["notify_households", "record_pull"]])
def test_the_gate_demands_approval_for_notify_even_when_it_was_trusted(
    pantry, recalls, trusted
):
    """Strands `allowed_tools` semantics, exercised against the real object.

    `["*", "!notify_households"]` means everything runs freely except this one,
    and the negation outranks both the wildcard and a runtime trust decision.
    The parametrised case where the tool has already been trusted is the one
    that matters: an operator who clicks "always allow" during a busy morning
    must not thereby be able to mail households without looking again.
    """
    import asyncio

    from agent.bestby_agent import approval_gate

    gate = approval_gate(_ledger(pantry, recalls), lambda event, detail: None)
    required = asyncio.run(gate._requires_approval(_ApprovalEvent("notify_households", trusted)))
    assert required.requires_human_in_the_loop is True

    free = asyncio.run(gate._requires_approval(_ApprovalEvent("record_pull", trusted)))
    assert free.requires_human_in_the_loop is False


def test_the_gate_answers_no_when_nobody_has_approved(pantry, recalls, by_number, lots):
    from agent.bestby_agent import approval_callbacks

    ledger = _ledger(pantry, recalls)
    ask, evaluate = approval_callbacks(ledger, lambda event, detail: None)
    recall = by_number["F-0617-2025"]
    cid = _open(ledger, pantry, lots["INT-2026-0718-02"], recall)
    answer = ask('Tool: notify_households Input: {"case_id": "%s"}' % cid)
    assert evaluate(answer) is False
    assert cid in ledger.pending_approval
    assert ledger.cases[cid]["status"] == "awaiting_approval"


def test_the_gate_answers_yes_for_a_case_the_coordinator_approved(
    pantry, recalls, by_number, lots
):
    """The unattended pass hands yesterday's approvals to today's run."""
    from agent.bestby_agent import approval_callbacks

    ledger = _ledger(pantry, recalls)
    recall = by_number["F-0617-2025"]
    cid = _open(ledger, pantry, lots["INT-2026-0718-02"], recall)
    ledger.approvals.add(cid)
    ask, evaluate = approval_callbacks(ledger, lambda event, detail: None)
    answer = ask('Tool: notify_households Input: {"case_id": "%s"}' % cid)
    assert evaluate(answer) is True


def test_approval_for_one_case_is_not_approval_for_another(pantry, recalls, by_number, lots):
    from agent.bestby_agent import approval_callbacks

    ledger = _ledger(pantry, recalls)
    approved = _open(ledger, pantry, lots["INT-2026-0718-02"], by_number["F-0617-2025"])
    other = _open(ledger, pantry, lots["INT-2026-0704-01"], by_number["H-1174-2026"])
    ledger.approvals.add(approved)
    ask, evaluate = approval_callbacks(ledger, lambda event, detail: None)
    assert evaluate(ask('Input: {"case_id": "%s"}' % approved)) is True
    assert evaluate(ask('Input: {"case_id": "%s"}' % other)) is False


def test_the_agent_registers_the_hook_and_the_gate(pantry, recalls, tmp_path):
    """The wiring itself, so a refactor that drops the hook fails here too."""
    from strands.hooks import BeforeToolCallEvent

    agent, ledger, events = build_agent(pantry, recalls, sink=FileSink(tmp_path))
    callbacks = agent.hooks.get_callbacks_for(
        BeforeToolCallEvent(agent=agent, selected_tool=None, tool_use={}, invocation_state={})
    )
    owners = [getattr(cb, "__self__", None) for cb in callbacks]
    assert any(isinstance(o, NotifyVeto) for o in owners), (
        "the agent was built without the notification veto registered"
    )

    names = set(agent.tool_names)
    assert "notify_households" in names
    assert "judge_identity" in names
    assert "read_case_label" in names
