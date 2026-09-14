/**
 * Slicing the queue.
 *
 * The filter is in the URL and nowhere else. No state, no client component, no
 * dropdown that forgets what it was set to. A coordinator can send
 * `/?class=Class+I&bay=Dry+Goods+A3` to the volunteer running that aisle and
 * they get the same page.
 *
 * Every option offered is read off the rows that are actually in the queue, so
 * the bar never offers a filter that returns nothing.
 */

import { Case, URGENCY_ORDER, Urgency } from "./types";

export type Sort = "urgency" | "oldest" | "newest" | "units";

export const SORTS: { key: Sort; label: string }[] = [
  { key: "urgency", label: "urgency" },
  { key: "oldest", label: "oldest recall" },
  { key: "newest", label: "newest recall" },
  { key: "units", label: "most units" },
];

export interface Query {
  klass: string | null;
  bay: string | null;
  households: "yes" | "no" | null;
  sort: Sort;
}

export type RawParams = Record<string, string | string[] | undefined>;

function one(v: string | string[] | undefined): string | null {
  if (Array.isArray(v)) return v[0] ?? null;
  return v && v.length > 0 ? v : null;
}

export function parseQuery(params: RawParams): Query {
  const sort = one(params.sort);
  const households = one(params.households);
  return {
    klass: one(params.class),
    bay: one(params.bay),
    households:
      households === "yes" || households === "no" ? households : null,
    sort: SORTS.some((s) => s.key === sort) ? (sort as Sort) : "urgency",
  };
}

export function href(q: Query, patch: Partial<Query>, base = "/"): string {
  const next: Query = { ...q, ...patch };
  const p = new URLSearchParams();
  if (next.klass) p.set("class", next.klass);
  if (next.bay) p.set("bay", next.bay);
  if (next.households) p.set("households", next.households);
  if (next.sort !== "urgency") p.set("sort", next.sort);
  const s = p.toString();
  return s ? `${base}?${s}` : base;
}

export function isFiltered(q: Query): boolean {
  return q.klass !== null || q.bay !== null || q.households !== null;
}

export function caseBays(c: Case): string[] {
  return [
    ...new Set(
      [...c.pull.lots, ...c.needs_evidence].map((l) => l.storage_location),
    ),
  ];
}

export function classesOn(cases: Case[]): string[] {
  return [...new Set(cases.map((c) => c.recall.classification))].sort();
}

export function baysOn(cases: Case[]): string[] {
  return [...new Set(cases.flatMap(caseBays))].sort();
}

/** Oldest notices first. A recall with no published date sorts last, never first. */
function byDate(a: Case, b: Case, direction: 1 | -1): number {
  const da = a.recall.recall_date;
  const db = b.recall.recall_date;
  if (!da && !db) return 0;
  if (!da) return 1;
  if (!db) return -1;
  return da === db ? 0 : da < db ? -direction : direction;
}

export function applyQuery(cases: Case[], q: Query): Case[] {
  let rows = cases;
  if (q.klass) rows = rows.filter((c) => c.recall.classification === q.klass);
  if (q.bay) rows = rows.filter((c) => caseBays(c).includes(q.bay as string));
  if (q.households === "yes") rows = rows.filter((c) => c.notify.households > 0);
  if (q.households === "no") rows = rows.filter((c) => c.notify.households === 0);

  const out = [...rows];
  if (q.sort === "oldest") out.sort((a, b) => byDate(a, b, 1));
  else if (q.sort === "newest") out.sort((a, b) => byDate(a, b, -1));
  else if (q.sort === "units")
    out.sort(
      (a, b) =>
        b.pull.units + b.notify.units - (a.pull.units + a.notify.units),
    );
  else
    out.sort((a, b) => {
      const ua = URGENCY_ORDER[a.urgency as Urgency] ?? 9;
      const ub = URGENCY_ORDER[b.urgency as Urgency] ?? 9;
      if (ua !== ub) return ua - ub;
      return a.recall.recall_number.localeCompare(b.recall.recall_number);
    });
  return out;
}

/** What the active filter says out loud, for the line above the queue. */
export function describe(q: Query): string[] {
  const parts: string[] = [];
  if (q.klass) parts.push(q.klass);
  if (q.bay) parts.push(q.bay);
  if (q.households === "yes") parts.push("households involved");
  if (q.households === "no") parts.push("shelf only");
  return parts;
}
