"""The pass. One command, run by a person or by the schedule.

    .venv/bin/python -m agent.run                     offline corpus, no model, no AWS
    .venv/bin/python -m agent.run --live              refetch openFDA first
    .venv/bin/python -m agent.run --live --dynamo     persist cases to DynamoDB
    .venv/bin/python -m agent.run --live --dynamo --agent
                                                      let the model read identity too

The deterministic pass is the floor, not a fallback. It needs no API key and no
credentials, and a pantry whose key expires still gets its shelves checked
against every open recall on stamped codes alone. `--agent` layers the model's
identity read on top, which is what removes the notices that merely share words
with something on the shelf.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone

from agent.casefile import build_cases, sweep_summary
from agent.engine.sweep import sweep
from agent.feeds.openfda import fetch, load_captured
from agent.shelf import load_pantry

CORPUS = "data/fda_food_enforcement_2025_2026.json"
SINCE = date(2025, 1, 1)


def _cleared_rows(result) -> list[dict]:
    return [
        {
            "lot_id": e.lot.lot_id,
            "product_description": e.lot.product_description,
            "recall_number": e.recall.recall_number,
            "reason": str(e.verdict.failed[0]) if e.verdict.failed else "no identifier failed",
        }
        for e in result.cleared
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="fetch openFDA now instead of the captured corpus")
    parser.add_argument("--dynamo", action="store_true", help="write cases to DynamoDB")
    parser.add_argument("--s3", action="store_true", help="write compliance records to S3")
    parser.add_argument("--agent", action="store_true", help="let the model read identity")
    parser.add_argument("--pantry", default=None, help="path to a pantry intake log")
    parser.add_argument("--approve", action="append", default=[], help="case id the coordinator approved")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON only")
    args = parser.parse_args()

    pantry = load_pantry(args.pantry)
    recalls = fetch(SINCE) if args.live else load_captured(CORPUS)
    ran_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = sweep(pantry, recalls, ran_at=ran_at)
    summary = sweep_summary(pantry, result)
    summary["source"] = "live openFDA" if args.live else CORPUS

    if args.agent:
        from agent.bestby_agent import DynamoSink, FileSink, build_agent

        sink = DynamoSink() if args.dynamo else FileSink()
        agent, ledger, events = build_agent(
            pantry, recalls, sink=sink, approvals=set(args.approve)
        )
        lots = ", ".join(
            l.lot_id for l in pantry.lots if any(
                l.lot_id == e.lot.lot_id for i in result.interruptions for e in i.exposures
            )
        )
        agent(
            "Run today's pass. The deterministic matcher already narrowed the shelf to "
            f"these lots, which have at least one open notice worth reading: {lots}. "
            "Start with shelf_lots, then work through those lots one at a time. For every "
            "lot, call candidate_notices and judge_identity on each candidate. Most of "
            "them will not be the same food and saying so is the point."
        )
        summary["agent_events"] = len(events)
        summary["cases_opened"] = len(ledger.cases)
        summary["awaiting_approval"] = sorted(ledger.pending_approval)
        print(json.dumps(summary, indent=2))
        return

    cases = build_cases(pantry, result)
    cleared = _cleared_rows(result)

    if args.dynamo:
        from agent.store import CaseStore

        store = CaseStore()
        for case in cases:
            store.put_case(case)
        summary["persisted_to"] = "dynamodb://bestby-cases"

    if args.s3:
        from agent.compliance import put_record

        for case in cases:
            number = case["recall"]["recall_number"]
            written = put_record(case, [c for c in cleared if c["recall_number"] == number])
            case["evidence_uri"] = written["uri"]
        if args.dynamo:
            from agent.store import CaseStore

            store = CaseStore()
            for case in cases:
                store.put_case(case)
        summary["evidence"] = [c["evidence_uri"] for c in cases]

    if args.json:
        print(json.dumps({"summary": summary, "cases": cases}, indent=2, default=str))
        return

    print(f"{pantry.name}, {pantry.city} {pantry.state}")
    print(
        f"{summary['lots_checked']} intake lots, {summary['units_on_shelf']} units on the shelf, "
        f"{summary['units_distributed']} units already distributed to "
        f"{summary['households_served']} households"
    )
    print(
        f"checked against {summary['recalls_considered']} open FDA food recalls "
        f"({summary['pairs_evaluated']} pairs judged, source: {summary['source']})"
    )
    print()
    if result.quiet:
        print("Nothing to do. Every lot is either clear or was checked against its code.")
        return
    print(
        f"{summary['interruptions']} interruption(s): pull {summary['cases_to_pull']} case(s), "
        f"notify {summary['households_to_notify']} household(s), "
        f"check {summary['lots_needing_evidence']} lot(s) by hand"
    )
    print(f"{summary['lots_cleared_by_code']} lot(s) were compared against a recalled code and stay on the shelf")
    for case in cases:
        print()
        print(f"[{case['urgency']}] {case['recall']['recall_number']} {case['recall']['classification']}")
        print(f"  {case['headline']}")
        print(f"  {case['recall']['title'][:100]}")
        print(f"  hazard: {case['recall']['reason'][:110]}")
        for lot in case["pull"]["lots"]:
            print(
                f"    PULL   {lot['cases_on_hand']} case(s), {lot['units_on_hand']} units, "
                f"{lot['storage_location']}, lot {lot['lot_code'] or 'none'}  [{lot['decided_by']}]"
            )
        if case["notify"]["households"]:
            print(
                f"    NOTIFY {case['notify']['households']} household(s), "
                f"{case['notify']['units']} units, "
                f"{case['notify']['children_under_5']} with a child under five"
            )
        for lot in case["needs_evidence"]:
            print(f"    CHECK  {lot['lot_id']} in {lot['storage_location']}")
            for missing in lot["missing"]:
                print(f"           go and read: {missing}")


if __name__ == "__main__":
    main()
