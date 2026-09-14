# Best By console design system

Adapted from the Pullback console design system. Same discipline, different reader, different
obligations, different palette. Nothing here was copied without a reason that holds for a food
pantry.

## The one thing this interface has to do

Best By watches the FDA food enforcement feed against one pantry's intake log and interrupts the
coordinator once per recall, never once per item. The console is not where the work happens. The
work happens in Dry Goods A3 with a cart, and on the phone with the Farhat household. The console
is where a coordinator reads one card and decides two things:

**pull these N cases off the shelf, call these M households.**

So the interface is graded on its empty state first and its dense state second. An empty queue is
the product working. It reads as a shift that closed, not as an app with nothing in it.

The reader is a pantry coordinator with a volunteer shift starting in twenty minutes. The register
is a public notice: calm, exact, and physical. Not a dashboard, not an analytics product, not cute.
Half the hazard strings in the live corpus name an organism (`clostridium botulinum`,
`salmonella`, `listeria monocytogenes`) and the rest name an undeclared allergen. Nothing on the
page may soften that language.

## What separates this from Pullback

Pullback has one obligation: send the claim or do not. Best By has **two**, and they are different
kinds of work done by different people in different rooms.

| | PULL | NOTIFY |
|---|---|---|
| Where | the shelf, a specific bay | a phone, a household file |
| Who | a volunteer with a cart | the coordinator |
| Reversible | yes, the cases are still here | no, the food is in a kitchen |
| Fails how | someone eats it tomorrow | someone ate it last week |

They are therefore distinguished by **form, not by a second accent hue**. Two hot colours on one
card is how a page stops having a hierarchy.

- **PULL** is a filled block: `--act` background, `--on-act` text. It is a label you could stick on
  a case. It is the thing you do right now, with your hands.
- **NOTIFY** is an inset block: `--sheet-2` background, `--ink` text, 2px left rule in `--ink`.
  It is a list of names. It is the thing you work through.

One is solid and inverted, one is outlined and quiet. Distinguishable across a room, at a glance,
in greyscale, and by anyone with any form of colour vision. A card with no shelf stock renders no
PULL block at all rather than a zero, because a zero is a thing to read and an absence is not.

## Type

Two families. The split carries the argument: the serif is what the agent concluded, the mono is
what the agent can prove.

| Family | Role |
|---|---|
| Literata (variable, 400/500/600, optical sizing on) | statements, product names, hazards, headlines |
| JetBrains Mono (400/500) | every fact: counts, dates, lot codes, recall numbers, check details, labels, buttons |

Literata is a reading serif drawn for screens and long text, and it carries the ledger register
this product needs: a pantry keeps a book. Newsreader is deliberately not reused, because Best By
is not a news product, it is an inventory record. Fraunces, Instrument Serif, Playfair and every
display serif are banned. There is no sans in this system.

JetBrains Mono over IBM Plex Mono for one reason that matters here: its digits are wide and its
zero is slashed, and this page is read by someone comparing `S88N D1M` on a screen to `S88N D1M`
stamped on the bottom of a can under bad fluorescent light.

### Scale

| Token | Size / line | Family | Used for |
|---|---|---|---|
| `--t-statement` | clamp(29px, 2.1vw + 17px, 40px) / 1.12 | Literata 400 | empty-state report, case headline |
| `--t-record` | clamp(20px, 0.8vw + 16px, 24px) / 1.24 | Literata 400 | one queue record's product |
| `--t-hazard` | clamp(16px, 0.4vw + 14.5px, 18px) / 1.45 | Literata 400 | the hazard sentence |
| `--t-prose` | 16px / 1.6 | Literata 400 | body, secondary statements |
| `--t-count` | 26px / 1 | JetBrains Mono 500, tabular | the PULL number, the NOTIFY number |
| `--t-data` | 13px / 1.55 | JetBrains Mono 400 | check details, lot rows, timeline detail |
| `--t-label` | 10.5px / 1 | JetBrains Mono 500, `0.11em` tracking, uppercase | section labels, field names |
| `--t-micro` | 11.5px / 1.4 | JetBrains Mono 400 | timestamps, case ids, bay names |

Numerals are always `tabular-nums` in mono. Counts, dates, lot codes and recall numbers never
render in the serif. A number in Literata on this page is a bug.

## Colour roles

One accent (`--act`), one hazard (`--hazard`), one waiting state (`--wait`). Three non-neutral
roles and no fourth. The accent is a deep teal because it is the colour of the action and of the
resolved empty state, and it is never used for hazard. Hazard owns oxblood and nothing else owns
oxblood.

| Role | Light | Dark | Meaning |
|---|---|---|---|
| `--paper` | `#EEF1F0` | `#101314` | page |
| `--sheet` | `#FAFBFA` | `#171B1C` | a record, a panel |
| `--sheet-2` | `#E4E8E7` | `#1E2324` | inset block, notify block, notice text, code |
| `--ink` | `#13181A` | `#E6EAE9` | primary text |
| `--ink-2` | `#434A4C` | `#A5ABAA` | secondary prose |
| `--ink-3` | `#6A7274` | `#79817F` | labels, timestamps, cleared checks |
| `--rule` | `#D7DCDB` | `#282D2E` | hairline between records |
| `--rule-strong` | `#BEC5C3` | `#383E3F` | table head rule, inset border |
| `--act` | `#0F4B4A` | `#54A8A0` | the pull block, primary action, resolved |
| `--on-act` | `#F5FAF9` | `#0A1513` | text on the accent |
| `--hazard` | `#8A1C16` | `#DE7C73` | hazard sentence, Class I, children under 5, failed check |
| `--wait` | `#6F4A0C` | `#CE9C48` | waiting on a person to go look at a shelf |

No pure black, no pure white. Backgrounds are a cool desaturated green-grey, deliberately not the
cream and brass palette every generated "trustworthy" page reaches for, and deliberately not the
warm food-app orange.

Every text-on-background pair in this table clears WCAG AA at its rendered size.

## Space and shape

4px base unit. Steps used: 4, 8, 12, 16, 24, 32, 48, 64, 96.
Container is a single reading column, `max-width: 1060px`, `padding-inline: 24px`.
Vertical rhythm between queue records is a 1px `--rule`, not a gap. Records are sheets of one
document, not floating cards.

Radius is `2px` everywhere and there is no second radius in the system. Nothing is a pill, nothing
is a circle. 2px rather than Pullback's 4px because every boxed thing on this page is standing in
for a printed object: a shipping label, an intake slip, a shelf tag.

Elevation is a hairline border and a background shift. There is no drop shadow anywhere.

## Components and their states

### Record (a queue row)

Two columns at `lg`: a reading column and a 168px right rail. The rail carries the urgency mark,
the recall number, the classification and the case id, right aligned, so the page has a spine and
the rules run the full width. The reading column carries, in the order a coordinator needs it:

1. the decision in plain words, the `headline` string, in serif, largest thing in the record
2. the product, brand and size, from the first lot's `product_description`
3. the hazard sentence, `recall.reason`, in `--hazard`
4. the two obligation blocks, PULL and NOTIFY, side by side
5. exactly one action: open the case

Below `lg` the rail stacks above the reading column, because the urgency mark is what decides
whether the coordinator reads the rest.

| State | Treatment |
|---|---|
| rest | 1px `--rule` bottom, `padding: 28px 0 30px` |
| hover | background `--sheet`, action underline appears |
| focus-visible | 2px `--act` outline, 2px offset, on the whole record link |
| pressed | `translateY(1px)` |

### Urgency mark

One mono uppercase phrase in the state colour, and nothing else. No coloured dot, no square, no
pill, no badge, no icon.

| `urgency` | Renders as | Colour |
|---|---|---|
| `same_day` | `SAME DAY` | `--hazard` |
| `today` | `TODAY` | `--ink` |
| `this_week` | `THIS WEEK` | `--ink-2` |
| `check` | `GO LOOK` | `--wait` |

`GO LOOK` rather than `CHECK`, because the row means a volunteer has to physically walk to a bay
and photograph a label. The word names the errand.

### Obligation blocks

```
PULL                          NOTIFY
84 units                      10 households
4 cases, Dry Goods A3         63 units, 8 with a child under 5
```

The count is `--t-count`, the qualifier is `--t-micro`. Bay names come verbatim from
`pull.locations`. `notify.children_under_5` renders in `--hazard` and only when it is nonzero,
because it is the number that set the urgency in the first place. Neither block is rendered when
its side of the decision is empty.

### Check row (the audit trail)

Grid: `[mark] [name, mono] [detail, mono, tabular]`. This is the point of the detail page. The
`detail` string is never paraphrased, truncated, or re-formatted. It is the string the matching
engine produced, and it is the only thing on the page that proves the pull list is not a guess.

Passed rows: `--ink` mark and name on `--sheet`. Failed rows: `--hazard` mark and name, plus a 2px
left rule in `--hazard`. Cleared, meaning a check that ran and did not decide: `--ink-3`.

### Errand list (`needs_evidence`)

Each `missing[]` string is already written as a physical instruction. It renders as a numbered
errand with the bay name pulled out into `--t-label` above it, and nothing is added to the string.
This block is `--wait` bordered, because nothing can move until a person walks over there.

### Buttons

| Variant | Rest | Hover | Focus | Disabled |
|---|---|---|---|---|
| primary | `--act` fill, `--on-act` text, mono uppercase 11px | brightness 1.08 | 2px offset `--act` ring | 40% opacity, real reason in `title` |
| secondary | transparent, 1px `--rule-strong`, `--ink` | border `--ink-3` | same ring | same |

Labels are two words at most and never wrap.

### Empty queue

Not a component, the point of the product. A serif statement, then a mono report of what the agent
screened while the coordinator was away, then the count that closed without them. Every number in
it is read from the cases table. There is no "No data", no grey illustration, no shrug.

## Motion

`MOTION_INTENSITY 2`. Three animations exist in the whole console.

1. Record hover background, 120ms ease-out. Feedback.
2. Button and record press `translateY(1px)`, 80ms. Feedback.
3. Empty-state report fades up 8px over 420ms on load. Storytelling: it answers the question the
   coordinator opened the page with.

Everything collapses to instant under `prefers-reduced-motion: reduce`. No scroll hijack, no
parallax, no skeleton shimmer, no spinners, no count-up numbers.

## Rules this console holds itself to

- Zero em dashes anywhere in copy or code.
- No hardcoded case data in any component. Every figure on screen came out of DynamoDB in a server
  component, and the number a person reads can be traced to one attribute of one row.
- Nothing is computed in the browser. If a number is not on the row, it does not appear. No
  percentages, no trends, no charts, no sparklines, no totals the agent did not write.
- No emoji, no icon library, no decorative SVG. The only glyphs are type.
- One action per record. A row of buttons is a product that has not decided what matters.
- Empty states say what happened.
- Each route owns its own `<title>` from a server component.
- Contact details for a household are never displayed. The console shows who to call and why. The
  phone number lives in the pantry's own system, and a recall console is not a place to leak it.
