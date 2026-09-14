"""The part of Best By that decides. No prompt reaches this file.

A recall notice is a paragraph about a batch. A shelf lot is a row in an intake
log. Deciding they describe the same product is reading, and the model is good
at it. Deciding whether this lot is inside that batch is string and date
comparison, and it happens here, where a model cannot argue with it.

Three outcomes, and the middle one is the product:

    MATCH           an identifier matched: this lot is in the recalled batch
    NEEDS_EVIDENCE  the notice is about this product and reached this state,
                    but nothing on the intake record settles which batch this
                    is, and one specific fact would. Send a volunteer to the
                    bay with the one thing to read.
    NO_MATCH        an identifier failed, or the product never shipped here.
                    Say nothing. Most of a pantry's shelf is this.

The order of the checks is the order of their strength, and it is not
cosmetic. A UPC and a lot code are decisive in both directions: if the notice
lists lot codes and this case's code is not among them, the case stays on the
shelf, and that is the answer that lets a pantry keep feeding people during a
recall instead of dumping a whole product line. Getting it backwards, treating
a mismatch as inconclusive, turns every recall into a total product pull, which
is what a paper process does and why pantries stop doing it.

`distribution` runs first because it is free and it is the most common true
negative in the whole feed: 77.1% of food enforcement reports name the states
the firm shipped to, and a pantry is in one state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from agent.feeds.base import Recall
from agent.shelf import ShelfLot


class Outcome(str, Enum):
    MATCH = "MATCH"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    NO_MATCH = "NO_MATCH"


@dataclass(frozen=True)
class IdentityAssertion:
    """The model's read on whether an intake line and a notice describe one product.

    An intake log says "Amy's Organic Lentil Soup Light in Sodium 14.5oz". The
    notice says "Amy's ORGANIC SOUPS LENTIL LIGHT IN SODIUM NET WT. 14.5 OZ.
    (411 g) Microwave: Place soup in a microwave-safe bowl...". Those are the
    same can, and a word-overlap score is a poor way to say so because the
    notice is half preparation instructions.

    This assertion may only replace `product_identity`, the soft lexical check.
    It can never touch the UPC, the lot code, the best-by date or the
    distribution state. The model may say "that is the same soup". It may never
    say "pull it anyway, the lot code does not matter".
    """

    same_product: bool
    confidence: float
    reason: str
    asserted_by: str

    MIN_CONFIDENCE = 0.7

    @property
    def usable(self) -> bool:
        return self.confidence >= self.MIN_CONFIDENCE


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str

    def __str__(self) -> str:
        return f"{'pass' if self.passed else 'FAIL'} {self.name}: {self.detail}"


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    checks: tuple[Check, ...]
    missing: tuple[str, ...] = ()
    decided_by: str = ""
    recall_number: str = ""
    lot_id: str = ""

    @property
    def passed(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.passed)

    @property
    def failed(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if not c.passed)

    @property
    def evidence_id(self) -> str:
        return f"{self.recall_number}:{self.lot_id}:{self.outcome.value}"


_STOP = {
    "the", "and", "for", "with", "from", "size", "pack", "count", "net", "wt",
    "oz", "lb", "lbs", "gram", "grams", "case", "cases", "per", "each", "inc",
    "llc", "ltd", "brand", "branded", "product", "products", "distributed",
    "packaged", "packed", "sold", "under", "following", "item", "items",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOP}


def _normalize_code(code: str) -> str:
    """Compare the characters a printer stamped, not the spaces a typist chose.

    Real example from F-0610-2025: the same notice lists both "S94N 42K" and
    "S94N42K" in one code_info field, because two people typed the same stamped
    code from the same can. A pantry's volunteer photographs it as a third
    spacing. Comparing raw strings would miss a real recall over whitespace.
    """
    return re.sub(r"[^a-z0-9]", "", code.lower())


def _distribution_check(lot: ShelfLot, recall: Recall, pantry_state: str) -> Check | None:
    ident = recall.identifiers
    if ident.nationwide:
        return Check("distribution", True, "the notice says the product went nationwide")
    if not ident.states:
        # 6.6% of reports name no geography at all. Absence is not exclusion, so
        # no check is emitted rather than a pass nobody verified.
        return None
    ok = pantry_state.upper() in ident.states
    listed = ", ".join(ident.states[:8]) + ("..." if len(ident.states) > 8 else "")
    return Check(
        "distribution",
        ok,
        f"{pantry_state.upper()} {'is' if ok else 'is not'} among the {len(ident.states)} "
        f"states the firm shipped to ({listed})",
    )


def _identity_check(lot: ShelfLot, recall: Recall, identity: IdentityAssertion | None) -> Check:
    if identity is not None and identity.usable:
        return Check(
            f"product_identity[{identity.asserted_by}]",
            identity.same_product,
            f"{identity.reason} (confidence {identity.confidence:.2f})",
        )
    mine = _tokens(f"{lot.brand} {lot.product_description}")
    theirs = _tokens(f"{recall.title}")
    shared = mine & theirs
    overlap = len(shared) / max(len(mine), 1)
    return Check(
        "product_identity",
        overlap >= 0.34,
        f"{overlap:.0%} of the intake line's words appear in the notice ({sorted(shared)[:6]})",
    )


def _upc_check(lot: ShelfLot, recall: Recall) -> Check | None:
    listed = recall.identifiers.upcs
    if not (lot.upc and listed):
        return None
    mine = _normalize_code(lot.upc)
    # Firms quote the same barcode as UPC-A (12) and as EAN-13 (12 plus a
    # leading zero). Compare on the 12 significant digits so one notation does
    # not read as a different product.
    def twelve(code: str) -> str:
        return code[-12:] if len(code) >= 12 else code

    ok = twelve(mine) in {twelve(_normalize_code(u)) for u in listed}
    return Check("upc", ok, f"UPC {lot.upc} {'is' if ok else 'is not'} on the notice ({len(listed)} listed)")


def _lot_code_check(lot: ShelfLot, recall: Recall) -> Check | None:
    listed = recall.identifiers.lot_codes
    if not (lot.lot_code and listed):
        return None
    mine = _normalize_code(lot.lot_code)
    ok = mine in {_normalize_code(c) for c in listed}
    shown = ", ".join(listed[:4]) + ("..." if len(listed) > 4 else "")
    return Check(
        "lot_code",
        ok,
        f"lot {lot.lot_code} {'is' if ok else 'is not'} among the {len(listed)} "
        f"recalled codes ({shown})",
    )


def _best_by_check(lot: ShelfLot, recall: Recall) -> Check | None:
    ident = recall.identifiers
    if lot.best_by is None:
        return None
    if ident.best_by_dates:
        ok = lot.best_by in ident.best_by_dates
        shown = ", ".join(d.isoformat() for d in ident.best_by_dates[:4])
        shown += "..." if len(ident.best_by_dates) > 4 else ""
        return Check(
            "best_by",
            ok,
            f"best by {lot.best_by.isoformat()} {'is' if ok else 'is not'} among the "
            f"{len(ident.best_by_dates)} recalled dates ({shown})",
        )
    if ident.best_by_before:
        ok = lot.best_by <= ident.best_by_before
        return Check(
            "best_by",
            ok,
            f"best by {lot.best_by.isoformat()} is {'on or before' if ok else 'after'} "
            f"the notice's bound of {ident.best_by_before.isoformat()}",
        )
    return None


def _missing_fact(lot: ShelfLot, recall: Recall) -> tuple[str, ...]:
    """The one thing to go and read, named as a physical act in a physical place."""
    ident = recall.identifiers
    where = lot.storage_location or "the storage bay"
    out: list[str] = []
    if ident.lot_codes and not lot.lot_code:
        out.append(f"the lot code stamped on the case in {where}")
    if (ident.best_by_dates or ident.best_by_before) and lot.best_by is None:
        out.append(f"the best-by date printed on the case in {where}")
    if ident.upcs and not lot.upc:
        out.append(f"the UPC barcode on a unit from {where}")
    if not out:
        out.append(
            f"a photograph of the case label in {where}: the notice does not publish "
            "a code this intake record can be checked against"
        )
    return tuple(out)


def decide(
    lot: ShelfLot,
    recall: Recall,
    *,
    pantry_state: str,
    identity: IdentityAssertion | None = None,
) -> Verdict:
    checks: list[Check] = []

    def result(outcome: Outcome, decided_by: str, missing: tuple[str, ...] = ()) -> Verdict:
        return Verdict(
            outcome=outcome,
            checks=tuple(checks),
            missing=missing,
            decided_by=decided_by,
            recall_number=recall.recall_number,
            lot_id=lot.lot_id,
        )

    distribution = _distribution_check(lot, recall, pantry_state)
    if distribution is not None:
        checks.append(distribution)
        if not distribution.passed:
            return result(Outcome.NO_MATCH, "distribution")

    identity_check = _identity_check(lot, recall, identity)
    checks.append(identity_check)
    if not identity_check.passed:
        return result(Outcome.NO_MATCH, "product_identity")

    upc = _upc_check(lot, recall)
    lot_code = _lot_code_check(lot, recall)
    # The printed date is only consulted when there is no stamped lot code to
    # compare, and that is not an optimisation. Firms publish both, and the two
    # lists are not always consistent with each other: F-0610-2025 names lot
    # S88ND1M in its code list while its best-by prose lists only two of the
    # six dates its own later sentence names. Reporting a failed date check
    # underneath a passed lot check would put a FAIL on a pull list that is
    # correct, and a coordinator who sees one contradictory line stops trusting
    # every line.
    best_by = None if lot_code is not None else _best_by_check(lot, recall)
    for check in (upc, lot_code, best_by):
        if check is not None:
            checks.append(check)

    # "All codes recalled", "all lots", "all prior batches/dates". The firm
    # pulled every unit of the product, so the barcode alone is the answer and a
    # lot code would add nothing. Without a UPC on either side there is still
    # nothing to check, and a product name is not an identifier.
    if recall.identifiers.all_codes:
        if upc is not None:
            return result(
                Outcome.MATCH if upc.passed else Outcome.NO_MATCH,
                "all_codes+upc",
            )
        if lot_code is not None and lot_code.passed:
            return result(Outcome.MATCH, "all_codes+lot_code")
        return result(Outcome.NEEDS_EVIDENCE, "all_codes", _missing_fact(lot, recall))

    # A stamped code is decisive in both directions. A pantry that cannot say
    # "this case is not the recalled batch" has to dump the whole product.
    if lot_code is not None:
        return result(Outcome.MATCH if lot_code.passed else Outcome.NO_MATCH, "lot_code")

    if best_by is not None and (recall.identifiers.best_by_dates or recall.identifiers.best_by_before):
        # The printed date is the only identifier 20.3% of food recalls publish.
        # It is weaker than a lot code, which is why the lot code is checked
        # first, but it is a real stamped value on a real case.
        return result(Outcome.MATCH if best_by.passed else Outcome.NO_MATCH, "best_by")

    if upc is not None and upc.passed and not recall.identifiers.checkable_beyond_upc:
        # The notice published a barcode and nothing else. Every unit carrying
        # that barcode is implicated, so the shelf lot is in scope.
        return result(Outcome.MATCH, "upc_only_notice")

    if upc is not None and not upc.passed:
        return result(Outcome.NO_MATCH, "upc")

    return result(Outcome.NEEDS_EVIDENCE, "no_identifier", _missing_fact(lot, recall))
