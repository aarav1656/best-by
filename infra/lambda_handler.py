"""The unattended pass. EventBridge Scheduler calls this every morning.

Nobody is watching when this runs, which changes two things.

The approval gate does not block. `notify_households` is still vetoed and still
requires the coordinator, but with no terminal attached the gate records the
case as waiting and the pass moves on to the next notice rather than hanging
until the timeout. Approvals come back through the console, are handed to the
next invocation in `approvals`, and the same gate lets them through then.

Everything else is the same code a person runs locally. The Lambda does not
have a reduced pass or a simplified matcher: it imports `agent.engine.sweep`
and `agent.bestby_agent` exactly as `agent/run.py` does, because a scheduled
run that behaves differently from the one you tested is not a scheduled run,
it is a second implementation.

Events this accepts:

    {}                              the daily pass, deterministic only
    {"agent": true}                 the daily pass with the model reading identity
    {"approve": ["<case_id>", ...]} approvals the coordinator gave in the console
    {"action": "cases"}             read back the current queue, for the console
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from agent.casefile import build_cases, sweep_summary
from agent.compliance import put_record
from agent.engine.sweep import sweep
from agent.feeds.openfda import fetch
from agent.shelf import load_pantry
from agent.store import CaseStore, RecallStore

SINCE = date(2025, 1, 1)
PANTRY_FILE = os.path.join(os.path.dirname(__file__), "data", "pantry.json")


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


def _recall_rows(recalls) -> list[dict]:
    """What the pass saw, so tomorrow's pass knows which notices are new."""
    return [
        {
            "source": r.source,
            "recall_number": r.recall_number,
            "report_date": r.report_date.isoformat(),
            "classification": r.classification,
            "status": r.status,
            "firm": r.firm,
            "title": r.title[:900],
            "lot_codes": list(r.identifiers.lot_codes[:20]),
            "upcs": list(r.identifiers.upcs[:10]),
            "best_by_dates": [d.isoformat() for d in r.identifiers.best_by_dates[:20]],
            "all_codes": r.identifiers.all_codes,
            "nationwide": r.identifiers.nationwide,
            "states": list(r.identifiers.states),
            "first_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        for r in recalls
        if r.open and r.recall_number
    ]


def handler(event, context):
    event = event or {}
    pantry = load_pantry(PANTRY_FILE)

    if event.get("action") == "cases":
        return {
            "pantry_id": pantry.pantry_id,
            "cases": CaseStore().list_cases(pantry.pantry_id),
        }

    started = datetime.now(timezone.utc)
    recalls = fetch(SINCE)
    result = sweep(pantry, recalls, ran_at=started.isoformat(timespec="seconds"))
    summary = sweep_summary(pantry, result)
    summary["source"] = "live openFDA"

    recorded = RecallStore().record(_recall_rows(recalls))
    summary["open_recalls_recorded"] = recorded

    approvals = set(event.get("approve") or [])
    store = CaseStore()
    cleared = _cleared_rows(result)

    if event.get("agent"):
        from agent.bestby_agent import DynamoSink, build_agent

        agent, ledger, events = build_agent(
            pantry, recalls, sink=DynamoSink(), approvals=approvals
        )
        affected = sorted(
            {e.lot.lot_id for i in result.interruptions for e in i.exposures}
        )
        agent(
            "Run today's pass. The deterministic matcher already narrowed the shelf to "
            f"these lots, which have at least one open notice worth reading: "
            f"{', '.join(affected)}. Work through them one at a time."
        )
        summary["agent_events"] = len(events)
        summary["cases_opened"] = len(ledger.cases)
        summary["awaiting_approval"] = sorted(ledger.pending_approval)
    else:
        cases = build_cases(pantry, result)
        for case in cases:
            number = case["recall"]["recall_number"]
            written = put_record(case, [c for c in cleared if c["recall_number"] == number])
            case["evidence_uri"] = written["uri"]
            store.put_case(case)
        summary["cases_opened"] = len(cases)
        summary["evidence"] = [c["evidence_uri"] for c in cases]

    summary["seconds"] = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
    print(json.dumps(summary, default=str), flush=True)
    return summary
