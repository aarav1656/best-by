"""The split between pulling and notifying, and the grouping that follows it.

Everything in `verdict.py` answers "is this the recalled batch". This file
tests the thing that makes Best By a product rather than a matcher: units on a
shelf and units in a family's cupboard are different obligations, and a system
that reports one total has told the coordinator nothing they can act on.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.casefile import build_case, build_cases, sweep_summary
from agent.engine.sweep import Interruption, candidates, exposure, sweep
from agent.engine.verdict import Outcome

RAN_AT = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc).isoformat()


@pytest.fixture(scope="module")
def result(pantry, recalls):
    return sweep(pantry, recalls, ran_at=RAN_AT)


def test_the_pass_only_considers_open_recalls(pantry, recalls, result):
    assert result.recalls_considered == sum(1 for r in recalls if r.open)
    assert result.recalls_considered < len(recalls)


def test_a_match_with_stock_and_distribution_obliges_both_actions(pantry, by_number, lots):
    exp = exposure(pantry, lots["INT-2026-0718-02"], by_number["F-0617-2025"])
    assert exp.verdict.outcome is Outcome.MATCH
    assert exp.units_on_hand == 84
    assert exp.units_distributed == 63
    assert exp.actions == ("PULL", "NOTIFY")


def test_a_match_with_stock_and_no_distribution_is_a_pull_only(pantry, by_number, lots):
    """36 bags of recalled popcorn, none of it handed out. Nobody to warn."""
    exp = exposure(pantry, lots["INT-2026-0813-02"], by_number["H-1234-2026"])
    assert exp.verdict.outcome is Outcome.MATCH
    assert exp.units_distributed == 0
    assert exp.actions == ("PULL",)
    assert exp.notify is False


def test_a_cleared_lot_obliges_nothing(pantry, by_number, lots):
    exp = exposure(pantry, lots["INT-2026-0829-03"], by_number["H-1174-2026"])
    assert exp.verdict.outcome is Outcome.NO_MATCH
    assert exp.actions == ()


def test_cases_are_counted_up_not_units(pantry, by_number, lots):
    """A volunteer carries cases. 84 units of 24 is 4 cases, not 3.5."""
    exp = exposure(pantry, lots["INT-2026-0718-02"], by_number["F-0617-2025"])
    assert exp.units_on_hand == 84
    assert exp.cases_on_hand == 4


def test_one_recall_is_one_interruption_however_many_lots(pantry, by_number, lots, result):
    """F-0610-2025 hits two separate tuna intakes. The coordinator sees one card."""
    tuna = next(i for i in result.actionable if i.recall.recall_number == "F-0610-2025")
    assert len(tuna.matched) == 2
    assert {e.lot.lot_id for e in tuna.matched} == {"INT-2026-0718-02", "INT-2026-0728-01"}
    assert tuna.headline() == "pull 7 cases, notify 14 households"


def test_a_household_on_two_lots_of_one_recall_is_counted_once(pantry, by_number, lots):
    """Otherwise a family that came back twice gets two notices about one recall."""
    exps = [
        exposure(pantry, lots["INT-2026-0718-02"], by_number["F-0610-2025"]),
        exposure(pantry, lots["INT-2026-0728-01"], by_number["F-0610-2025"]),
    ]
    interruption = Interruption(recall=by_number["F-0610-2025"], exposures=exps)
    ids = [h.household_id for h in interruption.households_to_notify]
    assert len(ids) == len(set(ids))

    case = build_case(pantry, interruption)
    rows = case["notify"]["recipients"]
    assert len({r["household_id"] for r in rows}) == len(rows)
    ellis = next(r for r in rows if r["household_id"] == "H-0158")
    # Ellis took units from both intakes. One row, the units summed.
    assert sorted(ellis["lots"]) == ["INT-2026-0728-01"]


def test_class_one_plus_distributed_product_is_the_only_same_day_case(by_number, pantry, lots):
    salmonella = Interruption(
        recall=by_number["H-0835-2026"],
        exposures=[exposure(pantry, lots["INT-2026-0625-01"], by_number["H-0835-2026"])],
    )
    assert salmonella.recall.class_i
    assert salmonella.units_distributed > 0
    assert salmonella.urgency == "same_day"

    mislabelled = Interruption(
        recall=by_number["H-1234-2026"],
        exposures=[exposure(pantry, lots["INT-2026-0813-02"], by_number["H-1234-2026"])],
    )
    assert not mislabelled.recall.class_i
    assert mislabelled.units_distributed == 0
    assert mislabelled.urgency == "this_week"


def test_the_queue_puts_the_dangerous_one_first(result):
    urgencies = [i.urgency for i in result.actionable]
    order = ["same_day", "today", "this_week", "check"]
    assert urgencies == sorted(urgencies, key=order.index)
    assert urgencies[0] == "same_day"


def test_households_with_small_children_are_listed_first(pantry, by_number, lots):
    """Listeria and botulism notices name under-fives as the population at risk."""
    case = build_case(
        pantry,
        Interruption(
            recall=by_number["F-0617-2025"],
            exposures=[exposure(pantry, lots["INT-2026-0718-02"], by_number["F-0617-2025"])],
        ),
    )
    rows = case["notify"]["recipients"]
    kids = [r["children_under_5"] for r in rows]
    assert kids == sorted(kids, reverse=True)
    assert rows[0]["children_under_5"] > 0


def test_lots_cleared_by_a_code_comparison_are_kept_for_the_record(result):
    """The inspector's question is 'did you check', not 'did you find anything'."""
    cleared = {(e.lot.lot_id, e.recall.recall_number) for e in result.cleared}
    assert ("INT-2026-0829-03", "H-1174-2026") in cleared
    assert all(
        e.verdict.decided_by in {"lot_code", "best_by", "upc", "all_codes+upc"}
        for e in result.cleared
    )


def test_pairs_killed_by_geography_are_not_kept_as_evidence(result):
    """There are hundreds of them and none of them is evidence of anything."""
    assert not any(e.verdict.decided_by == "distribution" for e in result.cleared)


def test_candidate_retrieval_narrows_before_the_model_is_asked(pantry, recalls, result):
    """23 lots against 614 open recalls is 14,122 pairs. The model sees 202."""
    open_recalls = sum(1 for r in recalls if r.open)
    assert result.pairs_evaluated < open_recalls * len(pantry.lots) / 50


def test_a_matching_barcode_is_a_candidate_whatever_the_words_say(pantry, by_number, lots):
    """An identifier outranks any amount of word overlap."""
    found = candidates(lots["INT-2026-0813-02"], [by_number["H-1234-2026"]])
    assert found == [by_number["H-1234-2026"]]


def test_most_of_the_shelf_never_becomes_a_candidate(pantry, recalls, result):
    """A pantry's ordinary staples must produce silence, not noise."""
    touched = {
        e.lot.lot_id for i in result.interruptions for e in i.exposures
    } | {e.lot.lot_id for e in result.cleared}
    untouched = [l.lot_id for l in pantry.lots if l.lot_id not in touched]
    assert len(untouched) >= 8


def test_the_summary_only_reports_numbers_it_computed(pantry, result):
    summary = sweep_summary(pantry, result)
    assert summary["lots_checked"] == len(pantry.lots)
    assert summary["units_on_shelf"] == sum(l.units_on_hand for l in pantry.lots)
    assert summary["units_distributed"] == sum(d.units for d in pantry.distributions)
    assert summary["cases_to_pull"] == sum(i.cases_to_pull for i in result.actionable)
    assert summary["quiet"] is False


def test_a_pantry_with_a_clean_shelf_produces_an_empty_queue(pantry, recalls):
    """Healthy state is empty, and the code has to be able to reach it."""
    from dataclasses import replace

    clean = replace(pantry, lots=tuple(l for l in pantry.lots if l.brand == "Barilla"))
    result = sweep(clean, recalls, ran_at=RAN_AT)
    assert result.quiet is True
    assert build_cases(clean, result) == []


def test_every_case_carries_the_checks_that_produced_it(pantry, result):
    for case in build_cases(pantry, result):
        for lot in case["pull"]["lots"]:
            assert lot["checks"]
            assert all(c["detail"] for c in lot["checks"])
            assert lot["decided_by"]
