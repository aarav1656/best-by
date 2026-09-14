"""The shape every recall source is reduced to before the engine sees it.

Best By reads one source today, openFDA's food enforcement reports. The shape
is separate from the adapter anyway, because the engine must never learn which
regulator it is reading: FSIS publishes meat and poultry recalls in the same
shelf-pull shape and is the obvious second adapter, and nothing in
`agent/engine/` would have to change to take it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class LotIdentifiers:
    """What the enforcement report says identifies the affected units.

    A recall notice is a description of a batch, not of a product. These four
    fields are the whole of what openFDA gives you to decide whether a case on
    a pantry shelf is in that batch:

        upcs            retail barcodes, when the firm quoted one
        lot_codes       the stamped batch or lot string
        best_by_dates   the printed date, which for a lot of food recalls is
                        the only identifier the firm published at all
        all_codes       the firm recalled every unit of this product, so the
                        UPC on its own is decisive and no lot code is needed

    `states` comes from distribution_pattern and is the cheapest true negative
    in the system: a pantry in Ohio does not need to walk its shelves for a
    recall the firm shipped only to California.
    """

    upcs: tuple[str, ...] = ()
    lot_codes: tuple[str, ...] = ()
    best_by_dates: tuple[date, ...] = ()
    best_by_before: date | None = None
    all_codes: bool = False
    states: tuple[str, ...] = ()
    nationwide: bool = False

    @property
    def checkable(self) -> bool:
        """True when the notice published something a shelf can be checked against."""
        return bool(self.upcs or self.lot_codes or self.best_by_dates or self.best_by_before)

    @property
    def checkable_beyond_upc(self) -> bool:
        """True when the notice narrows the recall to some units of a barcode.

        A notice that publishes only a UPC recalls every unit carrying it. A
        notice that also publishes lot codes or printed dates recalls a subset,
        so a UPC match alone cannot settle a case against it.
        """
        return bool(self.lot_codes or self.best_by_dates or self.best_by_before)


@dataclass(frozen=True)
class Recall:
    source: str
    recall_id: str
    recall_number: str
    recall_date: date
    report_date: date
    status: str
    classification: str
    title: str
    reason: str
    firm: str
    firm_location: str
    distribution_pattern: str
    quantity: str | None
    identifiers: LotIdentifiers = field(default_factory=LotIdentifiers)

    @property
    def open(self) -> bool:
        return self.status == "Ongoing"

    @property
    def class_i(self) -> bool:
        """Class I: reasonable probability of serious health consequence or death."""
        return self.classification.strip().upper() in {"CLASS I", "CLASS 1"}
