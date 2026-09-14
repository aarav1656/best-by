"""The document a health inspector asks for, written while the work happens.

A pantry answers to two people about a recall. Its regional food bank wants to
know the affected product left the distribution chain. A county health inspector
wants to know the pantry knew, acted, and can prove both. Neither accepts "we
got the email".

What they actually ask for is narrower and more awkward than a pull list:

  - which lots were destroyed, how many units, on what date, by whom
  - what the pantry did about product that had already gone out the door
  - and the one nobody keeps: which lots of the same recalled product were
    checked and found NOT to be in the affected batch, because that is the
    only thing that justifies having continued to hand them out

Best By writes that record as the pass runs, to S3, one object per case, and
keeps the verdict checks verbatim inside it. A disposal log that says "84 units
destroyed" is an assertion. One that says "84 units destroyed, lot S88N D1M,
matched against openFDA F-0617-2025 which lists exactly one recalled lot, code
read from the case photograph at intake on 2026-07-18" is evidence.

Text, not JSON, as the primary artifact. The person who needs this prints it
and puts it in a binder.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import boto3

BUCKET = "bestby-evidence-079415246611"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _wrap(text: str, width: int = 78, indent: str = "") -> list[str]:
    words, line, out = text.split(), "", []
    for word in words:
        if len(line) + len(word) + 1 > width:
            out.append(indent + line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(indent + line)
    return out


def render_record(case: dict, cleared: list[dict] | None = None) -> str:
    """The printable compliance record for one recall at one pantry."""
    recall = case["recall"]
    pull = case.get("pull", {})
    notify = case.get("notify", {})
    delivery = case.get("delivery") or {}
    lines: list[str] = []

    lines.append("FOOD RECALL ACTION RECORD")
    lines.append("=" * 78)
    lines.append(f"Pantry            {case.get('pantry_name')} ({case.get('pantry_location')})")
    lines.append(f"Case              {case.get('case_id')}")
    lines.append(f"Record written    {_now()}")
    lines.append("")
    lines.append("NOTICE")
    lines.append("-" * 78)
    lines.append(f"Source            {recall.get('source')} food enforcement report")
    lines.append(f"Recall number     {recall.get('recall_number')}")
    lines.append(f"Classification    {recall.get('classification')} ({recall.get('recall_status')})")
    lines.append(f"Recalling firm    {recall.get('firm')} {recall.get('firm_location')}")
    lines.append(f"FDA report date   {recall.get('report_date')}")
    lines.append(f"Firm initiated    {recall.get('recall_date')}")
    lines.append("Product")
    lines.extend(_wrap(recall.get("title", ""), indent="  "))
    lines.append("Reason for recall")
    lines.extend(_wrap(recall.get("reason", ""), indent="  "))
    lines.append("Distribution")
    lines.extend(_wrap(recall.get("distribution_pattern", "not stated"), indent="  "))
    lines.append("")

    lines.append("PRODUCT REMOVED FROM DISTRIBUTION")
    lines.append("-" * 78)
    lots = pull.get("lots", [])
    if not lots:
        lines.append("  None. No affected units remained on the shelf at the time of this pass.")
    for lot in lots:
        lines.append(f"  Intake lot      {lot['lot_id']}")
        lines.append(f"  Product         {lot['product_description']}")
        lines.append(f"  Received        {lot['received_on']} from {lot['donor']}")
        lines.append(f"  Location        {lot['storage_location']}")
        lines.append(
            f"  Quantity        {lot['units_on_hand']} units "
            f"({lot['cases_on_hand']} case(s) of {lot['units_per_case']})"
        )
        lines.append(f"  Lot code        {lot.get('lot_code') or 'not recorded'} "
                     f"(source: {lot.get('lot_code_source')})")
        lines.append(f"  Best by         {lot.get('best_by') or 'not recorded'}")
        lines.append(f"  Decided by      {lot.get('decided_by')}")
        lines.append("  Checks that produced this decision:")
        for check in lot.get("checks", []):
            mark = "pass" if check.get("passed") else "FAIL"
            lines.extend(_wrap(f"{mark} {check.get('name')}: {check.get('detail')}", indent="    "))
        lines.append("")

    lines.append("PRODUCT ALREADY DISTRIBUTED TO HOUSEHOLDS")
    lines.append("-" * 78)
    recipients = notify.get("recipients", [])
    if not recipients:
        lines.append("  None. No affected units had been distributed at the time of this pass.")
    else:
        lines.append(
            f"  {notify.get('units')} units across {len(recipients)} household(s). "
            f"{notify.get('children_under_5', 0)} of those households include a child under five."
        )
        lines.append("")
        lines.append(f"  {'Household':<12} {'Units':>6}  {'Last given':<12} {'Under 5':>7}  Notified")
        for row in recipients:
            record = next(
                (m for m in delivery.get("messages", []) if m.get("household_id") == row["household_id"]),
                None,
            )
            state = "not yet"
            if record:
                state = f"{record['mode']} {record.get('message_id', record.get('error', ''))[:24]}"
            lines.append(
                f"  {row['household_id']:<12} {row['units']:>6}  {row['last_given_on']:<12} "
                f"{row['children_under_5']:>7}  {state}"
            )
    lines.append("")

    evidence = case.get("needs_evidence", [])
    if evidence:
        lines.append("LOTS REQUIRING A PHYSICAL CHECK")
        lines.append("-" * 78)
        for lot in evidence:
            lines.append(f"  {lot['lot_id']}  {lot['product_description']}")
            lines.append(f"    Location      {lot['storage_location']}, {lot['units_on_hand']} units")
            for missing in lot.get("missing", []):
                lines.extend(_wrap(f"Go and read: {missing}", indent="    "))
        lines.append("")

    if cleared:
        lines.append("LOTS CHECKED AND FOUND NOT AFFECTED")
        lines.append("-" * 78)
        lines.append("  These stayed in distribution. This is the record that justifies that.")
        for row in cleared:
            lines.append(f"  {row['lot_id']}  {row['product_description']}")
            lines.extend(_wrap(row["reason"], indent="    "))
        lines.append("")

    lines.append("ACTIONS TAKEN")
    lines.append("-" * 78)
    for entry in case.get("timeline", []):
        lines.append(f"  {entry.get('at')}  {entry.get('event')}")
        lines.extend(_wrap(entry.get("detail", ""), indent="    "))
    lines.append("")
    lines.append("=" * 78)
    lines.append(
        "Produced by Best By. Every value above was read from the openFDA food "
        "enforcement API or from this pantry's own intake log. No figure here was "
        "entered by hand."
    )
    return "\n".join(lines)


def put_record(case: dict, cleared: list[dict] | None = None, *, bucket: str = BUCKET) -> dict:
    """Write the record to S3 as printable text plus the structured case beside it."""
    s3 = boto3.client("s3")
    pantry = case["pantry_id"]
    number = case["recall"]["recall_number"]
    day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    base = f"{pantry}/{day}/{number}"
    text = render_record(case, cleared)
    s3.put_object(
        Bucket=bucket,
        Key=f"{base}.txt",
        Body=text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )
    s3.put_object(
        Bucket=bucket,
        Key=f"{base}.json",
        Body=json.dumps({"case": case, "cleared": cleared or []}, indent=2, default=str).encode(),
        ContentType="application/json",
    )
    return {
        "uri": f"s3://{bucket}/{base}.txt",
        "json_uri": f"s3://{bucket}/{base}.json",
        "bytes": len(text.encode("utf-8")),
        "at": _now(),
    }
