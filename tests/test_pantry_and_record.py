"""The intake log, and the document a health inspector is handed.

The compliance record is the deliverable a pantry is actually audited on, so
these tests assert on its content rather than on the fact that a file was
written. A record that omits what was checked and cleared is the one that gets
a pantry written up, because it cannot explain why the rest of the pallet
stayed in distribution.
"""

from __future__ import annotations

from datetime import date

import pytest

from agent.casefile import build_case
from agent.compliance import render_record
from agent.engine.sweep import Interruption, exposure
from agent.shelf import load_pantry
from agent.store import _from_dynamo, _to_dynamo, case_id


def test_the_intake_log_loads_as_three_related_tables(pantry):
    assert pantry.state == "OH"
    assert len(pantry.lots) == 23
    assert len(pantry.households) == 14
    assert pantry.distributions
    assert pantry.units_on_shelf == sum(l.units_on_hand for l in pantry.lots)


def test_every_distribution_points_at_a_real_lot_and_a_real_household(pantry):
    lot_ids = {l.lot_id for l in pantry.lots}
    household_ids = {h.household_id for h in pantry.households}
    for dist in pantry.distributions:
        assert dist.lot_id in lot_ids, f"{dist.distribution_id} references a lot that does not exist"
        assert dist.household_id in household_ids


def test_no_lot_distributed_more_than_it_received(pantry):
    for lot in pantry.lots:
        out = sum(d.units for d in pantry.distributions_of(lot.lot_id))
        assert out + lot.units_on_hand <= lot.units_received, lot.lot_id


def test_cases_on_hand_rounds_up_because_a_part_case_is_still_a_case(pantry):
    lot = pantry.lot("INT-2026-0718-02")
    assert lot.units_on_hand == 84
    assert lot.units_per_case == 24
    assert lot.cases_on_hand == 4


def test_the_log_records_how_each_code_was_captured(pantry):
    sources = {l.lot_code_source for l in pantry.lots}
    assert "label_photo" in sources
    assert "photo_unreadable" in sources
    unreadable = [l for l in pantry.lots if l.lot_code_source == "photo_unreadable"]
    assert all(l.lot_code is None for l in unreadable), (
        "a lot whose photo could not be read must not carry a lot code"
    )


def test_at_least_one_lot_carries_a_code_read_from_a_photograph(pantry):
    photographed = [l for l in pantry.lots if l.label_photo and l.lot_code_source == "label_photo"]
    assert photographed
    assert any(l.lot_id == "INT-2026-0718-02" for l in photographed)


def test_a_household_with_small_children_is_flagged(pantry):
    assert pantry.household("H-0166").high_risk is True
    assert pantry.household("H-0158").high_risk is False


def test_the_case_id_is_stable_across_passes():
    assert case_id("riverbend-dayton", "F-0617-2025") == case_id("riverbend-dayton", "F-0617-2025")
    assert case_id("riverbend-dayton", "F-0617-2025") != case_id("riverbend-dayton", "F-0610-2025")
    assert case_id("other-pantry", "F-0617-2025") != case_id("riverbend-dayton", "F-0617-2025")


def test_dynamo_round_trip_keeps_integers_integers():
    """Decimal leaking out of this boundary would show up as 4.0 cases on a pull list."""
    original = {"units": 84, "cases": 4, "ratio": 0.5, "lots": ["a", "b"], "nested": {"n": 12}}
    assert _from_dynamo(_to_dynamo(original)) == original


def test_the_record_names_the_notice_the_lot_and_the_check(pantry, by_number):
    case = build_case(
        pantry,
        Interruption(
            recall=by_number["F-0617-2025"],
            exposures=[exposure(pantry, pantry.lot("INT-2026-0718-02"), by_number["F-0617-2025"])],
        ),
    )
    text = render_record(case)
    assert "F-0617-2025" in text
    assert "INT-2026-0718-02" in text
    assert "Dry Goods A3" in text
    assert "S88N D1M" in text
    assert "label_photo" in text
    # The sentence that makes destroying 84 cans defensible to the food bank.
    assert "lot S88N D1M is among the 1 recalled codes" in text


def test_the_record_separates_destroyed_product_from_distributed_product(pantry, by_number):
    case = build_case(
        pantry,
        Interruption(
            recall=by_number["F-0617-2025"],
            exposures=[exposure(pantry, pantry.lot("INT-2026-0718-02"), by_number["F-0617-2025"])],
        ),
    )
    text = render_record(case)
    assert "PRODUCT REMOVED FROM DISTRIBUTION" in text
    assert "PRODUCT ALREADY DISTRIBUTED TO HOUSEHOLDS" in text
    assert "H-0166" in text
    assert "not yet" in text, "an unsent notice must not read as sent"


def test_the_record_keeps_what_was_checked_and_cleared(pantry, by_number):
    """The line that justifies having kept handing the rest of the pallet out."""
    case = build_case(
        pantry,
        Interruption(
            recall=by_number["H-1174-2026"],
            exposures=[exposure(pantry, pantry.lot("INT-2026-0704-01"), by_number["H-1174-2026"])],
        ),
    )
    cleared = [
        {
            "lot_id": "INT-2026-0829-03",
            "product_description": "Amy's Organic Soups Lentil Light in Sodium, 14.5 oz can",
            "recall_number": "H-1174-2026",
            "reason": "FAIL lot_code: lot 60G1187 is not among the 1 recalled codes (60D0924)",
        }
    ]
    text = render_record(case, cleared)
    assert "LOTS CHECKED AND FOUND NOT AFFECTED" in text
    assert "60G1187" in text
    assert "INT-2026-0829-03" in text


def test_a_needs_evidence_case_records_the_errand(pantry, by_number):
    case = build_case(
        pantry,
        Interruption(
            recall=by_number["H-1223-2026"],
            exposures=[exposure(pantry, pantry.lot("INT-2026-0806-02"), by_number["H-1223-2026"])],
        ),
    )
    text = render_record(case)
    assert "LOTS REQUIRING A PHYSICAL CHECK" in text
    assert "Family Shelf D1" in text
    assert "Go and read" in text


def test_no_number_in_the_record_was_typed_by_hand(pantry, by_number):
    case = build_case(
        pantry,
        Interruption(
            recall=by_number["F-0617-2025"],
            exposures=[exposure(pantry, pantry.lot("INT-2026-0718-02"), by_number["F-0617-2025"])],
        ),
    )
    lot = pantry.lot("INT-2026-0718-02")
    assert case["pull"]["units"] == lot.units_on_hand
    assert case["pull"]["cases"] == lot.cases_on_hand
    assert case["notify"]["units"] == sum(
        d.units for d in pantry.distributions_of(lot.lot_id)
    )
    assert case["notify"]["households"] == len(
        {d.household_id for d in pantry.distributions_of(lot.lot_id)}
    )


def test_the_readme_disclosure_is_actually_in_the_intake_log():
    """The honesty claim has to live with the data, not only in the README."""
    import json
    from pathlib import Path

    payload = json.loads((Path(__file__).parent.parent / "data" / "pantry.json").read_text())
    assert "representative" in payload["note"]
    assert "live" in payload["note"]
    assert payload["provenance"]["INT-2026-0718-02"].startswith("lot code S88N D1M")
