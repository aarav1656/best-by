"""The Best By agent.

What the model is for: reading. An FDA enforcement report is a paragraph a
regulatory affairs person typed, half product description and half microwave
instructions. An intake line is whatever a volunteer wrote on a clipboard.
Deciding those describe the same food is reading comprehension, and it is the
one judgment in this system a person does better than a token count.

What the model is not for: deciding. Whether a case on the shelf is inside the
recalled batch is string and date comparison against the stamped code, and it
happens in `agent/engine/verdict.py`, where no prompt reaches it.

That seam is enforced three times, deliberately:

  1. `judge_identity` accepts the model's read and returns the verdict computed
     from it. The model learns the outcome; it never chooses one.
  2. `NotifyVeto`, a `BeforeToolCallEvent` hook, cancels `notify_households`
     unless the ledger holds a MATCH verdict, a distribution record proving
     those units actually went home with someone, and a drafted notice.
  3. `approval_gate`, a Strands `HumanInTheLoop` intervention with
     `allowed_tools=["*", "!notify_households"]`, means the coordinator
     approves before any household is contacted, even in a session where
     everything else has been trusted.

Delete the hook and Best By becomes a program that emails families about food
they may never have received. `tests/test_veto.py` is the test that proves it,
and the mutation proof in the README breaks the hook on purpose to show the
test going red.

Why the model earns its place, measured rather than asserted: run the
deterministic pass alone over the real pantry against the live feed and it
raises 10 interruptions. Four of them are the same recall of Ritz peanut butter
cracker sandwiches matched against two jars of peanut butter, because
"peanut" and "butter" are 40% of a short intake line. The model reads those and
says no, and the queue the coordinator actually sees is the six real ones. A
pantry that is interrupted four times a week for nothing stops reading the
interruptions, which is precisely the failure the paper process already has.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry
from strands.models.anthropic import AnthropicModel
from strands.vended_interventions import HumanInTheLoop

from agent.casefile import build_case
from agent.engine.sweep import Exposure, Interruption, candidates, exposure
from agent.engine.verdict import IdentityAssertion, Outcome, Verdict
from agent.feeds.base import Recall
from agent.shelf import Pantry, ShelfLot
from agent.store import case_id as make_case_id

MODEL_ID = os.environ.get("BESTBY_MODEL", "claude-sonnet-4-5-20250929")
DATA = Path(__file__).parent.parent / "data"
# The most lookalike notices any single lot in the real pantry draws is 20
# (measured: peanut butter, against the whole peanut allergen cluster). The cap
# exists so one pathological lot cannot spend a whole context window, not to
# trim the list to a comfortable size.
_MAX_CANDIDATES = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Ledger:
    """What this pass has established. The only thing the veto trusts."""

    pantry: Pantry
    recalls: dict[str, Recall]
    verdicts: dict[tuple[str, str], Verdict] = field(default_factory=dict)
    exposures: dict[tuple[str, str], Exposure] = field(default_factory=dict)
    cases: dict[str, dict] = field(default_factory=dict)
    drafts: dict[str, str] = field(default_factory=dict)
    notified: set[str] = field(default_factory=set)
    approvals: set[str] = field(default_factory=set)
    pending_approval: set[str] = field(default_factory=set)
    considered: int = 0

    def record(self, exp: Exposure) -> None:
        key = (exp.lot.lot_id, exp.recall.recall_number)
        self.verdicts[key] = exp.verdict
        self.exposures[key] = exp

    def matched_for(self, recall_number: str) -> list[Exposure]:
        return [
            e
            for (_, number), e in self.exposures.items()
            if number == recall_number and e.verdict.outcome is Outcome.MATCH
        ]

    def may_notify(self, case_id: str) -> str | None:
        """The reason contacting households is refused, or None to proceed.

        Four conditions, and every one of them is a way a real pantry gets this
        wrong. No verdict: nobody checked. Not a MATCH: the engine looked and
        said this is not the recalled batch. No distribution record: the units
        are on the shelf, so there is nobody to tell and a notice would frighten
        people over food they never received. No draft: there is no message to
        send, and "we sent something" is not a record.
        """
        case = self.cases.get(case_id)
        if case is None:
            return f"no case {case_id} has been opened"

        number = case["recall"]["recall_number"]
        matched = self.matched_for(number)
        if not matched:
            checked = [
                v for (_, n), v in self.verdicts.items() if n == number
            ]
            if not checked:
                return (
                    f"no lot has been judged against {number} yet, so there is no "
                    "verdict to notify on"
                )
            outcomes = ", ".join(sorted({v.outcome.value for v in checked}))
            return (
                f"no lot matched {number}. The engine returned {outcomes} for the "
                f"{len(checked)} lot(s) it checked. Households are only contacted "
                "about a confirmed lot match."
            )

        with_distribution = [e for e in matched if e.distributions]
        if not with_distribution:
            units = sum(e.units_on_hand for e in matched)
            return (
                f"{number} matched {len(matched)} lot(s) holding {units} units, but no "
                "unit from those lots was ever distributed to a household. There is "
                "nobody to notify; this case is a shelf pull only."
            )

        if not self.drafts.get(case_id):
            return f"case {case_id} has no notice drafted yet"

        if case_id in self.notified:
            return f"case {case_id} has already notified its households; it will not send twice"

        return None


class NotifyVeto(HookProvider):
    """The check that cannot be argued with, because it is not in the prompt."""

    def __init__(self, ledger: Ledger, log: Callable[[str, str], None]) -> None:
        self.ledger = ledger
        self.log = log

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.inspect)

    def inspect(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use.get("name") != "notify_households":
            return
        cid = (event.tool_use.get("input") or {}).get("case_id", "")
        refusal = self.ledger.may_notify(cid)
        if refusal:
            self.log("veto", refusal)
            event.cancel_tool = f"REFUSED by the notification veto: {refusal}"


def approval_callbacks(
    ledger: Ledger, log: Callable[[str, str], None]
) -> tuple[Callable[..., str], Callable[..., bool]]:
    """The ask and evaluate behaviour, separated from the Strands wrapper.

    Strands keeps these private on the `HumanInTheLoop` instance, and a gate
    whose behaviour can only be exercised by running a live model is a gate
    nobody tests. Pulled out here so `tests/test_veto.py` can call them.
    """

    def ask(prompt: str, **_: Any) -> str:
        try:
            payload = json.loads(prompt.split("Input: ", 1)[1])
            cid = payload.get("case_id", "")
        except (IndexError, ValueError):
            cid = ""
        if cid and cid in ledger.approvals:
            log("approved", f"{cid} was approved by the coordinator")
            return "yes"
        ledger.pending_approval.add(cid)
        case = ledger.cases.get(cid)
        if case is not None:
            case["status"] = "awaiting_approval"
            case["timeline"].append(
                {
                    "at": _now(),
                    "event": "approval_requested",
                    "detail": (
                        f"The notice is drafted for "
                        f"{case.get('notify', {}).get('households', 0)} household(s) "
                        "and is waiting for the coordinator."
                    ),
                }
            )
        log("awaiting_approval", f"{cid} is drafted and waiting for a person")
        return "no"

    def evaluate(response: Any, **_: Any) -> bool:
        return str(response).strip().lower() in {"y", "yes", "approve", "approved"}

    return ask, evaluate


def approval_gate(ledger: Ledger, log: Callable[[str, str], None]) -> HumanInTheLoop:
    """The one call a person has to make.

    Everything else this agent does is reversible. Reading notices, computing a
    verdict, opening a case, drafting a notice, even writing the compliance
    record: all of it can be corrected by the next pass. Telling a family their
    groceries were recalled cannot. So it is the single tool that can never be
    trusted away, and `allowed_tools` is a wildcard with `notify_households`
    negated, which in Strands means it requires approval even in a session where
    the caller has trusted everything else.

    In the scheduled run nobody is at a terminal, so the gate does not block the
    pass. It marks the case as waiting for the coordinator and moves on to the
    next notice. The console is where the answer comes back: an approved case id
    is handed to the next run and the same gate lets it through.

    The veto still runs underneath. Approval is permission to send a notice that
    already passed every check. It is not permission to skip them.
    """
    ask, evaluate = approval_callbacks(ledger, log)
    return HumanInTheLoop(allowed_tools=["*", "!notify_households"], ask=ask, evaluate=evaluate)


class CaseSink:
    """Where cases go when the pass ends. Both implementations are real.

    `read` matters as much as `write`. A pass that only wrote would overwrite
    what the previous pass learned, and the most expensive thing to forget is
    that households have already been contacted: the durable guard against
    notifying the same family twice is the delivery record on the stored case,
    not anything held in memory for one run.
    """

    def write(self, case: dict) -> str:
        raise NotImplementedError

    def read(self, pantry_id: str, case_id: str) -> dict | None:
        return None


class FileSink(CaseSink):
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or DATA / "cases"
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, case: dict) -> str:
        path = self.root / f"{case['case_id']}.json"
        path.write_text(json.dumps(case, indent=2, default=str))
        return str(path)

    def read(self, pantry_id: str, case_id: str) -> dict | None:
        path = self.root / f"{case_id}.json"
        return json.loads(path.read_text()) if path.exists() else None


class DynamoSink(CaseSink):
    def __init__(self) -> None:
        from agent.store import CaseStore

        self.store = CaseStore()

    def write(self, case: dict) -> str:
        self.store.put_case(case)
        return f"dynamodb://bestby-cases/{case['pantry_id']}/{case['case_id']}"

    def read(self, pantry_id: str, case_id: str) -> dict | None:
        return self.store.get_case(pantry_id, case_id)


SYSTEM_PROMPT = """You work for one food pantry. Every morning you check what is on its shelves, and what it has already given away, against every open FDA food recall. Almost every morning the answer is nothing, and saying nothing is the correct output.

You are reading a regulator's prose against a volunteer's intake line. That comparison is your job and you are good at it: "Amy's Organic Soups Lentil Light in Sodium, 14.5 oz can" and "Amy's ORGANIC SOUPS LENTIL LIGHT IN SODIUM NET WT. 14.5 OZ. (411 g) Microwave: Place soup in a microwave-safe bowl" are the same can, even though half the notice is cooking instructions. Equally: "Ritz Peanut Butter Cracker Sandwiches" and "Jif Creamy Peanut Butter, 16 oz jar" share the words peanut and butter and are not remotely the same food. Say so.

What is not your job: deciding whether a lot is in the recalled batch. Stamped lot codes, printed best-by dates and barcodes are compared outside you, and you will be told the result. If you are told NO_MATCH, that is the answer. Do not argue, do not retry with different wording, do not notify anyone anyway. Recalled food left on a shelf and safe food thrown away are both failures, and both of them start with someone deciding the codes did not matter.

Work one shelf lot at a time:

1. Call candidate_notices for the lot.
2. For each candidate worth considering, call judge_identity with your honest read: is this the same food, how confident, and why. Cite the specific wording that convinced you. If the notice is about a different product, say same_product=false and move on. This is where most of your value is.
3. judge_identity returns the computed verdict.

   On MATCH: call open_case for that recall number. The case tells you two separate numbers, and they are different obligations. Units still on the shelf are a pull: a volunteer walks to a named bay and takes cases off. Units already distributed are households who have the food at home, and the only thing that helps them is being told. Handle both, and never let the pull list stand in for the notification.

   If the case has households to notify, call draft_notice, then notify_households.

   notify_households is the one thing you cannot do alone. Telling a family their groceries were recalled cannot be taken back, so it waits for the coordinator to approve it. When the answer comes back "waiting for a person", that is the system working. Say so once and move to the next lot. Do not retry it, do not reword the notice to get a different answer, and never tell the coordinator that households were notified when they were not.

   Then call record_pull for the shelf units and file_compliance_record for the case.

   On NEEDS_EVIDENCE: the notice is about this product and it reached this state, but nothing on the intake record says which batch this lot is. Call open_case, then request_shelf_check with the single most useful instruction. Name the bay and name the one thing to read. One errand, not a form. If a volunteer sends back a photograph of the case label, call read_case_label and the verdict is recomputed from what the photo actually shows. That settles it in either direction, and clearing a lot is as useful an answer as matching one.

   On NO_MATCH: do nothing further with that pair. Silence is correct and most of your work is silence.

When you draft a household notice, write what you would want to receive. Name the product, name when they got it and how much, say plainly what the hazard is, say exactly what to do with the food, and say the pantry will replace it. Use {household} where the family's name goes and {units} where the quantity goes. No greeting padded with feeling, no apology paragraph, no urgency theatre, no blame on the donor. Under 150 words. Many of these families do not read English as a first language and some are reading it on a phone, so use short sentences and concrete nouns.

These notices include botulism, salmonella and listeria. Say what the hazard is plainly and once. Do not soften it and do not dramatise it."""


def build_agent(
    pantry: Pantry,
    recalls: list[Recall],
    *,
    sink: CaseSink | None = None,
    model_id: str = MODEL_ID,
    approvals: set[str] | None = None,
) -> tuple[Agent, Ledger, list[dict]]:
    ledger = Ledger(
        pantry=pantry,
        recalls={r.recall_number: r for r in recalls},
        approvals=set(approvals or ()),
    )
    sink = sink or FileSink()
    events: list[dict] = []

    def log(event: str, detail: str) -> None:
        entry = {"at": _now(), "event": event, "detail": detail}
        events.append(entry)
        print(json.dumps(entry), flush=True)

    def _lot(lot_id: str) -> ShelfLot | None:
        return pantry.lot(lot_id)

    @tool
    def shelf_lots() -> str:
        """Every intake lot this pantry currently holds, with what was captured at intake."""
        lines = [
            f"{pantry.name}, {pantry.city} {pantry.state}: {len(pantry.lots)} lots, "
            f"{pantry.units_on_shelf} units on the shelf, {pantry.units_distributed} units "
            f"distributed to {len(pantry.households)} households."
        ]
        for lot in pantry.lots:
            out = sum(d.units for d in pantry.distributions_of(lot.lot_id))
            lines.append(
                f"  {lot.lot_id}  {lot.product_description}\n"
                f"    {lot.units_on_hand} on hand ({lot.cases_on_hand} cases) in "
                f"{lot.storage_location}, {out} units already distributed\n"
                f"    lot code {lot.lot_code or 'NOT CAPTURED'} ({lot.lot_code_source}), "
                f"best by {lot.best_by or 'not recorded'}, UPC {lot.upc or 'not recorded'}"
            )
        return "\n".join(lines)

    @tool
    def candidate_notices(lot_id: str) -> str:
        """Open FDA recall notices worth reading against one shelf lot, best first.

        Args:
            lot_id: The intake lot to check, e.g. INT-2026-0718-02.
        """
        lot = _lot(lot_id)
        if lot is None:
            return f"No lot {lot_id}. Known: {[l.lot_id for l in pantry.lots]}"
        found = candidates(lot, list(ledger.recalls.values()))
        ledger.considered += len(found)
        if not found:
            log("cleared", f"{lot_id}: no open notice resembles this product")
            return "No candidate notices. This lot is clear."
        head = (
            f"lot {lot.lot_id}: {lot.product_description!r}, received {lot.received_on} "
            f"from {lot.donor}, lot code {lot.lot_code or 'NOT CAPTURED'}, "
            f"best by {lot.best_by or 'not recorded'}"
        )
        # Every candidate the deterministic pass would have raised, not a
        # convenient top slice. A lot that draws twenty lookalike notices is
        # exactly the lot where truncating the list would hide the one the
        # model needed to reject, and the rejections are the value here.
        lines = [head]
        for recall in found[:_MAX_CANDIDATES]:
            ident = recall.identifiers
            lines.append(
                f"\n[{recall.recall_number}] {recall.classification}, reported "
                f"{recall.report_date}, firm {recall.firm}\n"
                f"  product: {recall.title[:400]}\n"
                f"  reason: {recall.reason[:240]}\n"
                f"  the notice identifies affected units by: "
                f"{len(ident.lot_codes)} lot code(s), {len(ident.upcs)} UPC(s), "
                f"{len(ident.best_by_dates)} best-by date(s)"
                + (", and says all units are affected" if ident.all_codes else "")
            )
        return "\n".join(lines)

    @tool
    def judge_identity(
        lot_id: str, recall_number: str, same_product: bool, confidence: float, reason: str
    ) -> str:
        """Record your read on whether a shelf lot and a notice describe one food, and get the verdict.

        Your read replaces the lexical word-overlap test only. The lot code,
        best-by date, UPC and distribution states are compared regardless of
        what you say here.

        Args:
            lot_id: The intake lot.
            recall_number: The notice you are comparing it against.
            same_product: True if the intake line and the notice describe the same food.
            confidence: 0.0 to 1.0, your honest confidence.
            reason: The specific wording that decided it for you.
        """
        lot = _lot(lot_id)
        recall = ledger.recalls.get(recall_number)
        if lot is None or recall is None:
            return f"Unknown lot {lot_id} or notice {recall_number}."
        assertion = IdentityAssertion(
            same_product=same_product,
            confidence=confidence,
            reason=reason,
            asserted_by=model_id,
        )
        exp = exposure(pantry, lot, recall, identity=assertion)
        ledger.record(exp)
        log(
            "verdict",
            f"{lot_id} vs {recall_number}: {exp.verdict.outcome.value} "
            f"by {exp.verdict.decided_by}",
        )
        detail = "\n".join(f"  {c}" for c in exp.verdict.checks)
        extra = ""
        if exp.verdict.missing:
            extra = "\nTo settle it, someone has to read: " + "; ".join(exp.verdict.missing)
        if exp.verdict.outcome is Outcome.MATCH:
            extra += (
                f"\nOn the shelf: {exp.units_on_hand} units ({exp.cases_on_hand} cases) in "
                f"{lot.storage_location}."
                f"\nAlready distributed: {exp.units_distributed} units to "
                f"{len(exp.households)} household(s)."
            )
        return f"verdict {exp.verdict.outcome.value} (decided by {exp.verdict.decided_by})\n{detail}{extra}"

    @tool
    def open_case(recall_number: str) -> str:
        """Persist one recall and everything it affects at this pantry, so it survives the pass.

        A case is one notice, not one lot. Open it once for a recall, however
        many lots matched it.

        Args:
            recall_number: The FDA recall number, e.g. F-0617-2025.
        """
        recall = ledger.recalls.get(recall_number)
        if recall is None:
            return f"Unknown notice {recall_number}."
        judged = [e for (_, n), e in ledger.exposures.items() if n == recall_number]
        if not judged:
            return f"Nothing to open: call judge_identity for a lot against {recall_number} first."
        interruption = Interruption(recall=recall, exposures=judged)
        if not interruption.actionable:
            return (
                f"{recall_number} affects nothing here: every lot checked came back NO_MATCH. "
                "No case is needed."
            )
        case = build_case(pantry, interruption)
        cid = case["case_id"]

        # A case this pantry has seen before keeps what the earlier pass learned.
        # The delivery record is the expensive one to lose: it is the only
        # durable proof households were already contacted, so dropping it would
        # let tomorrow's pass tell the same families the same thing again.
        previous = sink.read(pantry.pantry_id, cid)
        if previous:
            case["created_at"] = previous.get("created_at", case["created_at"])
            # The timeline is not carried forward here. `agent/store.py` owns
            # merging it, and doing it in both places concatenated the stored
            # copy with itself on every pass: six runs turned 22 real events
            # into 3,247 entries and a 378KB item against DynamoDB's 400KB
            # ceiling. Write the new entries only and let the store union them.
            for carried in ("delivery", "notice_text", "evidence_uri", "pull_record"):
                if previous.get(carried):
                    case[carried] = previous[carried]
            # `.get("delivery", {})` is wrong here and was a real bug: the key
            # exists on every stored case and its value is null until households
            # are notified, so the default never fires and the chained get
            # raises on None.
            if (previous.get("delivery") or {}).get("attempted"):
                case["status"] = previous.get("status", case["status"])
                ledger.notified.add(cid)
                log("already_notified", f"{cid} notified households on an earlier pass")
            if previous.get("notice_text"):
                ledger.drafts[cid] = previous["notice_text"]

        ledger.cases[cid] = case
        where = sink.write(case)
        log("case_opened", f"{cid} {recall_number} {case['headline']} -> {where}")
        return (
            f"Case {cid} open for {recall_number}, status {case['status']}, urgency "
            f"{case['urgency']}.\n"
            f"Pull: {case['pull']['cases']} case(s), {case['pull']['units']} units from "
            f"{', '.join(case['pull']['locations']) or 'nowhere'}.\n"
            f"Notify: {case['notify']['households']} household(s) holding "
            f"{case['notify']['units']} units, {case['notify']['children_under_5']} of them "
            f"with a child under five.\n"
            f"Needs a physical check: {len(case['needs_evidence'])} lot(s)."
        )

    @tool
    def draft_notice(case_id: str, notice_text: str) -> str:
        """Attach the message that will go to every household on this case.

        Args:
            case_id: The case this notice belongs to.
            notice_text: The full message. Must name the recall number and say what to do with the food.
        """
        case = ledger.cases.get(case_id)
        if case is None:
            return f"No open case {case_id}."
        number = case["recall"]["recall_number"]
        if number not in notice_text:
            return (
                f"Rejected: the notice must cite recall number {number}, so a household "
                "who calls the pantry or the firm can be matched to it."
            )
        if len(notice_text.split()) > 200:
            return "Rejected: too long. Under 150 words."
        ledger.drafts[case_id] = notice_text
        case["notice_text"] = notice_text
        case["timeline"].append(
            {"at": _now(), "event": "notice_drafted", "detail": f"{len(notice_text.split())} words"}
        )
        case["updated_at"] = _now()
        sink.write(case)
        log("notice_drafted", f"{case_id} cites {number}")
        return "Notice attached. It still needs the coordinator's approval before it is sent."

    @tool
    def notify_households(case_id: str) -> str:
        """Send the recall notice to every household that took this food home.

        Refused unless the engine returned a MATCH, those units have a
        distribution record, and a notice is drafted. Requires the
        coordinator's approval.

        Args:
            case_id: The case to notify on.
        """
        from agent.dispatch import notify_all

        case = ledger.cases.get(case_id)
        if case is None:
            return f"No open case {case_id}."
        delivery = notify_all(case, ledger.drafts[case_id])
        case["delivery"] = delivery
        case["status"] = "notified"
        ledger.notified.add(case_id)
        # The timeline says where the notices actually went, never where they
        # were aimed. SES is in sandbox, so a notice addressed to a household
        # may have been accepted for that address or routed to the mailbox
        # simulator, and a coordinator reading this case later has to be able to
        # tell which happened.
        case["timeline"].append(
            {
                "at": _now(),
                "event": "households_notified",
                "detail": (
                    f"{delivery['attempted']} notice(s) attempted: "
                    f"{delivery['direct']} delivered to the household's own address, "
                    f"{delivery['simulator']} routed to the SES mailbox simulator, "
                    f"{delivery['failed']} failed."
                ),
            }
        )
        case["updated_at"] = _now()
        sink.write(case)
        log("notified", f"{case_id}: {delivery['direct']} direct, {delivery['simulator']} simulator")
        return (
            f"Attempted {delivery['attempted']} notices. {delivery['direct']} were accepted for "
            f"the household's own address, {delivery['simulator']} went to the SES mailbox "
            f"simulator because sandbox would have rejected the real address, and "
            f"{delivery['failed']} failed. Households in the simulator group have NOT been "
            "reached; say so plainly."
        )

    @tool
    def record_pull(case_id: str, pulled_by: str, units_destroyed: int) -> str:
        """Record that the shelf units were taken off and destroyed.

        Args:
            case_id: The case being acted on.
            pulled_by: Who did it, as it should appear in the compliance record.
            units_destroyed: How many units actually came off the shelf.
        """
        case = ledger.cases.get(case_id)
        if case is None:
            return f"No open case {case_id}."
        expected = case["pull"]["units"]
        case["pull_record"] = {
            "at": _now(),
            "pulled_by": pulled_by,
            "units_destroyed": units_destroyed,
            "units_expected": expected,
            "complete": units_destroyed >= expected,
        }
        case["timeline"].append(
            {
                "at": _now(),
                "event": "pulled",
                "detail": (
                    f"{units_destroyed} of {expected} units destroyed by {pulled_by}"
                    + ("" if units_destroyed >= expected else ", short of the pull list")
                ),
            }
        )
        case["updated_at"] = _now()
        sink.write(case)
        log("pulled", f"{case_id}: {units_destroyed}/{expected} units")
        if units_destroyed < expected:
            return (
                f"Recorded {units_destroyed} of {expected} units. The record says the pull is "
                "incomplete. Do not close this case."
            )
        return f"Recorded. {units_destroyed} units destroyed, matching the pull list."

    @tool
    def request_shelf_check(case_id: str, instruction: str) -> str:
        """Ask a volunteer to go and read the one thing that settles a lot.

        Args:
            case_id: The case that is stuck.
            instruction: One errand. Name the bay and name the one code to read.
        """
        case = ledger.cases.get(case_id)
        if case is None:
            return f"No open case {case_id}."
        case["status"] = "needs_evidence"
        case["shelf_check"] = {"at": _now(), "instruction": instruction}
        case["timeline"].append({"at": _now(), "event": "shelf_check_requested", "detail": instruction})
        case["updated_at"] = _now()
        sink.write(case)
        log("shelf_check", f"{case_id}: {instruction}")
        return "Asked. The case waits until someone walks to the bay."

    @tool
    def read_case_label(lot_id: str, recall_number: str, image_path: str) -> str:
        """Read the stamped code off a photograph of a case label and recompute the verdict.

        Use when a lot is NEEDS_EVIDENCE and a volunteer has photographed the
        case. Also how intake captures a code in the first place.

        Args:
            lot_id: The intake lot the photograph is of.
            recall_number: The notice the recomputed verdict should be against.
            image_path: Path to the photograph.
        """
        from dataclasses import replace

        from agent.label import apply_reading, read_label

        lot = _lot(lot_id)
        recall = ledger.recalls.get(recall_number)
        if lot is None or recall is None:
            return f"Unknown lot {lot_id} or notice {recall_number}."
        reading = read_label(image_path, booking_in=lot.product_description)
        if not reading.image_legible:
            log("label_unreadable", f"{lot_id}: {reading.summary[:90]}")
            return (
                f"That photograph cannot be read: {reading.summary} "
                f"Ask for: {reading.reshoot_instruction}"
            )

        from datetime import date as _date

        enriched = apply_reading(lot.to_wire(), reading)
        updated = replace(
            lot,
            lot_code=enriched.get("lot_code"),
            lot_code_source=enriched.get("lot_code_source", lot.lot_code_source),
            upc=enriched.get("upc"),
            best_by=_date.fromisoformat(enriched["best_by"]) if enriched.get("best_by") else None,
            label_reading=enriched.get("label_reading"),
        )
        exp = exposure(pantry, updated, recall)
        ledger.record(exp)
        log("label_read", f"{lot_id}: {exp.verdict.outcome.value} by {exp.verdict.decided_by}")
        return (
            f"Read the label: {reading.summary}\n"
            f"lot code {reading.lot_code.status} {reading.lot_code.value or ''}, "
            f"best by {reading.best_by.status} {reading.best_by.value or ''}, "
            f"UPC {reading.upc.status} {reading.upc.value or ''}\n"
            f"The verdict for {lot_id} against {recall_number} is now "
            f"{exp.verdict.outcome.value} (decided by {exp.verdict.decided_by}).\n"
            + "\n".join(f"  {c}" for c in exp.verdict.checks)
        )

    @tool
    def file_compliance_record(case_id: str) -> str:
        """Write the disposal and notification record a health inspector would ask for.

        Args:
            case_id: The case to document.
        """
        from agent.compliance import put_record

        case = ledger.cases.get(case_id)
        if case is None:
            return f"No open case {case_id}."
        number = case["recall"]["recall_number"]
        cleared = [
            {
                "lot_id": e.lot.lot_id,
                "product_description": e.lot.product_description,
                "recall_number": number,
                "reason": str(e.verdict.failed[0]) if e.verdict.failed else "no identifier failed",
            }
            for (_, n), e in ledger.exposures.items()
            if n == number and e.verdict.outcome is Outcome.NO_MATCH
        ]
        written = put_record(case, cleared)
        case["evidence_uri"] = written["uri"]
        case["timeline"].append(
            {"at": _now(), "event": "record_filed", "detail": f"{written['bytes']} bytes to {written['uri']}"}
        )
        case["updated_at"] = _now()
        sink.write(case)
        log("record_filed", f"{case_id} -> {written['uri']}")
        return f"Filed. {written['uri']}"

    tools = [
        shelf_lots,
        candidate_notices,
        judge_identity,
        open_case,
        draft_notice,
        notify_households,
        record_pull,
        request_shelf_check,
        read_case_label,
        file_compliance_record,
    ]

    agent = Agent(
        model=AnthropicModel(model_id=model_id, max_tokens=4096),
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        hooks=[NotifyVeto(ledger, log)],
        interventions=[approval_gate(ledger, log)],
    )
    return agent, ledger, events
