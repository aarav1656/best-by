# Best By console

The coordinator-facing surface for Best By. Two routes and no third.

- `/` is the decision queue. One card per recall that reaches the pantry, sorted by urgency
  (`same_day`, `today`, `this_week`, `check`). Each card leads with the decision in plain words,
  then the product, then the hazard, and carries the two obligations as visually distinct blocks:
  PULL (still on the shelf) and NOTIFY (already in a kitchen). Healthy state is an empty queue and
  it is designed as the win, not as a blank.
- `/case/[caseId]` is the one case. The pull list with each lot's bay, cases, units, lot code and
  best-by, plus the verbatim `checks` array showing which comparison decided it. The notify list.
  The `needs_evidence` errands. The drafted notice, the S3 compliance record, and the timeline.

`DESIGN.md` is the design system and it is binding. Read it before touching a component.

## Where the numbers come from

Every figure on screen is one attribute of one DynamoDB row. Nothing is computed in the browser,
nothing is cached, nothing is interpolated. The table is `bestby-cases`, partition key `pantry_id`,
sort key `case_id`, read server-side in `lib/cases.ts` with `@aws-sdk/lib-dynamodb`. When the table
does not answer, the page says so and names the error rather than showing a stale or empty queue.

## Environment

Vercel reserves the `AWS_` prefix, so the credentials carry custom names and are passed explicitly
into the DynamoDB client.

| Variable | Meaning |
|---|---|
| `BESTBY_AWS_ACCESS_KEY_ID` | IAM access key with read on the cases table |
| `BESTBY_AWS_SECRET_ACCESS_KEY` | its secret |
| `BESTBY_AWS_REGION` | `us-east-1` |
| `BESTBY_PANTRY_ID` | optional, defaults to `riverbend-dayton` |
| `BESTBY_TABLE` | optional, defaults to `bestby-cases` |

Locally they live in `.env.local`, which is gitignored and never committed.

## Run

```
pnpm install
pnpm dev
pnpm build
```

## Deploy

```
vercel --prod
```
