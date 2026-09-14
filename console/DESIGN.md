# Best By console design system - Stamp & Sheet

Best By is a pantry coordinator tool. It matches live FDA food recalls to shelf
stock and to households who already took food home. Dual obligations: **PULL**
(shelf) and **NOTIFY** (households).

This console is **Stamp & Sheet**. It is not a notice feed and not a dashboard.

## Differentiation (hard)

| Axis | Pullback | Lapse | Best By |
|---|---|---|---|
| Metaphor | public recall notice / claim letter | DOB service notice / deadline | stamped case + dual sheets |
| Type | Newsreader + IBM Plex Mono | Newsreader + IBM Plex Mono | **Literata + JetBrains Mono** |
| Paper | cool grey-green | cool grey-green | **warm carton kraft** |
| Accent | forest green seal | deadline hue ramp | **indigo stamp ink** |
| Hazard | oxblood | oxblood / lapsed | oxblood (Class I / kids under 5 only) |
| Layout | one reading column | one reading column | **persistent SHELF \| KITCHENS split** |
| Radius | ~4px | ~4px | **0–1px** |
| Showpiece | empty night shift | deadline countdown | **stamped lot match + printable bay sheet** |

Banned overlaps with siblings: Newsreader, Plex Mono, green/teal as primary
action, single hairline document spine as the home layout, "public notice"
masthead voice.

## The one thing this interface has to do

Interrupt the coordinator once per recall. The work happens in Dry Goods A3
with a cart, and on the phone with a household. The console is where they read
one card and decide two things:

**pull these N cases off the shelf, call these M households.**

An empty queue is the product working. It reads as shelves cleared, never as an
empty SaaS inbox. Empty state uses an indigo **CLEARED** stamp, never a green
checkmark.

## Metaphor: stamp and sheet

1. **The stamp** - the lot code ink-jetted on the case. That string is the
   product's whole claim. Matched recall cards lead with an oversized mono lot
   stamp. If no lot code exists, the stamp reads **GO LOOK**.
2. **The sheets** - a **PULL SHEET** for the cart, and a **CALL SHEET** for the
   coordinator. Home opens with two sheet panels (SHELF | KITCHENS), not five
   equal KPI tiles.

## PULL vs NOTIFY (form, not a second hue)

| | PULL | NOTIFY |
|---|---|---|
| Where | the shelf, a specific bay | a phone, a household file |
| Who | a volunteer with a cart | the coordinator |
| Form | filled `--stamp` / `--on-stamp` | `--sheet-2` inset, 2px left rule in `--ink` |

One accent only. Two hot colours on one card kills hierarchy. A card with no
shelf stock renders no PULL block (absence, not a zero).

## Type

Keep Literata + JetBrains Mono. They already separate Best By from Pullback and
Lapse.

| Token | Spec | Use |
|---|---|---|
| `--t-statement` | Literata 400, clamp(28–38px) / 1.15 | shift brief |
| `--t-product` / `--t-record` | Literata 500, clamp(18–22px) / 1.25 | product on a sheet row |
| `--t-hazard` | Literata 400, 16–17px / 1.45, `--hazard` | organism / allergen sentence only |
| `--t-stamp` | JetBrains Mono 500, clamp(22–36px), tracking 0.04em, tabular | **the lot code, hero** |
| `--t-count` | JetBrains Mono 500, 28–40px, tabular | pull units / household counts |
| `--t-label` | JetBrains Mono 500, 10px, 0.14em caps | SHELF, KITCHENS, BAY, CLASS I |
| `--t-data` | JetBrains Mono 400, 13px | bay, recall #, intake id, SES id |

A number in Literata is a bug. A lot code not in `--t-stamp` is a bug.

## Color

Warm carton, indigo ink, oxblood hazard. No teal. No forest green.

| Role | Light | Dark | Meaning |
|---|---|---|---|
| `--paper` | `#F1E8D8` | `#161310` | kraft page |
| `--sheet` | `#FAF6EE` | `#1E1A16` | a sheet panel |
| `--sheet-2` | `#E6DCC8` | `#2A241C` | inset / notify list |
| `--ink` | `#1A1510` | `#F0E8DA` | primary |
| `--ink-2` | `#5A5044` | `#B8AE9E` | secondary |
| `--ink-3` | `#8A7E6E` | `#8A8070` | labels |
| `--rule` | `#D4C8B0` | `#3A3228` | sheet edge |
| `--stamp` | `#1B2A5A` | `#8FA4E0` | primary action + lot stamp |
| `--on-stamp` | `#F7F4EC` | `#0E1220` | text on stamp |
| `--hazard` | `#8A1C16` | `#E08078` | Class I, kids under 5, failed check |
| `--wait` | `#7A4E0C` | `#D3A24E` | GO LOOK / needs photo |

Accent meaning: indigo is the ink that stamped the can. Resolved empty state
uses `--stamp`, never green.

## Layout rhythm

### Home = two sheets, not one queue

- One Literata shift brief.
- Two sheet panels: SHELF (pull units/bays) and KITCHENS (households to tell).
- Matched recall cards below; each leads with the lot stamp, then product,
  hazard, PULL / NOTIFY blocks.
- Urgency (`SAME DAY` / `TODAY` / `GO LOOK`) stays mono caps in the card corner.

### Pull route = bay clipboard

Bay sections as tear-off blocks with a checkbox column that survives print.
Lot code column uses stamp-sized mono. Footer sign-off styled as a rubber-stamp
box.

### Passes = overnight report

Mono ledger of what screened while the coordinator slept. No charts.

## Components

1. **Sheet panel** - kraft inset, 1px `--rule`, label SHELF or KITCHENS, one huge
   count, one verb, one CTA.
2. **Stamp** - lot code in `--stamp` ink, light wash behind it. 0° rotation for
   scanability (optional tilt only on empty-state storytelling).
3. **PULL block** - filled `--stamp` / `--on-stamp`.
4. **NOTIFY block** - `--sheet-2` with 2px left rule in `--ink`.
5. **Record** - no floating card shadow; 1px carton edge; 0–1px radius.
6. **Empty state** - Literata: "Nothing under recall on these shelves." Mono
   overnight report. **CLEARED** stamp in indigo.

## Motion

Low intensity. One showpiece: on a MATCH card enter view, lot stamp settles
280ms ease-out. Everything else: 80–120ms press/hover. Honor
`prefers-reduced-motion`.

## Banned chrome

No pills, shadows, emoji, icon libraries, charts, or em dashes in UI copy.
Radius stays 0–1px.

## Rules (honesty)

Do not invent case data. Do not change DynamoDB reads, matching, or agent
backend behavior in the name of design. Every figure on the home position is a
count of rows. Hazard strings stay verbatim from FDA reason text.

## What a judge must see in 10 seconds

1. This is a **food pantry** tool (kraft, bay names, households, cases).
2. The agent matches **stamped lot codes** to FDA notices.
3. Work splits into **pull off the shelf** vs **tell kitchens who already took
   it home**.

If any of those three needs narration, the UI failed.
