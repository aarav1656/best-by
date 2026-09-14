"""Reading the stamped code off a photograph of a case label, at intake.

This is the inversion the whole product rests on, so it is worth being precise
about what moved.

The obvious design reads a label when a recall lands. A notice arrives naming
lot S88N D1M, someone walks the aisles with a printout, finds the pallet,
crouches, reads the stamp. That works and it is what pantries do today, and it
fails for a reason that has nothing to do with diligence: measured over 2,547
live food enforcement reports, only 32.7% publish a lot code at all, so half
those walks end at a case whose code cannot be compared to anything, and the
coordinator has to decide whether to dump the pallet on a maybe.

Best By reads the label when the donation is booked in instead. A volunteer
already has the case in their hands, already has a phone, and photographing the
stamped panel costs them four seconds. The code becomes a string in a table
before anyone knows a recall is coming. Six weeks later the comparison is
`"s88nd1m" in {...}`, which is exact, instant, auditable, and runs against all
614 open recalls at once instead of the one notice someone happened to open.

The model's job here is transcription and nothing else. It never decides
whether a lot is recalled: `agent/engine/verdict.py` does that, from the string
this returns, and no prompt reaches it.

Three outcomes per field, because they are three different situations:

    read          the characters are legible and reported as printed
    not_present   the label is legible and this kind of code is not on it
    unreadable    blur, glare, distance, crop or darkness make the text
                  untrustworthy, so nothing is reported for it

Guessing a plausible-looking code is worse than reporting nothing. A wrong lot
code does not merely fail to help. It produces a confident false MATCH, and
downstream of that a coordinator destroys good food a pantry cannot replace and
tells fourteen families their groceries were recalled. It can equally produce a
false NO_MATCH, which leaves recalled food on a shelf with a clean audit trail
saying it was checked. Both are worse than "unreadable, photograph it again",
which costs one volunteer one minute while the case is still in their hands.
"""

from __future__ import annotations

import re
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field
from strands import Agent
from strands.models.anthropic import AnthropicModel

MODEL_ID = "claude-sonnet-4-5-20250929"

ReadStatus = Literal["read", "not_present", "unreadable"]

_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


class CodeField(BaseModel):
    """One kind of stamped code, and what the model actually saw."""

    status: ReadStatus = Field(
        description="'read' only if the characters are legible enough to type with "
        "confidence. 'not_present' if the label is legible but this code type is not "
        "on it. 'unreadable' if this code's location is visible but the text is too "
        "small, blurry, angled, dark, or obstructed to make out."
    )
    value: str | None = Field(
        default=None,
        description="The exact string as printed, including its own dashes, spaces "
        "and slashes. Only set when status is 'read'.",
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="0.0 unless status is 'read'."
    )
    region: str = Field(
        default="",
        description="Where on the packaging this is, or would be, in plain words: "
        "'ink-jetted on the bottom of the can', 'printed on the case end panel "
        "under the barcode'.",
    )
    note: str = Field(
        default="",
        description="Only when status is 'unreadable': what is wrong with the photo "
        "for this specific code and what a reshoot would need.",
    )


class LabelReading(BaseModel):
    """What one photograph of a food case or unit label actually shows."""

    image_legible: bool = Field(
        description="False only if the whole photograph is unusable for reading any "
        "text at all: extreme blur, near darkness, or the label entirely out of "
        "frame. A photo that is fine overall but has one small illegible code is "
        "still image_legible=true; only that one field is 'unreadable'."
    )
    reshoot_instruction: str = Field(
        default="",
        description="Set when image_legible is false: the concrete photo to take "
        "instead, e.g. 'hold the can bottom flat to the lens in daylight'.",
    )
    product_name: CodeField
    lot_code: CodeField
    best_by: CodeField
    upc: CodeField
    net_weight: CodeField
    other_codes: list[CodeField] = Field(
        default_factory=list,
        description="Any other stamped or printed code: an establishment number, a "
        "case item number, a julian pack date, a plant code.",
    )
    summary: str = Field(
        description="One plain sentence: what was actually found, or why nothing was."
    )


SYSTEM_PROMPT = """You are reading one photograph taken by a food pantry volunteer booking a donation onto the shelf. They are photographing the stamped code panel on a case or on a unit. What you transcribe is stored as that shelf lot's identity, and every future FDA recall this pantry receives will be checked against it by exact string comparison.

For every kind of code (product name, lot or batch code, best-by or use-by date, UPC, net weight, and anything else stamped or printed):

- Report status "read" only if you can see the actual characters clearly enough to type them with confidence. Transcribe exactly what is printed, including its own punctuation and spacing.
- Report status "not_present" if the packaging is legible overall but this kind of code genuinely is not printed anywhere visible in this photo.
- Report status "unreadable" if you can see roughly where the code is but the characters are too small, blurry, dark, cut off, or glare-obscured to actually read. Say what is wrong and what a reshoot needs.

Never invent or guess a code that only looks plausible. If you are not certain of every character, that field is "unreadable", not "read".

A wrong lot code here has two failure modes and both are serious. Too generous, and a later recall matches a batch this pantry never had: a coordinator destroys food that families need and sends recall notices to households who were never at risk. Too careless in the other direction, and a recalled batch sits on the shelf with an audit trail claiming it was checked. "Unreadable" costs a volunteer one more photograph while the case is still in their hands. Either wrong answer costs a great deal more.

On food packaging the lot code and the best-by date are very often ink-jetted together in one run, on a can bottom, a bag seal, or a case end panel, with no labels to tell you which is which. A typical stamp reads like "S88N BEST IF USED BY 1/17/28 D1M", where the manufacturer's lot identity is the alphanumeric fragments and the date is the date. When the fragments are split around the date like that, report the lot_code as the fragments joined in printed order with a single space between them, and report the date separately in best_by exactly as printed.

Report best_by exactly as it is printed on the package. Do not reformat it, do not expand a two-digit year, and do not convert between day-first and month-first. Transcription only.

A UPC-A barcode prints exactly 12 digits beneath its bars, grouped 1-5-5-1; EAN-13 prints 13, grouped 1-6-6. Count the digits against the bar groups before reporting a UPC as "read". If the printed digits are too small at this image's resolution to place each digit against its bar, report "unreadable" and say the photo needs to be retaken closer, not a best guess. The grouping spaces exist for a human eye and are not part of the code: report the upc value as one contiguous run of digits.

Set image_legible to false only when the whole photograph cannot be used to read any text. A clean marketing shot of a product with no code panel in frame is image_legible=true with every code field "not_present": nothing is wrong with the photo, there is simply no stamp in it."""


def _sniff_format(data: bytes) -> str:
    for magic, fmt in _MAGIC:
        if data.startswith(magic):
            return fmt
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    raise ValueError("Unrecognized image data: not a png, jpeg, gif or webp.")


def _load_image(source: str | Path | bytes) -> tuple[bytes, str]:
    if isinstance(source, bytes):
        data = source
    elif isinstance(source, (str, Path)):
        data = Path(source).read_bytes()
    else:
        raise TypeError(f"read_label expects a path or bytes, got {type(source)!r}")
    return data, _sniff_format(data)


def _pixel_size(data: bytes, fmt: str) -> tuple[int, int] | None:
    """Width and height straight from the file header, no decode needed.

    Told to the model as text alongside the image, because a thumbnail is
    exactly the case where it should downgrade a stamp to "unreadable" rather
    than guess at characters too small to resolve.
    """
    if fmt == "png" and len(data) >= 24 and data[12:16] == b"IHDR":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if fmt == "jpeg":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height = int.from_bytes(data[i + 5 : i + 7], "big")
                width = int.from_bytes(data[i + 7 : i + 9], "big")
                return width, height
            i += 2 + seg_len
    return None


# A phone photo of a case panel is 3000px on the long edge and needs no help. A
# 400px image pulled off a supplier page has a stamp a handful of pixels tall,
# and the model will confidently misread it rather than say so. Interpolating up
# adds no information the photo never had, but it measurably changes whether the
# model reports "unreadable" instead of a wrong string at the same confidence.
_TARGET_LONG_EDGE = 1400
_MAX_UPSCALE = 6
# Anthropic's image input is capped at roughly 8000px per side and images above
# ~1568px on the long edge are downscaled server-side anyway, so a 5000px phone
# photo is bytes spent on nothing. Bounding it here keeps a large intake photo
# from failing the request outright.
_MAX_LONG_EDGE = 2200


def _normalize(data: bytes, fmt: str, size: tuple[int, int] | None) -> tuple[bytes, str]:
    if size is None:
        return data, fmt
    width, height = size
    long_edge = max(width, height)
    if not long_edge:
        return data, fmt
    if long_edge < _TARGET_LONG_EDGE:
        scale = min(_MAX_UPSCALE, _TARGET_LONG_EDGE / long_edge)
    elif long_edge > _MAX_LONG_EDGE:
        scale = _MAX_LONG_EDGE / long_edge
    else:
        return data, fmt
    with Image.open(BytesIO(data)) as im:
        resized = im.convert("RGB").resize(
            (max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS
        )
        buf = BytesIO()
        resized.save(buf, format="PNG")
        return buf.getvalue(), "png"


def read_label(
    image_path_or_bytes: str | Path | bytes,
    *,
    booking_in: str = "a donated case",
    model_id: str = MODEL_ID,
) -> LabelReading:
    """Transcribe every stamped code visible in one intake photograph.

    `booking_in` is what the volunteer says they are logging, e.g. "8 cases of
    Genova tuna from the Miami Valley pallet". It is context for the model, not
    an answer: every field is read regardless, because a photo taken to capture
    a lot code usually also shows the best-by date and sometimes the barcode,
    and all three are worth having before the recall arrives.
    """
    data, fmt = _load_image(image_path_or_bytes)
    size = _pixel_size(data, fmt)
    size_note = f"This photograph was captured at {size[0]}x{size[1]} pixels. " if size else ""
    data, fmt = _normalize(data, fmt, size)
    agent = Agent(
        model=AnthropicModel(model_id=model_id, max_tokens=2048),
        system_prompt=SYSTEM_PROMPT,
    )
    prompt = [
        {"image": {"format": fmt, "source": {"bytes": data}}},
        {
            "text": f"The volunteer is booking in: {booking_in}\n\n"
            f"{size_note}Read this intake photograph and report every code you can "
            "find on it, honestly, field by field."
        },
    ]
    result = agent(prompt, structured_output_model=LabelReading)
    if result.structured_output is None:
        raise RuntimeError("Model did not return a structured label reading.")
    return result.structured_output


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_PRINTED_NUMERIC = re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})")
_PRINTED_DMY = re.compile(r"(\d{1,2})[\s/\-]([A-Za-z]{3,9})[\s/\-.,]{1,3}(\d{2,4})")
_PRINTED_MDY = re.compile(r"([A-Za-z]{3,9})[\s/\-.]{1,3}(\d{1,2})(?:st|nd|rd|th)?[\s,/\-]{1,3}(\d{2,4})")


def parse_printed_date(printed: str) -> date | None:
    """Turn a transcribed best-by stamp into a date, or refuse.

    The model is told to transcribe, never to reformat, so the parsing lives
    here in code where it is testable and where an ambiguous stamp returns None
    instead of a confident guess. US food labels print month first; a day-first
    reading is taken only when the month-first reading is impossible.
    """
    text = (printed or "").strip()
    if not text:
        return None

    def build(y: int, m: int, d: int) -> date | None:
        y = y if y >= 100 else 2000 + y
        if not (1 <= m <= 12 and 1 <= d <= 31 and 2000 <= y <= 2099):
            return None
        try:
            return date(y, m, d)
        except ValueError:
            return None

    m = _PRINTED_DMY.search(text)
    if m and _MONTHS.get(m.group(2)[:3].lower()):
        return build(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
    m = _PRINTED_MDY.search(text)
    if m and _MONTHS.get(m.group(1)[:3].lower()):
        return build(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    m = _PRINTED_NUMERIC.search(text)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return build(c, a, b) or build(c, b, a)
    return None


def apply_reading(lot: dict, reading: LabelReading) -> dict:
    """Fold whatever was legibly read onto a copy of an intake record.

    Only fields with status "read" are applied. "not_present" and "unreadable"
    leave the existing value untouched rather than overwriting it with nothing,
    and `lot_code_source` records which of the three happened, so a pantry
    auditing the record later can tell a code that was photographed from a code
    that was typed off a packing slip from a code nobody ever captured.

    The whole reading is attached as `label_reading`, because the value that
    made it into the record is not the same as the evidence for it.
    """
    enriched = dict(lot)
    if reading.lot_code.status == "read" and reading.lot_code.value:
        enriched["lot_code"] = reading.lot_code.value.strip()
        enriched["lot_code_source"] = "label_photo"
    elif reading.lot_code.status == "unreadable":
        enriched.setdefault("lot_code", None)
        enriched["lot_code_source"] = "photo_unreadable"
    elif reading.lot_code.status == "not_present":
        enriched.setdefault("lot_code", None)
        enriched["lot_code_source"] = "no_lot_code_on_label"

    if reading.upc.status == "read" and reading.upc.value:
        enriched["upc"] = "".join(reading.upc.value.split())

    if reading.best_by.status == "read" and reading.best_by.value:
        parsed = parse_printed_date(reading.best_by.value)
        if parsed:
            enriched["best_by"] = parsed.isoformat()
        enriched["best_by_printed"] = reading.best_by.value.strip()

    enriched["label_reading"] = reading.model_dump(mode="json")
    return enriched
