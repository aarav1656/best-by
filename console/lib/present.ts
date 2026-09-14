import { Case, Lot, Urgency, URGENCY_WORD } from "./types";

export function urgencyMark(u: Urgency | string): string {
  const word = URGENCY_WORD[u as Urgency];
  return (word ?? String(u).replace(/_/g, " ")).toUpperCase();
}

export function primaryLot(c: Case): Lot | null {
  return c.pull.lots[0] ?? c.needs_evidence[0] ?? null;
}

/** The brand is already inside most intake descriptions. Never print it twice. */
export function productLine(lot: Lot): string {
  const desc = lot.product_description;
  if (!lot.brand) return desc;
  const haystack = desc.toLowerCase();
  const named = lot.brand
    .toLowerCase()
    .split(/[\s,.]+/)
    .filter((w) => w.length >= 3)
    .some((w) => haystack.includes(w));
  return named ? desc : `${lot.brand} ${desc}`;
}

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function stamp(iso: string | null): string {
  if (!iso) return "not recorded";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(
    d.getUTCDate(),
  )} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;
}

export function evidenceBucket(uri: string): string {
  return uri.replace(/^s3:\/\//, "");
}
