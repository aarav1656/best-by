"""Durable case state, over DynamoDB. The only module that talks to it.

    bestby-cases    PK pantry_id (S)  SK case_id (S)
    bestby-recalls  PK source (S)     SK recall_number (S)

Both PAY_PER_REQUEST. Plain JSON-shaped dicts go in and come out; no boto3
type (Decimal, set) leaks past this boundary.

A case is one recall against one pantry, not one lot against one recall. That
is the same grouping `Interruption` uses, and it is the reason the coordinator
is interrupted once per notice however many cases are affected.

`put_case` is read-modify-write, not a ConditionExpression. A conditional put
only protects the first write, and every write after that has to merge: keep
created_at, append to the timeline, and let the caller's newer view replace
status and the pull and notify lists. Merging a list is not expressible as a
condition expression, so it happens in Python. The tradeoff is a lost-update
race between two writers on the same case_id, which is acceptable because a
case_id is only ever written by one scheduled pass for one pantry, never two
Lambda invocations at once. The field that must survive that merge is
`delivery`: it is the only durable proof that households were already
contacted, and losing it would let the next pass frighten the same fourteen
families a second time.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Any

import boto3

CASES_TABLE = "bestby-cases"
RECALLS_TABLE = "bestby-recalls"


def case_id(pantry_id: str, recall_number: str) -> str:
    """Same pantry, same notice, same case, however many times the pass runs."""
    return hashlib.sha256(f"{pantry_id}|{recall_number}".encode()).hexdigest()[:16]


def _to_dynamo(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_dynamo(asdict(value))
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_dynamo(v) for v in value]
    if value == "":
        # DynamoDB accepts empty strings in non-key attributes but they read
        # back as falsy nothing in the console; None is the honest value.
        return None
    return value


def _from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    return value


class CaseStore:
    def __init__(self, table_name: str = CASES_TABLE) -> None:
        self.table = boto3.resource("dynamodb").Table(table_name)

    def get_case(self, pantry_id: str, case_id_value: str) -> dict | None:
        resp = self.table.get_item(Key={"pantry_id": pantry_id, "case_id": case_id_value})
        item = resp.get("Item")
        return _from_dynamo(item) if item else None

    def put_case(self, case: dict) -> dict:
        previous = self.get_case(case["pantry_id"], case["case_id"])
        merged = dict(case)
        if previous:
            merged["created_at"] = previous.get("created_at", case.get("created_at"))
            merged["timeline"] = list(previous.get("timeline", [])) + list(case.get("timeline", []))
            for carried in ("delivery", "evidence_uri", "notice_text", "approved_by", "approved_at"):
                if previous.get(carried) and not case.get(carried):
                    merged[carried] = previous[carried]
        self.table.put_item(Item=_to_dynamo(merged))
        return merged

    def list_cases(self, pantry_id: str) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        resp = self.table.query(KeyConditionExpression=Key("pantry_id").eq(pantry_id))
        return [_from_dynamo(i) for i in resp.get("Items", [])]

    def set_status(self, pantry_id: str, case_id_value: str, status: str, event: dict) -> dict | None:
        case = self.get_case(pantry_id, case_id_value)
        if case is None:
            return None
        case["status"] = status
        case.setdefault("timeline", []).append(event)
        case["updated_at"] = event.get("at", case.get("updated_at"))
        self.table.put_item(Item=_to_dynamo(case))
        return case


class RecallStore:
    """Every notice the pass has seen, so a second pass knows what is new.

    A pantry does not want to be told about a recall it already handled. The
    case table answers that for recalls that matched something; this table
    answers it for the other 600, and it is what makes `--since-last-pass`
    honest rather than a date guess.
    """

    def __init__(self, table_name: str = RECALLS_TABLE) -> None:
        self.table = boto3.resource("dynamodb").Table(table_name)

    def seen(self, source: str, recall_number: str) -> bool:
        resp = self.table.get_item(Key={"source": source, "recall_number": recall_number})
        return "Item" in resp

    def record(self, recalls: list[dict]) -> int:
        written = 0
        with self.table.batch_writer(overwrite_by_pkeys=["source", "recall_number"]) as batch:
            for r in recalls:
                batch.put_item(Item=_to_dynamo(r))
                written += 1
        return written

    def known_numbers(self, source: str = "openFDA") -> set[str]:
        from boto3.dynamodb.conditions import Key

        out: set[str] = set()
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("source").eq(source),
            "ProjectionExpression": "recall_number",
        }
        while True:
            resp = self.table.query(**kwargs)
            out.update(i["recall_number"] for i in resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                return out
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
