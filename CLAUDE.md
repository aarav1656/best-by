# Best By

An agent that watches the FDA food recall feed against what a food pantry
actually has on its shelves, and who already took some home. Submitted to the
AWS Agents for Humans hackathon, Good Neighbor Agents track, deadline
2026-09-14 17:00 PT.

## The one idea

Read the lot code at intake, from a photograph, not at recall time.

Measured across all 2,547 food enforcement reports with a 2025 or 2026 report
date (`python scripts/measure_feed.py`): 32.5% publish a lot code, 37.4% a UPC,
31.7% a printed best-by date, and 27.0% publish nothing a shelf can be checked
against. So hunting for a code when a notice lands fails a quarter of the time.
Capturing it when the case comes off the truck turns every later comparison into
an exact string match against all 614 open recalls at once.

## The rules that must never be broken

**The model reads identity. The model never decides eligibility.**

- `agent/engine/verdict.py` decides, from stamped codes, printed dates and
  distribution states. No prompt reaches it. MATCH / NEEDS_EVIDENCE / NO_MATCH.
- `judge_identity` accepts the model's read and returns the computed verdict.
- An `IdentityAssertion` may only replace the soft lexical `product_identity`
  check. It can never touch the UPC, the lot code, the best-by date or the
  distribution state.

**Pull and notify are separate obligations.** Units on the shelf and units
already in a household's cupboard are different numbers with different
recipients. Never let one stand in for the other, and never report a single
"affected units" total.

**`notify_households` is the only irreversible tool.**

- `NotifyVeto` in `agent/bestby_agent.py` is a Strands `BeforeToolCallEvent`
  hook that cancels it unless the ledger holds a MATCH verdict, a distribution
  record, and a drafted notice.
- `approval_gate` is a `HumanInTheLoop` with
  `allowed_tools=["*", "!notify_households"]`.
- `tests/test_veto.py::test_the_hook_cancels_a_dispatch_that_is_actually_attempted`
  proves it by attempting a real dispatch against a recording sender. Break the
  hook and it goes red. Never weaken that test to make a change pass.

**Never invent an identifier.** `_extract_lot_codes` has a negation guard
because 28 reports say in words that there is no lot code, and without it the
extractor reported the next number it found. `agent/label.py` reports
`unreadable` rather than guessing. A wrong lot code destroys good food and mails
families who were never at risk.

## Environment

- Python 3.12 venv at `.venv`. Run from the repo root.
- `.env` holds `ANTHROPIC_API_KEY`. Never print it, never commit it.
- AWS: profile `palimpsest`, region us-east-1. Always
  `export AWS_PROFILE=palimpsest AWS_DEFAULT_REGION=us-east-1` and
  `unset AWS_BEARER_TOKEN_BEDROCK` first.
- **Bedrock and AgentCore do not work on this account.** It is an AWS India
  (AISPL) account. Every model in every region returns `Operation not allowed`,
  for the administrator too. Do not spend time on it. Strands runs against the
  Anthropic API directly while Lambda, EventBridge, DynamoDB, S3 and SES carry
  the rest. Lambda memory is capped at 512MB here.

## Live resources

- DynamoDB `bestby-cases` (PK pantry_id, SK case_id), `bestby-recalls`
- S3 `bestby-evidence-079415246611`
- Lambda `bestby-run`, IAM role `bestby-exec`, schedule `bestby-daily`
- SES sender `bestby@getava.xyz`, sandbox, domain `getava.xyz` verified

## Data honesty

`data/pantry.json` is a representative pantry's intake log and its `note` field
says so. The recalls it is checked against are always live. The lot codes on
lots inside an open recall are the real published codes, and the engine finds
them by matching; never add a field that flags which lots are supposed to match.
Never hand-write a case into DynamoDB to make the console look better: cases come
from a real run or the console is showing fiction.

## House style

No em dashes. No decorative comments. Comments justify non-obvious decisions
only. Production code only: no mocks, no stubs, no placeholder data. Tests run
against real captured API responses in `data/`, never invented fixtures. Never
write a number that was not measured by a script in this repo.
