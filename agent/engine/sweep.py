"""One recall, two obligations, and the arithmetic that separates them.

Everything upstream of this file answers "is this case in the recalled batch".
This file answers the question a coordinator actually has, which is what to do
about it, and the answer is two different things at once:

    PULL     units still on the shelf. A volunteer walks to a bay, takes cases
             off, and the pantry destroys them and writes down that it did.
    NOTIFY   units that already went home with a household. Nothing can be
             pulled. Someone has to be told, by name, that food they were given
             is being recalled and why.

A pull list is a chore. A notification list is the only part of a recall that
reaches a person who might otherwise eat the food. They have different urgency,
different recipients, and different failure modes, and a system that reports
"14 affected units" without splitting them has told the coordinator nothing
actionable. The split is not a display concern: `notify_households` is the one
irreversible tool in this agent, and it is gated on the distribution record
this module produces, not on the verdict alone.

`Interruption` is the unit of attention. It groups every affected lot under one
recall, because the coordinator's decision is "do I act on this notice", once,
not "do I act on this case" fourteen times. A pantry that gets interrupted per
case stops reading the interruptions, which is the failure the paper process
already has.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent.engine.verdict import IdentityAssertion, Outcome, Verdict, decide
from agent.feeds.base import Recall
from agent.shelf import Distribution, Household, Pantry, ShelfLot


@dataclass(frozen=True)
class Exposure:
    """One shelf lot judged against one recall, with what it obliges."""

    lot: ShelfLot
    recall: Recall
    verdict: Verdict
    units_on_hand: int
    cases_on_hand: int
    distributions: tuple[Distribution, ...]
    households: tuple[Household, ...]

    @property
    def units_distributed(self) -> int:
        return sum(d.units for d in self.distributions)

    @property
    def pull(self) -> bool:
        return self.verdict.outcome is Outcome.MATCH and self.units_on_hand > 0

    @property
    def notify(self) -> bool:
        return self.verdict.outcome is Outcome.MATCH and bool(self.distributions)

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(a for a, on in (("PULL", self.pull), ("NOTIFY", self.notify)) if on)

    @property
    def households_with_children(self) -> tuple[Household, ...]:
        return tuple(h for h in self.households if h.high_risk)


@dataclass
class Interruption:
    """One recall, everything it affects, and the single decision it asks for."""

    recall: Recall
    exposures: list[Exposure] = field(default_factory=list)

    @property
    def matched(self) -> list[Exposure]:
        return [e for e in self.exposures if e.verdict.outcome is Outcome.MATCH]

    @property
    def unresolved(self) -> list[Exposure]:
        return [e for e in self.exposures if e.verdict.outcome is Outcome.NEEDS_EVIDENCE]

    @property
    def cleared(self) -> list[Exposure]:
        return [e for e in self.exposures if e.verdict.outcome is Outcome.NO_MATCH]

    @property
    def units_to_pull(self) -> int:
        return sum(e.units_on_hand for e in self.matched if e.pull)

    @property
    def cases_to_pull(self) -> int:
        return sum(e.cases_on_hand for e in self.matched if e.pull)

    @property
    def units_distributed(self) -> int:
        return sum(e.units_distributed for e in self.matched)

    @property
    def households_to_notify(self) -> tuple[Household, ...]:
        seen: dict[str, Household] = {}
        for e in self.matched:
            if not e.notify:
                continue
            for h in e.households:
                seen.setdefault(h.household_id, h)
        return tuple(seen.values())

    @property
    def actionable(self) -> bool:
        return bool(self.matched or self.unresolved)

    @property
    def urgency(self) -> str:
        """Class I plus product already out the door is the only same-day case.

        Class I means the FDA judged a reasonable probability of serious health
        consequence or death. Everything else can wait for the next shift, and
        saying so is what keeps the queue readable.
        """
        if not self.matched:
            return "check" if self.unresolved else "none"
        if self.recall.class_i and self.units_distributed > 0:
            return "same_day"
        if self.recall.class_i or self.units_distributed > 0:
            return "today"
        return "this_week"

    def headline(self) -> str:
        parts = []
        if self.cases_to_pull:
            parts.append(f"pull {self.cases_to_pull} case{'s' if self.cases_to_pull != 1 else ''}")
        households = self.households_to_notify
        if households:
            parts.append(f"notify {len(households)} household{'s' if len(households) != 1 else ''}")
        if self.unresolved:
            parts.append(f"check {len(self.unresolved)} lot{'s' if len(self.unresolved) != 1 else ''}")
        return ", ".join(parts) or "nothing to do"


@dataclass
class Sweep:
    """One pass over the whole pantry against one batch of notices."""

    pantry_id: str
    pantry_state: str
    ran_at: str
    lots_checked: int
    recalls_considered: int
    pairs_evaluated: int
    interruptions: list[Interruption] = field(default_factory=list)
    # A pantry's inspector asks "did you check?", not "did you find anything".
    # A lot whose stamped code was compared against a recalled code and did not
    # match is the most valuable line in a compliance record, because it is the
    # one that justifies having kept feeding people out of that bay. Pairs
    # killed by geography or by not being the same product are not kept: there
    # are hundreds of them and none of them is evidence of anything.
    cleared: list[Exposure] = field(default_factory=list)

    @property
    def actionable(self) -> list[Interruption]:
        order = {"same_day": 0, "today": 1, "this_week": 2, "check": 3, "none": 4}
        return sorted(
            (i for i in self.interruptions if i.actionable),
            key=lambda i: (order[i.urgency], -i.units_distributed, -i.units_to_pull),
        )

    @property
    def quiet(self) -> bool:
        return not self.actionable


# A recall notice is a product description plus preparation instructions plus a
# firm address. Only the first few words are the product. Past roughly this
# many characters a notice is describing packaging, not identity, and including
# it dilutes the token overlap that finds candidates worth judging.
_TITLE_HEAD = 160
_CANDIDATE_STOP = {
    "the", "and", "for", "with", "from", "size", "pack", "count", "net", "wt",
    "oz", "lb", "lbs", "case", "cases", "per", "each", "inc", "llc", "ltd",
    "brand", "branded", "product", "products", "distributed", "packaged",
    "packed", "sold", "under", "following", "item", "items", "bag", "bags",
    "box", "boxes", "can", "cans", "jar", "jars", "container", "containers",
}


def _candidate_tokens(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-z]+", text.lower())
        if len(w) > 3 and w not in _CANDIDATE_STOP
    }


def candidates(lot: ShelfLot, recalls: list[Recall], *, floor: float = 0.25) -> list[Recall]:
    """Notices worth spending a model turn on for one shelf lot.

    A pantry with 40 lots against 614 open recalls is 24,560 pairs. Judging
    every pair with a model would cost more than the pantry's annual food
    budget, so this narrows by hand first and the model only reads what is
    left. A barcode that matches exactly skips the lexical test entirely, since
    an identifier is worth more than any amount of word overlap.
    """
    mine = _candidate_tokens(f"{lot.brand} {lot.product_description}")
    if not mine:
        return []
    my_upc = re.sub(r"\D", "", lot.upc or "")[-12:]
    out: list[tuple[float, Recall]] = []
    for recall in recalls:
        if my_upc:
            listed = {re.sub(r"\D", "", u)[-12:] for u in recall.identifiers.upcs}
            if my_upc in listed:
                out.append((1.0, recall))
                continue
        theirs = _candidate_tokens(recall.title[:_TITLE_HEAD])
        if not theirs:
            continue
        score = len(mine & theirs) / min(len(mine), len(theirs))
        if score >= floor:
            out.append((score, recall))
    out.sort(key=lambda pair: pair[0], reverse=True)
    return [r for _, r in out]


def exposure(
    pantry: Pantry,
    lot: ShelfLot,
    recall: Recall,
    *,
    identity: IdentityAssertion | None = None,
) -> Exposure:
    verdict = decide(lot, recall, pantry_state=pantry.state, identity=identity)
    dists = pantry.distributions_of(lot.lot_id)
    households = tuple(
        h for h in (pantry.household(d.household_id) for d in dists) if h is not None
    )
    return Exposure(
        lot=lot,
        recall=recall,
        verdict=verdict,
        units_on_hand=lot.units_on_hand,
        cases_on_hand=lot.cases_on_hand,
        distributions=dists,
        households=households,
    )


def sweep(
    pantry: Pantry,
    recalls: list[Recall],
    *,
    ran_at: str,
    open_only: bool = True,
) -> Sweep:
    """The deterministic pass. Runs with no model and no credentials.

    This is what the scheduled Lambda runs every morning, and what the tests
    run offline. The model's identity read is an improvement layered on top by
    `agent/bestby_agent.py`, never a dependency: a pantry whose API key expires
    still gets its shelf checked, on lexical identity plus exact codes.
    """
    pool = [r for r in recalls if r.open] if open_only else list(recalls)
    grouped: dict[str, Interruption] = {}
    cleared: list[Exposure] = []
    pairs = 0
    for lot in pantry.lots:
        for recall in candidates(lot, pool):
            pairs += 1
            exp = exposure(pantry, lot, recall)
            if exp.verdict.outcome is Outcome.NO_MATCH:
                if exp.verdict.decided_by in {"lot_code", "best_by", "upc", "all_codes+upc"}:
                    cleared.append(exp)
                continue
            grouped.setdefault(recall.recall_number, Interruption(recall=recall)).exposures.append(exp)
    return Sweep(
        pantry_id=pantry.pantry_id,
        pantry_state=pantry.state,
        ran_at=ran_at,
        lots_checked=len(pantry.lots),
        recalls_considered=len(pool),
        pairs_evaluated=pairs,
        interruptions=list(grouped.values()),
        cleared=cleared,
    )
