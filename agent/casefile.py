"""One recall, turned into the one thing a coordinator has to read.

An `Interruption` is the engine's view: lots, verdicts, checks. A case is the
coordinator's view, and the difference is not formatting. The engine thinks in
pairs. The person thinks in errands: which bay to walk to, how many cases come
off the shelf, which families get a phone call tonight. This module does that
translation once, and the console, the compliance record and the notice draft
all read the same object, so nothing in the product can show a number the case
file does not contain.

Every check that produced the decision is carried through verbatim. A pull list
a coordinator cannot audit is a pull list a coordinator eventually ignores, and
"lot S88N D1M is among the 1 recalled codes (S88N D1M)" is the sentence that
makes taking 84 cans off a shelf defensible to the food bank that sent them.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from agent.engine.sweep import Exposure, Interruption, Sweep
from agent.shelf import Pantry
from agent.store import case_id


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _lot_row(exp: Exposure) -> dict:
    lot = exp.lot
    return {
        "lot_id": lot.lot_id,
        "product_description": lot.product_description,
        "brand": lot.brand,
        "storage_location": lot.storage_location,
        "received_on": lot.received_on.isoformat(),
        "donor": lot.donor,
        "units_on_hand": exp.units_on_hand,
        "cases_on_hand": exp.cases_on_hand,
        "units_per_case": lot.units_per_case,
        "units_distributed": exp.units_distributed,
        "upc": lot.upc,
        "lot_code": lot.lot_code,
        "lot_code_source": lot.lot_code_source,
        "best_by": lot.best_by.isoformat() if lot.best_by else None,
        "label_photo": lot.label_photo,
        "outcome": exp.verdict.outcome.value,
        "decided_by": exp.verdict.decided_by,
        "checks": [asdict(c) for c in exp.verdict.checks],
        "missing": list(exp.verdict.missing),
        "evidence_id": exp.verdict.evidence_id,
    }


def build_case(pantry: Pantry, interruption: Interruption) -> dict:
    recall = interruption.recall
    cid = case_id(pantry.pantry_id, recall.recall_number)

    pull_lots = [_lot_row(e) for e in interruption.matched if e.pull]
    evidence_lots = [_lot_row(e) for e in interruption.unresolved]

    # Who got what, collapsed per household. A family that took cans on three
    # different Saturdays gets one notice naming the total, not three notices.
    recipients: dict[str, dict] = {}
    for exp in interruption.matched:
        if not exp.notify:
            continue
        for dist in exp.distributions:
            household = pantry.household(dist.household_id)
            if household is None:
                continue
            row = recipients.setdefault(
                household.household_id,
                {
                    "household_id": household.household_id,
                    "name": household.name,
                    "contact_email": household.contact_email,
                    "contact_phone": household.contact_phone,
                    "language": household.language,
                    "household_size": household.household_size,
                    "children_under_5": household.children_under_5,
                    "units": 0,
                    "lots": [],
                    "last_given_on": dist.given_on.isoformat(),
                },
            )
            row["units"] += dist.units
            if exp.lot.lot_id not in row["lots"]:
                row["lots"].append(exp.lot.lot_id)
            row["last_given_on"] = max(row["last_given_on"], dist.given_on.isoformat())

    ordered = sorted(
        recipients.values(),
        key=lambda r: (-r["children_under_5"], -r["units"], r["household_id"]),
    )

    status = "awaiting_approval" if interruption.matched else "needs_evidence"
    return {
        "pantry_id": pantry.pantry_id,
        "pantry_name": pantry.name,
        "pantry_location": f"{pantry.city}, {pantry.state}",
        "case_id": cid,
        "status": status,
        "urgency": interruption.urgency,
        "headline": interruption.headline(),
        "recall": {
            "source": recall.source,
            "recall_number": recall.recall_number,
            "classification": recall.classification,
            "recall_status": recall.status,
            "title": recall.title,
            "reason": recall.reason,
            "firm": recall.firm,
            "firm_location": recall.firm_location,
            "report_date": recall.report_date.isoformat(),
            "recall_date": recall.recall_date.isoformat(),
            "distribution_pattern": recall.distribution_pattern,
            "quantity": recall.quantity,
            "class_i": recall.class_i,
        },
        "pull": {
            "cases": interruption.cases_to_pull,
            "units": interruption.units_to_pull,
            "locations": sorted({l["storage_location"] for l in pull_lots}),
            "lots": pull_lots,
        },
        "notify": {
            "households": len(ordered),
            "units": sum(r["units"] for r in ordered),
            "children_under_5": sum(1 for r in ordered if r["children_under_5"] > 0),
            "recipients": ordered,
        },
        "needs_evidence": evidence_lots,
        "notice_text": None,
        "delivery": None,
        "evidence_uri": None,
        "timeline": [
            {
                "at": now(),
                "event": "opened",
                "detail": (
                    f"{len(interruption.matched)} lot(s) matched, "
                    f"{len(interruption.unresolved)} need evidence, "
                    f"{len(interruption.cleared)} cleared"
                ),
            }
        ],
        "created_at": now(),
        "updated_at": now(),
    }


def build_cases(pantry: Pantry, result: Sweep) -> list[dict]:
    return [build_case(pantry, i) for i in result.actionable]


def sweep_summary(pantry: Pantry, result: Sweep) -> dict:
    """The one row a pantry's board sees: what was checked and what came of it."""
    actionable = result.actionable
    return {
        "pantry_id": pantry.pantry_id,
        "pantry_name": pantry.name,
        "ran_at": result.ran_at,
        "lots_checked": result.lots_checked,
        "units_on_shelf": pantry.units_on_shelf,
        "units_distributed": pantry.units_distributed,
        "households_served": len(pantry.households),
        "recalls_considered": result.recalls_considered,
        "pairs_evaluated": result.pairs_evaluated,
        "interruptions": len(actionable),
        "cases_to_pull": sum(i.cases_to_pull for i in actionable),
        "units_to_pull": sum(i.units_to_pull for i in actionable),
        "households_to_notify": len({h.household_id for i in actionable for h in i.households_to_notify}),
        "lots_needing_evidence": sum(len(i.unresolved) for i in actionable),
        "lots_cleared_by_code": len(result.cleared),
        "quiet": result.quiet,
    }
