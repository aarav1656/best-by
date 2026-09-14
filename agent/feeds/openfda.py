"""openFDA food enforcement reports, read as shelf instructions.

An enforcement report is the FDA's record of why it classified a firm's recall.
It was not written for a food pantry, and the gap between what it says and what
a pantry has to do is the whole of this module's work.

The one field that matters is `code_info`. It is free text, it is whatever the
firm's regulatory affairs person typed, and it carries the only thing that
distinguishes an affected case from an identical unaffected one. Measured over
all 2,547 food enforcement reports with a report_date in 2025 or 2026, captured
2026-09-14 (`python scripts/measure_feed.py`, which reruns the measurement
against the captured corpus and prints every number in this docstring and in
the README):

    lot or batch code parsed       829 / 2,547   32.5%
    UPC parsed                     953 / 2,547   37.4%
    printed best-by date parsed    808 / 2,547   31.7%
    best-by date but no lot code   519 / 2,547   20.4%
    "all units" language           191 / 2,547    7.5%
    nothing checkable at all       688 / 2,547   27.0%

Two numbers there decide the architecture. Only 32.5% of notices publish a lot
code, so a system that matches on lot codes alone is silent about two thirds of
the feed. And 20.4% publish a printed best-by date and no lot code at all,
which is why this module extracts dates as a first-class identifier rather than
as a fallback, and why the product is called Best By.

The same distribution is why the lot code is captured at intake instead of
hunted for when a notice lands. Going to look at recall time means walking the
shelves with a printout, and a quarter of those walks end at a case whose code
cannot be compared to anything the notice published. If the case was
photographed when it came off the truck, the comparison is an exact string
match against all 614 open recalls at once.

Three extractors here, and only the first is shared with the general-purpose
recall matcher this was adapted from:

`_extract_lot_codes` pulls the stamped batch string out of an anchored region
after "Lot No." or "Batch", with a fallback for the comma-less runs firms
paste out of a spreadsheet ("LLA617603   30 JUN 2027 LLA617703   30 JUN 2027").

`_extract_best_by` is new and is the reason this product is called Best By. For
a large share of food recalls the firm never published a lot code at all, only
the printed date: "BEST BY 23/MAR/2027 GY", "Best Before/By Date: 8/7/2026 -
8/12/2026", "USE BY: 10/19/2027". A pantry's intake log records the printed
best-by date on every case because that is what rotation is scheduled on, so a
date the notice publishes is a date the pantry can already check. It handles
ranges ("between 5/21/26 - 6/9/26"), open-ended bounds ("all best by dates on
or before July 10, 2027"), and the four date orders firms actually use.

`_extract_scope` reads the sentences that mean "every unit, whatever the code":
"All codes recalled", "all prior batches/dates", "all lots". Without it a
recall of an entire product line produces NEEDS_EVIDENCE on every case in the
pantry, which is exactly the alert-fatigue failure the product exists to end.

`_extract_states` parses distribution_pattern into USPS state codes. It is the
cheapest true negative available: a notice that shipped only to CA and NV is
not a shelf-walk for a pantry in Ohio, and saying so costs one set
intersection. Nationwide is detected separately and always matches.

There is no per-record public detail URL in this API. The FDA's own recall
lookup page (accessdata.fda.gov/scripts/ires) returns 503 when probed, so no
URL is synthesised: a link that does not resolve is worse on a pull list than
no link.

FSIS, which publishes meat and poultry recalls, is the obvious second adapter
and would need no engine changes. Its API is blocked by a WAF from the network
this was built on, so it is not wired up rather than half wired up.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import httpx

from agent.feeds.base import LotIdentifiers, Recall

BASE = "https://api.fda.gov"
FOOD_ENFORCEMENT = "/food/enforcement.json"
OPENFDA_MAX_LIMIT = 1000

_GROUPS = (
    r"\d{12,13}(?!\d)"
    r"|\d{6}\s\d{6,7}(?!\d)"
    r"|\d{1,2}\s\d{4,6}\s\d{4,6}(?:\s\d{1,2})?(?!\d)"
)
# "UPC (5 oz.): 123..." puts a unit size in parens between the label and the
# digits. The plain pattern's [^0-9(] gap cannot cross that, and widening the
# gap to allow it starts swallowing unrelated numbers earlier in the sentence,
# so the parenthetical case gets its own pattern.
_UPC_PLAIN = re.compile(r"\bUPC\b[^0-9(]{0,15}(" + _GROUPS + ")", re.I)
_UPC_PARENTHETICAL = re.compile(r"\bUPC\b\s*\([^)]{0,25}\)\s*[^0-9]{0,15}(" + _GROUPS + ")", re.I)

_LOT_ANCHOR = re.compile(
    r"\b(?:lot(?:s)?|batch(?:es)?)\b\.?\s*(?:no\.?s?|numbers?|codes?|#s?|number)?\s*[:\s]{0,3}", re.I
)
# 28 of the 2,547 captured reports say in words that there is no lot code:
# "No identifying lot numbers. Product Code: 654203.", "product does not have
# lot or best by code", "Delta Fresh does NOT assign lot information to the
# shipping container." Without this guard the anchor fires on the word "lot"
# inside the denial and the extractor reports the next number it finds as the
# recalled lot, which is the single worst thing this file could do: it invents
# an identifier the firm explicitly said does not exist, and `_lot_code_check`
# treats an identifier as decisive in both directions.
_LOT_NEGATION = re.compile(r"\b(?:no|none|not|without|lack\w*|absent|don'?t|does\s*n[o']t)\b", re.I)
_NEGATION_WINDOW = 40
_LOT_STOP = re.compile(
    r"\b(?:exp\b|expir\w*|best\s*by|best\s*before|best\s*if|bud\b|discard|use\s*by"
    r"|sell\s*by|udi|gtin|ref\b|ndc|item)\b",
    re.I,
)
_ENUM_PREFIX = re.compile(r"^\(?[a-zA-Z0-9]{1,3}[.)]\s*")
_LOT_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 \-]{0,28}[A-Za-z0-9]|[A-Za-z0-9]")
_MONTH_WORD = re.compile(r"^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*$", re.I)
_EMBEDDED_CODE = re.compile(r"\b[A-Za-z]{1,4}\d{4,10}[A-Za-z]{0,3}\b|\b\d{5,10}\b")


def _extract_upcs(text: str) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for rx in (_UPC_PLAIN, _UPC_PARENTHETICAL):
        for m in rx.finditer(text):
            digits = re.sub(r"\s", "", m.group(1))
            if len(digits) in (12, 13) and digits not in seen:
                seen.add(digits)
                out.append(digits)
    return tuple(out)


def _clean_lot_token(raw: str) -> str | None:
    raw = _ENUM_PREFIX.sub("", raw.strip().strip(".")).strip()
    if not raw or "/" in raw or len(raw) > 30:
        return None
    if not _LOT_TOKEN.fullmatch(raw):
        return None
    if not any(c.isdigit() for c in raw):
        return None
    return re.sub(r"\s+", " ", raw)


def _scan_embedded_codes(segment: str) -> list[str]:
    out = []
    for m in _EMBEDDED_CODE.finditer(segment):
        token = m.group(0)
        if _MONTH_WORD.match(token):
            continue
        out.append(token)
    return out


def _extract_lot_codes(text: str, *, cap: int = 40) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for anchor in _LOT_ANCHOR.finditer(text):
        preceding = text[max(0, anchor.start() - _NEGATION_WINDOW) : anchor.start()]
        if _LOT_NEGATION.search(preceding):
            continue
        start = anchor.end()
        stop = _LOT_STOP.search(text, start, start + 400)
        end = stop.start() if stop else min(len(text), start + 250)
        region = text[start:end]
        segments = re.split(r"[,;]", region)
        found_in_region = False
        for raw in segments:
            token = _clean_lot_token(raw)
            if not token:
                continue
            found_in_region = True
            if token.lower() in seen:
                continue
            seen.add(token.lower())
            out.append(token)
            if len(out) >= cap:
                return tuple(out)
        # A single unpunctuated segment ("code date code date ...") never cleans
        # as one token. Only then fall back to scanning it for code-shaped
        # substrings, so an ordinary comma list is never counted through both
        # paths.
        if not found_in_region and len(segments) == 1:
            for token in _scan_embedded_codes(segments[0]):
                if token.lower() in seen:
                    continue
                seen.add(token.lower())
                out.append(token)
                if len(out) >= cap:
                    return tuple(out)
    return tuple(out)


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# The four date shapes that actually appear in code_info, in the order they
# must be tried. Numeric-first would swallow "23/MAR/2027" as a failed
# day/month/year, so the two alphabetic-month forms are tried first.
_DATE_DMY_WORD = re.compile(
    r"\b(\d{1,2})[\s/\-]([A-Za-z]{3,9})[\s/\-.,]{1,3}(\d{2,4})\b"
)
_DATE_MDY_WORD = re.compile(
    r"\b([A-Za-z]{3,9})[\s/\-.]{1,3}(\d{1,2})(?:st|nd|rd|th)?[\s,/\-]{1,3}(\d{2,4})\b"
)
_DATE_NUMERIC = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")

_BEST_BY_ANCHOR = re.compile(
    r"\b(?:best\s*(?:by|before|if\s*used?\s*by)(?:\s*/\s*by)?|use\s*by|used?\s*by"
    r"|sell\s*by|fresh\s*thru|exp(?:iration|ires?|\.)?|expiry|enjoy\s*by)\b"
    r"(?:\s*date[s]?)?\s*[:\-]?\s*",
    re.I,
)
# "on or before July 10, 2027" / "and all prior batches/dates" turn a single
# printed date into an open-ended upper bound rather than one date to equal.
_BEFORE_BOUND = re.compile(r"\b(?:on\s+or\s+)?(?:before|prior\s+to|thru|through|up\s+to)\b", re.I)
_ALL_CODES = re.compile(
    r"\ball\s+(?:codes?|lots?|lot\s+codes?|batch(?:es)?|units?|product(?:ion)?\s+(?:codes?|dates?)"
    r"|prior\s+batch(?:es)?|best\s*by\s+dates?|expiration\s+dates?|dates?)\b"
    r"|\b(?:all\s+)?prior\s+batch(?:es)?\s*/\s*dates?\b"
    r"|\bevery\s+lot\b|\bno\s+lot\s+(?:number|code)s?\b|\bregardless\s+of\s+(?:lot|code|date)\b",
    re.I,
)


def _year(raw: str) -> int:
    y = int(raw)
    return y if y >= 100 else 2000 + y


def _safe_date(y: int, m: int, d: int) -> date | None:
    if not (1 <= m <= 12 and 1 <= d <= 31 and 2000 <= y <= 2099):
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _parse_dates(segment: str) -> list[date]:
    """Every date in one anchored region, in the order it was printed."""
    found: list[tuple[int, date]] = []
    consumed: list[tuple[int, int]] = []

    def overlaps(a: int, b: int) -> bool:
        return any(not (b <= s or a >= e) for s, e in consumed)

    for m in _DATE_DMY_WORD.finditer(segment):
        month = _MONTHS.get(m.group(2)[:3].lower())
        if month is None:
            continue
        d = _safe_date(_year(m.group(3)), month, int(m.group(1)))
        if d:
            found.append((m.start(), d))
            consumed.append((m.start(), m.end()))
    for m in _DATE_MDY_WORD.finditer(segment):
        if overlaps(m.start(), m.end()):
            continue
        month = _MONTHS.get(m.group(1)[:3].lower())
        if month is None:
            continue
        d = _safe_date(_year(m.group(3)), month, int(m.group(2)))
        if d:
            found.append((m.start(), d))
            consumed.append((m.start(), m.end()))
    for m in _DATE_NUMERIC.finditer(segment):
        if overlaps(m.start(), m.end()):
            continue
        # US food labels print month first. A day-first reading is only taken
        # when the month-first reading is impossible (13/01/2027).
        a, b = int(m.group(1)), int(m.group(2))
        d = _safe_date(_year(m.group(3)), a, b) or _safe_date(_year(m.group(3)), b, a)
        if d:
            found.append((m.start(), d))
            consumed.append((m.start(), m.end()))
    found.sort()
    return [d for _, d in found]


def _extract_best_by(text: str, *, cap: int = 60) -> tuple[tuple[date, ...], date | None]:
    """Printed best-by dates, plus an upper bound when the notice states one.

    Returns (exact dates, before_bound). A notice saying "all best by dates on
    or before July 10, 2027" yields no exact dates and a bound of 2027-07-10,
    because matching a single case against that date alone would miss every
    earlier case the recall also covers.
    """
    exact: list[date] = []
    seen: set[date] = set()
    bound: date | None = None
    for anchor in _BEST_BY_ANCHOR.finditer(text):
        start = anchor.end()
        region = text[start : start + 300]
        # A lot-code anchor after the dates ends this region: "Best By 6/1/26
        # Lot 4471" describes two different things.
        lot_stop = _LOT_ANCHOR.search(region)
        if lot_stop:
            region = region[: lot_stop.start()]
        dates = _parse_dates(region)
        if not dates:
            continue
        # "on or before" may sit just before the anchor ("all best by dates on
        # or before July 10 2027" anchors on "best by"), so look both sides.
        context = text[max(0, anchor.start() - 60) : start + 40]
        if _BEFORE_BOUND.search(context):
            candidate = max(dates)
            bound = candidate if bound is None else max(bound, candidate)
            continue
        for d in dates:
            if d in seen:
                continue
            seen.add(d)
            exact.append(d)
            if len(exact) >= cap:
                return tuple(exact), bound
    return tuple(exact), bound


def _extract_scope(text: str) -> bool:
    return bool(_ALL_CODES.search(text))


_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR",
}
_STATE_TOKEN = re.compile(r"\b([A-Z]{2})\b")
_NATIONWIDE = re.compile(r"\bnation[\s-]?wide\b|\bthroughout\s+the\s+(?:united\s+states|us)\b|\ball\s+50\s+states\b", re.I)
_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def _extract_states(pattern: str) -> tuple[tuple[str, ...], bool]:
    if not pattern:
        return (), False
    if _NATIONWIDE.search(pattern):
        return (), True
    codes = {c for c in _STATE_TOKEN.findall(pattern) if c in _STATES}
    lowered = pattern.lower()
    for name, code in _STATE_NAMES.items():
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            codes.add(code)
    return tuple(sorted(codes)), False


def _parse_yyyymmdd(s: str) -> date | None:
    s = (s or "").strip()
    if not re.fullmatch(r"\d{8}", s):
        return None
    return _safe_date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def extract_identifiers(payload: dict[str, Any]) -> LotIdentifiers:
    code_info = f"{payload.get('code_info') or ''} {payload.get('more_code_info') or ''}".strip()
    description = payload.get("product_description") or ""
    # A retail UPC is often quoted in product_description while code_info on
    # the same record carries only batch and date codes. Lot codes do not show
    # that split, so lot extraction stays scoped to code_info.
    upcs = _extract_upcs(code_info) or _extract_upcs(description)
    best_by, before = _extract_best_by(code_info)
    states, nationwide = _extract_states(payload.get("distribution_pattern") or "")
    return LotIdentifiers(
        upcs=upcs,
        lot_codes=_extract_lot_codes(code_info),
        best_by_dates=best_by,
        best_by_before=before,
        all_codes=_extract_scope(code_info),
        states=states,
        nationwide=nationwide,
    )


def parse_recall(payload: dict[str, Any]) -> Recall:
    event_id = str(payload.get("event_id") or "")
    recall_number = str(payload.get("recall_number") or "").strip()
    if not recall_number:
        # One report in the captured corpus carries no recall_number at all.
        # A case cannot be keyed or cited without an identifier, so this falls
        # back to the FDA's own event_id with a prefix that makes the
        # substitution obvious on a compliance record. It is not invented; it
        # is the other identifier the same record already publishes.
        recall_number = f"EVENT-{event_id}" if event_id else ""
    report = _parse_yyyymmdd(payload.get("report_date", "")) or date.today()
    initiated = _parse_yyyymmdd(payload.get("recall_initiation_date", "")) or report
    firm = (payload.get("recalling_firm") or "").strip()
    location = ", ".join(
        p for p in (payload.get("city"), payload.get("state")) if p and p != "N/A"
    )
    return Recall(
        source="openFDA",
        recall_id=event_id or recall_number,
        recall_number=recall_number,
        recall_date=initiated,
        report_date=report,
        status=(payload.get("status") or "").strip(),
        classification=(payload.get("classification") or "").strip(),
        title=(payload.get("product_description") or "").strip(),
        reason=(payload.get("reason_for_recall") or "").strip(),
        firm=firm,
        firm_location=location,
        distribution_pattern=(payload.get("distribution_pattern") or "").strip(),
        quantity=(payload.get("product_quantity") or "").strip() or None,
        identifiers=extract_identifiers(payload),
    )


def fetch(since: date, *, limit: int = 1000, timeout: float = 60.0) -> list[Recall]:
    """Every food enforcement report with a report_date on or after `since`.

    openFDA paginates with skip/limit and refuses a page size above 1000, so
    this walks pages until meta.results.total is exhausted. report_date, not
    recall_initiation_date, because a pantry learns about a recall when the FDA
    publishes it, and firms sometimes initiate months before classification.
    """
    page_limit = min(limit, OPENFDA_MAX_LIMIT)
    search = f"report_date:[{since.strftime('%Y%m%d')} TO 99991231]"
    recalls: list[Recall] = []
    skip = 0
    total: int | None = None
    while total is None or skip < total:
        resp = httpx.get(
            f"{BASE}{FOOD_ENFORCEMENT}",
            params={"search": search, "limit": page_limit, "skip": skip},
            timeout=timeout,
        )
        if resp.status_code == 404:
            # openFDA returns 404 NOT_FOUND instead of an empty result set when
            # a search matches nothing.
            break
        resp.raise_for_status()
        body = resp.json()
        total = body["meta"]["results"]["total"]
        recalls.extend(parse_recall(item) for item in body.get("results", []))
        skip += page_limit
    recalls.sort(key=lambda r: r.report_date, reverse=True)
    return recalls


def load_captured(path: str) -> list[Recall]:
    """Parse a captured openFDA response from disk, same shape as `fetch`."""
    import json
    from pathlib import Path

    body = json.loads(Path(path).read_text())
    recalls = [parse_recall(item) for item in body.get("results", [])]
    recalls.sort(key=lambda r: r.report_date, reverse=True)
    return recalls
