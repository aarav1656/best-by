import {
  Case,
  Delivery,
  DeliveryMessage,
  DeliveryMode,
  Lot,
  Recipient,
  Urgency,
  URGENCY_WORD,
} from "./types";

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

/**
 * Same stamp, to the second. Two passes can start twenty two seconds apart, and
 * a page that prints both as the same minute is claiming they were one run.
 */
export function stampExact(iso: string | null): string {
  if (!iso) return "not recorded";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(
    d.getUTCDate(),
  )} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} UTC`;
}

/**
 * How a send actually landed.
 * `simulator` means SES accepted the message into the
 * mailbox simulator instead of the household's own address, so the family was not
 * reached. It is never a success and never rendered as one.
 */
export const DELIVERY_STATE: Record<
  DeliveryMode | "missing",
  { mark: string; tone: "stamp" | "wait" | "hazard" }
> = {
  direct: { mark: "reached", tone: "stamp" },
  simulator: { mark: "not reached", tone: "wait" },
  failed: { mark: "send failed", tone: "hazard" },
  missing: { mark: "no record", tone: "hazard" },
};

export interface DeliveryLine {
  recipient: Recipient;
  message: DeliveryMessage | null;
  state: DeliveryMode | "missing";
}

/** Join the notify roster to what SES actually did, keeping every household. */
export function deliveryLines(
  recipients: Recipient[],
  delivery: Delivery,
): DeliveryLine[] {
  const byHousehold = new Map(delivery.messages.map((m) => [m.household_id, m]));
  const lines: DeliveryLine[] = recipients.map((recipient) => {
    const message = byHousehold.get(recipient.household_id) ?? null;
    byHousehold.delete(recipient.household_id);
    return { recipient, message, state: message ? message.mode : "missing" };
  });
  return lines;
}

/** Households the notice did not reach, for any reason. */
export function unreachedCount(lines: DeliveryLine[]): number {
  return lines.filter((l) => l.state !== "direct").length;
}
