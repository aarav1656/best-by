"""The decision engine, against real notices and the real intake log.

The tests that matter here are the negative ones. A matcher that finds every
recall is easy and useless: it produces a total product pull every time, which
is what a paper process does. The engine earns its place by saying "this case
is not the recalled batch, keep handing it out", and being right.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from agent.engine.verdict import IdentityAssertion, Outcome, decide


def test_a_photographed_lot_code_matches_a_single_lot_recall(lots, by_number):
    """The whole product in one assertion.

    INT-2026-0718-02's lot code was read by the vision model off an FDA-published
    photograph of the stamped can bottom. F-0617-2025 recalls exactly one lot.
    They are the same string, and nobody typed it in to make this pass.
    """
    verdict = decide(lots["INT-2026-0718-02"], by_number["F-0617-2025"], pantry_state="OH")
    assert verdict.outcome is Outcome.MATCH
    assert verdict.decided_by == "lot_code"
    assert lots["INT-2026-0718-02"].lot_code_source == "label_photo"


def test_the_same_product_in_a_different_batch_stays_on_the_shelf(lots, by_number):
    """INT-2026-0829-03 is the identical Amy's soup in a lot the notice does not name.

    This is the answer that lets a pantry keep feeding people during a recall.
    An engine that returns NEEDS_EVIDENCE here has told the coordinator to dump
    108 cans of good soup.
    """
    verdict = decide(lots["INT-2026-0829-03"], by_number["H-1174-2026"], pantry_state="OH")
    assert verdict.outcome is Outcome.NO_MATCH
    assert verdict.decided_by == "lot_code"
    failed = {c.name for c in verdict.failed}
    assert failed == {"lot_code"}


def test_the_recalled_batch_of_the_same_product_is_pulled(lots, by_number):
    verdict = decide(lots["INT-2026-0704-01"], by_number["H-1174-2026"], pantry_state="OH")
    assert verdict.outcome is Outcome.MATCH
    assert verdict.decided_by == "lot_code"


def test_a_notice_that_never_shipped_here_is_not_a_shelf_walk(lots, by_number):
    """H-0850-2026 went to PA and WI. The pantry is in Ohio."""
    verdict = decide(lots["INT-2026-0715-05"], by_number["H-0850-2026"], pantry_state="OH")
    assert verdict.outcome is Outcome.NO_MATCH
    assert verdict.decided_by == "distribution"


def test_the_same_notice_in_a_state_it_shipped_to_is_not_dismissed(lots, by_number):
    """The geography check must be able to pass, or it is not a check."""
    verdict = decide(lots["INT-2026-0715-05"], by_number["H-0850-2026"], pantry_state="WI")
    assert verdict.outcome is not Outcome.NO_MATCH
    assert [c for c in verdict.checks if c.name == "distribution"][0].passed


def test_a_printed_date_decides_when_the_notice_published_no_lot_code(lots, by_number):
    """H-0835-2026 is Class I and its only identifier is BEST BY 23/MAR/2027."""
    recall = by_number["H-0835-2026"]
    assert recall.identifiers.lot_codes == ()
    verdict = decide(lots["INT-2026-0625-01"], recall, pantry_state="OH")
    assert verdict.outcome is Outcome.MATCH
    assert verdict.decided_by == "best_by"


def test_a_printed_date_outside_the_stated_bound_clears_the_lot(lots, by_number):
    """H-1264-2026 bounds at 2027-10-31. The pantry's bars are stamped 2027-11-30."""
    verdict = decide(lots["INT-2026-0722-01"], by_number["H-1264-2026"], pantry_state="OH")
    assert verdict.outcome is Outcome.NO_MATCH
    assert verdict.decided_by == "best_by"


def test_all_units_language_makes_the_barcode_decisive(lots, by_number):
    """H-1234-2026 recalls every unit, so no lot code is needed or expected."""
    verdict = decide(lots["INT-2026-0813-02"], by_number["H-1234-2026"], pantry_state="OH")
    assert verdict.outcome is Outcome.MATCH
    assert verdict.decided_by == "all_codes+upc"


def test_all_units_language_still_clears_a_different_barcode(lots, by_number):
    """H-1233-2026 is the same firm, same 'all codes', a different flavour."""
    verdict = decide(lots["INT-2026-0813-02"], by_number["H-1233-2026"], pantry_state="OH")
    assert verdict.outcome is Outcome.NO_MATCH


def test_an_unreadable_intake_photo_becomes_an_errand_not_a_guess(lots, by_number):
    """INT-2026-0806-02's intake photo failed, so no lot code was captured.

    The engine must not guess and must not stay silent. It names the bay and the
    one thing to read, which is the entire cost of having missed the photo.
    """
    lot = lots["INT-2026-0806-02"]
    assert lot.lot_code is None
    assert lot.lot_code_source == "photo_unreadable"
    verdict = decide(lot, by_number["H-1223-2026"], pantry_state="OH")
    assert verdict.outcome is Outcome.NEEDS_EVIDENCE
    assert any("lot code" in m for m in verdict.missing)
    assert any("Family Shelf D1" in m for m in verdict.missing)


def test_capturing_the_lot_code_turns_that_errand_into_an_answer(lots, by_number):
    """The same lot with a code captured needs no volunteer and no printout.

    260317 is one of the five codes H-1223-2026 actually recalls.
    """
    lot = replace(lots["INT-2026-0806-02"], lot_code="260317", lot_code_source="label_photo")
    verdict = decide(lot, by_number["H-1223-2026"], pantry_state="OH")
    assert verdict.outcome is Outcome.MATCH
    assert verdict.decided_by == "lot_code"


def test_whitespace_in_a_stamped_code_does_not_lose_a_recall(lots, by_number):
    """F-0610-2025 lists S94N 42K and S94N42K, typed by two different people."""
    spaced = replace(lots["INT-2026-0728-01"], lot_code="s94n42k")
    assert decide(spaced, by_number["F-0610-2025"], pantry_state="OH").outcome is Outcome.MATCH


def test_the_model_may_overrule_word_overlap_and_nothing_else(lots, by_number):
    """An identity assertion replaces the lexical check. It cannot reach a code.

    The model says, with full confidence, that a jar of Skippy is a can of
    recalled Amy's lentil soup. The lot code says otherwise and the lot code
    wins, which is the property the whole design rests on.
    """
    lie = IdentityAssertion(
        same_product=True, confidence=1.0, reason="I am certain", asserted_by="test"
    )
    verdict = decide(
        lots["INT-2026-0829-03"], by_number["H-1174-2026"], pantry_state="OH", identity=lie
    )
    assert verdict.outcome is Outcome.NO_MATCH
    assert verdict.decided_by == "lot_code"


def test_a_low_confidence_assertion_is_ignored(lots, by_number):
    unsure = IdentityAssertion(
        same_product=False, confidence=0.2, reason="not sure", asserted_by="test"
    )
    verdict = decide(
        lots["INT-2026-0704-01"], by_number["H-1174-2026"], pantry_state="OH", identity=unsure
    )
    # Below MIN_CONFIDENCE the assertion is discarded and the lexical check runs,
    # so the outcome is whatever the codes say, not whatever the model said.
    assert verdict.outcome is Outcome.MATCH
    assert not any(c.name.startswith("product_identity[") for c in verdict.checks)


def test_the_model_can_stop_a_lexical_false_positive(lots, by_number):
    """Jif and Ritz peanut butter cracker sandwiches share 40% of a short line."""
    lexical = decide(lots["INT-2026-0709-02"], by_number["H-0326-2025"], pantry_state="OH")
    assert lexical.outcome is Outcome.NEEDS_EVIDENCE

    read = IdentityAssertion(
        same_product=False,
        confidence=0.97,
        reason="a jar of peanut butter is not a cracker sandwich",
        asserted_by="test",
    )
    with_model = decide(
        lots["INT-2026-0709-02"], by_number["H-0326-2025"], pantry_state="OH", identity=read
    )
    assert with_model.outcome is Outcome.NO_MATCH
    assert with_model.decided_by == "product_identity"


def test_the_weaker_identifier_is_not_reported_under_the_stronger_one(lots, by_number):
    """A lot code decides. A contradicting date check must not appear beside it.

    F-0610-2025 lists S88ND1M as a recalled code but its best-by prose names only
    two of the six dates its own later sentence names, so 2028-01-17 is absent
    from the parsed list. A FAIL line underneath a correct pull instruction is
    how a coordinator learns to stop reading the lines.
    """
    verdict = decide(lots["INT-2026-0718-02"], by_number["F-0610-2025"], pantry_state="OH")
    assert verdict.outcome is Outcome.MATCH
    assert {c.name for c in verdict.checks} == {"distribution", "product_identity", "lot_code"}


def test_every_verdict_can_be_explained_by_naming_its_checks(lots, by_number):
    verdict = decide(lots["INT-2026-0718-02"], by_number["F-0617-2025"], pantry_state="OH")
    assert verdict.checks
    assert verdict.evidence_id == "F-0617-2025:INT-2026-0718-02:MATCH"
    assert all(c.detail for c in verdict.checks)
