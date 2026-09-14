"""The extractors, against the exact free text real firms wrote.

Each assertion names the recall it came from, so a failure can be checked
against the live API rather than against someone's memory of what the parser
used to do.
"""

from __future__ import annotations

from datetime import date

import pytest

from agent.feeds.openfda import (
    _extract_best_by,
    _extract_lot_codes,
    _extract_scope,
    _extract_states,
    _extract_upcs,
    extract_identifiers,
    parse_recall,
)


def test_lot_codes_from_a_comma_separated_list(by_number):
    """F-0610-2025, the Tri-Union tuna recall. Fifteen codes in one field."""
    ident = by_number["F-0610-2025"].identifiers
    assert "S94N 42K" in ident.lot_codes
    assert "S88ND1M" in ident.lot_codes
    assert len(ident.lot_codes) == 15


def test_the_same_stamped_code_appears_in_two_spacings(by_number):
    """The firm typed S94N 42K and S94N42K into one field. Both are the same can."""
    codes = by_number["F-0610-2025"].identifiers.lot_codes
    assert "S94N 42K" in codes
    assert "S94N42K" in codes


def test_a_single_lot_recall(by_number):
    """F-0617-2025 recalls exactly one batch, which is what makes it checkable."""
    assert by_number["F-0617-2025"].identifiers.lot_codes == ("S88N D1M",)


def test_best_by_from_a_slashed_alphabetic_month(by_number):
    """H-0835-2026 code_info is 'BEST BY 23/MAR/2027 GY' and nothing else."""
    ident = by_number["H-0835-2026"].identifiers
    assert ident.best_by_dates == (date(2027, 3, 23),)
    assert ident.lot_codes == ()


def test_best_by_survives_a_semicolon_list(by_number):
    """H-0394-2025 lists eleven 'Best By: MM/DD/YYYY code' pairs in one run."""
    ident = by_number["H-0394-2025"].identifiers
    assert date(2027, 6, 24) in ident.best_by_dates
    assert date(2027, 7, 5) in ident.best_by_dates


def test_an_open_ended_bound_is_not_an_exact_date(by_number):
    """H-1234-2026: 'all best by dates on or before July 10, 2027'.

    Recorded as a bound, not as one date. Reading it as an exact date would
    clear every case stamped earlier than the bound, which is every case the
    recall actually covers.
    """
    ident = by_number["H-1234-2026"].identifiers
    assert ident.best_by_before == date(2027, 7, 10)
    assert ident.best_by_dates == ()


def test_all_units_language_is_detected(by_number):
    assert by_number["H-1234-2026"].identifiers.all_codes is True


def test_a_lot_scoped_recall_is_not_read_as_all_units(by_number):
    assert by_number["F-0617-2025"].identifiers.all_codes is False


def test_upc_from_the_product_description_when_code_info_has_none(by_number):
    """H-0835-2026 quotes the barcode in the description, not in code_info."""
    assert by_number["H-0835-2026"].identifiers.upcs == ("085239270240",)


def test_a_parenthetical_unit_size_does_not_break_the_upc(by_number):
    """F-0801-2025: 'UPC (5 oz.): 609465693477 UPC (10 0z.): 642147152459'."""
    upcs = by_number["F-0801-2025"].identifiers.upcs
    assert "609465693477" in upcs
    assert "642147152459" in upcs


def test_states_parsed_from_a_bare_list(by_number):
    assert by_number["H-0890-2026"].identifiers.states == ("KS", "MN", "NY", "WI")
    assert by_number["H-0890-2026"].identifiers.nationwide is False


def test_nationwide_is_detected_not_guessed(by_number):
    ident = by_number["F-0610-2025"].identifiers
    assert ident.nationwide is True
    assert ident.states == ()


def test_state_names_spelled_out_are_read(by_number):
    """H-1222-2026 distribution_pattern is the word Nevada, not the code NV."""
    assert "NV" in by_number["H-1222-2026"].identifiers.states


def test_a_date_is_never_mistaken_for_a_lot_code():
    """'30 JUN 2027' inside an unpunctuated run must not become a lot code."""
    text = "Batch codes: LLA617603   30 JUN 2027 LLA617703   30 JUN 2027"
    codes = _extract_lot_codes(text)
    assert "LLA617603" in codes
    assert "LLA617703" in codes
    assert not any("JUN" in c.upper() for c in codes)


def test_a_lot_anchor_after_a_date_ends_the_date_region():
    """'Best By 6/1/26 Lot 4471' is two facts, not one date list."""
    dates, bound = _extract_best_by("Best By: 6/1/2026 Lot No. 4471")
    assert dates == (date(2026, 6, 1),)
    assert bound is None


def test_an_impossible_month_first_date_falls_back_to_day_first():
    dates, _ = _extract_best_by("Best By: 13/06/2027")
    assert dates == (date(2027, 6, 13),)


def test_two_digit_years_expand_into_this_century():
    dates, _ = _extract_best_by("BEST BY: 30 DEC 26")
    assert dates == (date(2026, 12, 30),)


def test_nothing_is_invented_from_an_empty_field():
    ident = extract_identifiers({"code_info": "", "product_description": "", "distribution_pattern": ""})
    assert ident.checkable is False
    assert ident.all_codes is False
    assert ident.states == ()
    assert ident.nationwide is False


def test_no_identifying_lot_numbers_stays_empty(by_number):
    """F-0700-2025 says so in words. An extractor that finds a code here lies."""
    assert by_number["F-0700-2025"].identifiers.lot_codes == ()


def test_checkable_beyond_upc_distinguishes_a_whole_product_recall(by_number):
    """A UPC-only notice recalls every unit. A UPC-plus-lot notice recalls some."""
    assert by_number["H-0835-2026"].identifiers.checkable_beyond_upc is True
    assert by_number["F-0617-2025"].identifiers.checkable_beyond_upc is True


def test_report_date_not_initiation_date_drives_ordering(by_number):
    recall = by_number["F-0610-2025"]
    assert recall.report_date == date(2025, 3, 19)
    assert recall.status == "Ongoing"
    assert recall.class_i is False


def test_class_one_is_recognised(by_number):
    assert by_number["H-0835-2026"].class_i is True


def test_the_captured_corpus_is_the_real_shape(recalls):
    assert len(recalls) == 2547
    assert {r.source for r in recalls} == {"openFDA"}
    assert all(r.recall_number for r in recalls)
