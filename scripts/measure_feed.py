"""Every number in the README, recomputed from the captured feed.

Run against the corpus in data/ (offline, no credentials) or with --live to
refetch from openFDA first and measure what is there today.

    .venv/bin/python scripts/measure_feed.py
    .venv/bin/python scripts/measure_feed.py --live
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

from agent.feeds.openfda import fetch, load_captured

CORPUS = Path(__file__).parent.parent / "data" / "fda_food_enforcement_2025_2026.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="refetch from openFDA first")
    args = parser.parse_args()

    if args.live:
        recalls = fetch(date(2025, 1, 1))
        source = "live openFDA, fetched now"
    else:
        recalls = load_captured(str(CORPUS))
        meta = json.loads(CORPUS.read_text())
        source = f"{CORPUS.name}, captured {meta['captured_at']}, openFDA last_updated {meta['last_updated']}"

    n = len(recalls)
    lots = sum(1 for r in recalls if r.identifiers.lot_codes)
    upcs = sum(1 for r in recalls if r.identifiers.upcs)
    bestby = sum(1 for r in recalls if r.identifiers.best_by_dates or r.identifiers.best_by_before)
    allcodes = sum(1 for r in recalls if r.identifiers.all_codes)
    nothing = sum(1 for r in recalls if not r.identifiers.checkable and not r.identifiers.all_codes)
    date_only = sum(
        1
        for r in recalls
        if (r.identifiers.best_by_dates or r.identifiers.best_by_before) and not r.identifiers.lot_codes
    )
    states = sum(1 for r in recalls if r.identifiers.states)
    nationwide = sum(1 for r in recalls if r.identifiers.nationwide)
    no_geo = n - states - nationwide
    ongoing = [r for r in recalls if r.open]
    class_i = sum(1 for r in recalls if r.class_i)

    def pct(k: int) -> str:
        return f"{k:>6,} / {n:,}   {k / n:5.1%}"

    print(f"source: {source}")
    print(f"food enforcement reports: {n:,}")
    print()
    print("what the notice publishes to identify affected units")
    print(f"  lot or batch code       {pct(lots)}")
    print(f"  UPC                     {pct(upcs)}")
    print(f"  printed best-by date    {pct(bestby)}")
    print(f"  best-by but no lot code {pct(date_only)}")
    print(f"  'all units' language    {pct(allcodes)}")
    print(f"  nothing checkable       {pct(nothing)}")
    print()
    print("where the notice says the product went")
    print(f"  named states            {pct(states)}")
    print(f"  nationwide              {pct(nationwide)}")
    print(f"  neither stated          {pct(no_geo)}")
    print()
    print("status and severity")
    print(f"  Ongoing                 {pct(len(ongoing))}")
    print(f"  Class I                 {pct(class_i)}")
    print()
    print(f"  distinct recalling firms: {len({r.firm for r in recalls}):,}")
    print(f"  reports per week over the window: {n / ((max(r.report_date for r in recalls) - min(r.report_date for r in recalls)).days / 7):.1f}")
    print(f"  first report {min(r.report_date for r in recalls)}, last {max(r.report_date for r in recalls)}")
    print()
    top = Counter(r.classification for r in recalls).most_common()
    print("  classification:", ", ".join(f"{k} {v:,}" for k, v in top))


if __name__ == "__main__":
    main()
