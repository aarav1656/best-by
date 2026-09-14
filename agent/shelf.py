"""What a food pantry actually has, in the shape a pantry actually records it.

A pantry does not have purchase history. It has an intake log. Cases come off a
truck in a donation, a volunteer writes down what arrived and how much, the
cases go on a shelf, and over the following weeks they go out to households a
few units at a time. Three tables, and the third one is the one nobody models:

    ShelfLot        one intake: a product, a quantity, a shelf, and the codes
                    a volunteer photographed off the case when it arrived
    Distribution    units from a lot that went home with a household
    Household       who that was and how to reach them

`units_on_hand` and the sum of that lot's distributions are different numbers
and produce different obligations. Product still on the shelf is a pull: a
volunteer walks to a bay, takes cases off, and the pantry destroys them. Product
already distributed cannot be pulled, only disclosed, and that is the half of a
recall that actually reaches a person who might eat it. Conflating the two is
how a pantry ends up with a tidy disposal record and twelve households who were
never told.

The codes on a `ShelfLot` are captured at intake, not looked up at recall time.
That is the inversion the whole product rests on. `lot_code` is read off a
photograph of the case label by `agent/label.py` when the donation is booked in,
which costs a volunteer one photo and turns every future recall comparison into
an exact string match. Looking for the same code six weeks later, against a
notice that has already landed, means walking the shelves with a printout.
`lot_code_source` records which of those happened for every lot, because a
pantry auditing its own record months later needs to know whether a code was
read off the case or typed from a packing slip.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent.parent / "data"
PANTRY_FILE = DATA / "pantry.json"


@dataclass(frozen=True)
class Household:
    household_id: str
    name: str
    contact_email: str | None
    contact_phone: str | None
    language: str
    household_size: int
    children_under_5: int

    @property
    def high_risk(self) -> bool:
        """Listeria and botulism notices name under-5s as the population at risk."""
        return self.children_under_5 > 0


@dataclass(frozen=True)
class Distribution:
    distribution_id: str
    lot_id: str
    household_id: str
    units: int
    given_on: date


@dataclass(frozen=True)
class ShelfLot:
    lot_id: str
    product_description: str
    brand: str
    received_on: date
    donor: str
    units_received: int
    units_on_hand: int
    units_per_case: int
    storage_location: str
    upc: str | None = None
    lot_code: str | None = None
    lot_code_source: str = "unrecorded"
    best_by: date | None = None
    label_photo: str | None = None
    label_reading: dict[str, Any] | None = None

    @property
    def cases_on_hand(self) -> int:
        """Whole cases a volunteer would physically carry, rounded up."""
        if self.units_per_case <= 0:
            return 0
        return -(-self.units_on_hand // self.units_per_case)

    @property
    def identified(self) -> bool:
        return bool(self.lot_code or self.upc or self.best_by)

    def to_wire(self) -> dict[str, Any]:
        return {
            "lot_id": self.lot_id,
            "product_description": self.product_description,
            "brand": self.brand,
            "received_on": self.received_on.isoformat(),
            "donor": self.donor,
            "units_received": self.units_received,
            "units_on_hand": self.units_on_hand,
            "units_per_case": self.units_per_case,
            "storage_location": self.storage_location,
            "upc": self.upc,
            "lot_code": self.lot_code,
            "lot_code_source": self.lot_code_source,
            "best_by": self.best_by.isoformat() if self.best_by else None,
            "label_photo": self.label_photo,
        }


@dataclass(frozen=True)
class Pantry:
    pantry_id: str
    name: str
    city: str
    state: str
    coordinator_email: str
    lots: tuple[ShelfLot, ...] = ()
    distributions: tuple[Distribution, ...] = ()
    households: tuple[Household, ...] = ()
    note: str = ""

    def lot(self, lot_id: str) -> ShelfLot | None:
        return next((l for l in self.lots if l.lot_id == lot_id), None)

    def household(self, household_id: str) -> Household | None:
        return next((h for h in self.households if h.household_id == household_id), None)

    def distributions_of(self, lot_id: str) -> tuple[Distribution, ...]:
        return tuple(d for d in self.distributions if d.lot_id == lot_id)

    @property
    def units_on_shelf(self) -> int:
        return sum(l.units_on_hand for l in self.lots)

    @property
    def units_distributed(self) -> int:
        return sum(d.units for d in self.distributions)

    @property
    def lots_with_lot_code(self) -> int:
        return sum(1 for l in self.lots if l.lot_code)


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def load_pantry(path: str | Path | None = None) -> Pantry:
    payload = json.loads(Path(path or PANTRY_FILE).read_text())
    lots = tuple(
        ShelfLot(
            lot_id=l["lot_id"],
            product_description=l["product_description"],
            brand=l["brand"],
            received_on=date.fromisoformat(l["received_on"]),
            donor=l["donor"],
            units_received=l["units_received"],
            units_on_hand=l["units_on_hand"],
            units_per_case=l["units_per_case"],
            storage_location=l["storage_location"],
            upc=l.get("upc"),
            lot_code=l.get("lot_code"),
            lot_code_source=l.get("lot_code_source", "unrecorded"),
            best_by=_date(l.get("best_by")),
            label_photo=l.get("label_photo"),
            label_reading=l.get("label_reading"),
        )
        for l in payload["lots"]
    )
    distributions = tuple(
        Distribution(
            distribution_id=d["distribution_id"],
            lot_id=d["lot_id"],
            household_id=d["household_id"],
            units=d["units"],
            given_on=date.fromisoformat(d["given_on"]),
        )
        for d in payload["distributions"]
    )
    households = tuple(
        Household(
            household_id=h["household_id"],
            name=h["name"],
            contact_email=h.get("contact_email"),
            contact_phone=h.get("contact_phone"),
            language=h.get("language", "en"),
            household_size=h["household_size"],
            children_under_5=h.get("children_under_5", 0),
        )
        for h in payload["households"]
    )
    return Pantry(
        pantry_id=payload["pantry_id"],
        name=payload["name"],
        city=payload["city"],
        state=payload["state"],
        coordinator_email=payload["coordinator_email"],
        lots=lots,
        distributions=distributions,
        households=households,
        note=payload.get("note", ""),
    )
