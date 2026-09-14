"""Telling the households that already took the food home. Really sending it.

This is the only irreversible thing Best By does. A pull list can be wrong and
cost a pantry some cans. A notification that is wrong reaches a family and tells
them food they have already eaten was recalled, and there is no unsend. So the
gate on this path is not politeness, it is the design: `NotifyVeto` in
`agent/bestby_agent.py` cancels the tool outright unless the engine returned a
confirmed lot match with a distribution record behind it, and the Strands
`HumanInTheLoop` intervention means the coordinator approves before anything
leaves the building.

SES is in sandbox on this account, which means a message is only accepted for a
recipient that is a verified identity or sits under a verified domain. That is a
real constraint and it is handled by routing, never by pretending: every send
records `intended` (the household's own address as the pantry has it) alongside
`to` (where SES actually accepted it) and a `mode`. A coordinator reading this
case in six months must be able to tell a notice that reached a family from one
that reached a mailbox simulator, and a system that blurs those two has told the
pantry it discharged a duty it did not discharge.

    direct      accepted for the household's own address
    simulator   accepted by SES's mailbox simulator because sandbox would have
                rejected the real address; the household was NOT reached
    failed      SES refused it, with the reason kept
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

SENDER = os.environ.get("BESTBY_SENDER", "bestby@getava.xyz")
SIMULATOR = "success@simulator.amazonses.com"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _verified_identities(client: Any) -> set[str]:
    out: set[str] = set()
    token = None
    while True:
        kwargs = {"PageSize": 100}
        if token:
            kwargs["NextToken"] = token
        resp = client.list_email_identities(**kwargs)
        for identity in resp.get("EmailIdentities", []):
            out.add(identity["IdentityName"].lower())
        token = resp.get("NextToken")
        if not token:
            return out


def _deliverable(address: str, identities: set[str]) -> bool:
    """True when SES in sandbox will accept this recipient.

    A verified domain identity covers every address under it, which is why the
    domain is checked separately from the exact address.
    """
    address = address.lower()
    if address in identities:
        return True
    domain = address.split("@")[-1]
    return domain in identities


def send_notice(
    *,
    to: str | None,
    subject: str,
    body: str,
    household_id: str,
    case_id: str,
) -> dict:
    """Send one household notice through SES and report where it really went."""
    client = boto3.client("sesv2")
    intended = (to or "").strip()
    if not intended or not _EMAIL.match(intended):
        return {
            "household_id": household_id,
            "case_id": case_id,
            "intended": intended or None,
            "to": None,
            "mode": "failed",
            "error": "no usable email address on the household record",
            "at": _now(),
        }

    identities = _verified_identities(client)
    if _deliverable(intended, identities):
        recipient, mode = intended, "direct"
    else:
        recipient, mode = SIMULATOR, "simulator"

    try:
        resp = client.send_email(
            FromEmailAddress=SENDER,
            Destination={"ToAddresses": [recipient]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                }
            },
        )
    except ClientError as exc:
        return {
            "household_id": household_id,
            "case_id": case_id,
            "intended": intended,
            "to": recipient,
            "mode": "failed",
            "error": exc.response.get("Error", {}).get("Message", str(exc)),
            "at": _now(),
        }

    return {
        "household_id": household_id,
        "case_id": case_id,
        "intended": intended,
        "to": recipient,
        "mode": mode,
        "message_id": resp["MessageId"],
        "at": _now(),
    }


def notify_all(case: dict, notice_text: str) -> dict:
    """Send the approved notice to every household on this case.

    Returns a delivery record, not a boolean. Partial success is the normal
    outcome for a pantry whose roster has three households with no email, and
    reporting it as failure would be as wrong as reporting it as success.
    """
    recipients = case.get("notify", {}).get("recipients", [])
    recall = case.get("recall", {})
    subject = f"Food recall notice from {case.get('pantry_name', 'your food pantry')}"
    sent: list[dict] = []
    for row in recipients:
        personalised = notice_text.replace("{household}", row.get("name", "Neighbor")).replace(
            "{units}", str(row.get("units", 0))
        )
        sent.append(
            send_notice(
                to=row.get("contact_email"),
                subject=subject,
                body=personalised,
                household_id=row.get("household_id", ""),
                case_id=case.get("case_id", ""),
            )
        )
    modes = [s["mode"] for s in sent]
    return {
        "at": _now(),
        "recall_number": recall.get("recall_number"),
        "attempted": len(sent),
        "direct": modes.count("direct"),
        "simulator": modes.count("simulator"),
        "failed": modes.count("failed"),
        "sender": SENDER,
        "messages": sent,
    }
