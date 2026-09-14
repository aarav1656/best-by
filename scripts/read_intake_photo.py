"""The intake step, end to end, on one photograph.

This is what a volunteer's phone triggers when a donation is booked in. It reads
the stamped codes off the case photo, folds them onto the intake record, and
then checks that record against every open FDA food recall so the pantry learns
immediately if the pallet it just accepted is already recalled.

    .venv/bin/python scripts/read_intake_photo.py data/labels/genova-tuna-lotcode-bottom-F-0610-2025.jpg \
        --product "Genova Yellowfin Tuna in Extra Virgin Olive Oil and Sea Salt, 5 oz can" \
        --state OH

Needs ANTHROPIC_API_KEY. Everything after the read runs offline.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date

from agent.engine.sweep import candidates
from agent.engine.verdict import Outcome, decide
from agent.feeds.openfda import fetch, load_captured
from agent.label import apply_reading, parse_printed_date, read_label
from agent.shelf import ShelfLot

CORPUS = "data/fda_food_enforcement_2025_2026.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--product", required=True, help="what the volunteer says they are booking in")
    parser.add_argument("--brand", default="")
    parser.add_argument("--state", default="OH", help="the pantry's state, for the distribution check")
    parser.add_argument("--units", type=int, default=0)
    parser.add_argument("--per-case", type=int, default=1)
    parser.add_argument("--location", default="the intake bay")
    parser.add_argument("--live", action="store_true", help="fetch openFDA now")
    args = parser.parse_args()

    print(f"reading {args.image}")
    reading = read_label(args.image, booking_in=args.product)
    print()
    print(f"  image_legible  {reading.image_legible}")
    if not reading.image_legible:
        print(f"  reshoot        {reading.reshoot_instruction}")
        return
    for name in ("product_name", "lot_code", "best_by", "upc", "net_weight"):
        field = getattr(reading, name)
        line = f"  {name:<14} {field.status:<12}"
        if field.value:
            line += f" {field.value!r} (confidence {field.confidence:.2f})"
        print(line)
        if field.note:
            print(f"                 note: {field.note}")
    print(f"  summary        {reading.summary}")

    lot = ShelfLot(
        lot_id="INTAKE",
        product_description=args.product,
        brand=args.brand,
        received_on=date.today(),
        donor="intake",
        units_received=args.units,
        units_on_hand=args.units,
        units_per_case=args.per_case,
        storage_location=args.location,
    )
    enriched = apply_reading(lot.to_wire(), reading)
    lot = replace(
        lot,
        lot_code=enriched.get("lot_code"),
        lot_code_source=enriched.get("lot_code_source", "unrecorded"),
        upc=enriched.get("upc"),
        best_by=date.fromisoformat(enriched["best_by"]) if enriched.get("best_by") else None,
    )
    print()
    print("intake record after the read")
    print(f"  lot_code   {lot.lot_code!r} (source {lot.lot_code_source})")
    print(f"  best_by    {lot.best_by}")
    print(f"  upc        {lot.upc!r}")

    recalls = fetch(date(2025, 1, 1)) if args.live else load_captured(CORPUS)
    openrecalls = [r for r in recalls if r.open]
    print()
    print(f"checking against {len(openrecalls)} open FDA food recalls")
    hits = 0
    for recall in candidates(lot, openrecalls):
        verdict = decide(lot, recall, pantry_state=args.state)
        if verdict.outcome is Outcome.NO_MATCH:
            continue
        hits += 1
        print()
        print(f"  [{verdict.outcome.value}] {recall.recall_number} {recall.classification} ({recall.status})")
        print(f"    {recall.title[:110]}")
        print(f"    reason: {recall.reason[:110]}")
        print(f"    decided by {verdict.decided_by}")
        for check in verdict.checks:
            print(f"      {check}")
        for missing in verdict.missing:
            print(f"      go and read: {missing}")
    if not hits:
        print("  nothing open matches this case. Book it in.")


if __name__ == "__main__":
    main()
