/**
 * The pantry's whole position, read off the case rows.
 *
 * Everything here is a sum or a count over attributes that are already on a
 * row. Nothing is estimated and nothing is a rate.
 *
 * The one piece of arithmetic that needed a decision is double counting. Two
 * notices can name the same intake lot, and two notices can name the same
 * household, because the FDA publishes one recall number per firm action and a
 * firm can take four of them against one jar of peanut butter. A volunteer
 * still walks to the bay once and pulls those cases once. So a lot is counted
 * once by `lot_id` and a household once by `household_id`, and the recall
 * numbers that implicate each one are carried along rather than thrown away.
 */

import { Case, Lot, Recipient } from "./types";
import { deliveryLines } from "./present";

export interface ShelfLot {
  lot: Lot;
  /** Every open notice that names this lot, in the order the queue holds them. */
  recalls: string[];
  caseIds: string[];
  /**
   * Every distinct thing a person has to go and read, across all of those
   * notices. Four notices on one jar can ask for different evidence, and a
   * volunteer walking to the bay should carry all of it in one trip.
   */
  missing: string[];
}

export interface OwedHousehold {
  recipient: Recipient;
  recalls: string[];
  /**
   * Units of recalled food this household is holding, added up across every
   * notice that owes them a call. Two recalls mean two different foods in one
   * kitchen, so units add. The children under five do not: they are the same
   * children, and counting them twice would inflate the one number on this
   * page that decides who gets phoned first.
   */
  units: number;
}

export interface UnreachedCase {
  caseId: string;
  recallNumber: string;
  unreached: number;
  of: number;
}

export interface Position {
  openCases: number;
  closedCases: number;
  classI: number;
  /** Distinct intake lots under an open recall that are still on the shelf. */
  pullLots: ShelfLot[];
  pullUnits: number;
  pullCases: number;
  pullBays: string[];
  /** Distinct intake lots a person has to walk over and photograph. */
  checkLots: ShelfLot[];
  checkBays: string[];
  /** Distinct households on an open notify list with no delivery recorded. */
  owed: OwedHousehold[];
  owedUnits: number;
  owedChildren: number;
  /** Distinct households a notice actually reached. */
  reached: string[];
  unreached: UnreachedCase[];
  unreachedHouseholds: number;
  updatedAt: string | null;
}

function collect(
  index: Map<string, ShelfLot>,
  lots: Lot[],
  c: Case,
): void {
  for (const lot of lots) {
    const held = index.get(lot.lot_id);
    if (held) {
      if (!held.recalls.includes(c.recall.recall_number)) {
        held.recalls.push(c.recall.recall_number);
        held.caseIds.push(c.case_id);
      }
      for (const m of lot.missing) {
        if (!held.missing.includes(m)) held.missing.push(m);
      }
      continue;
    }
    index.set(lot.lot_id, {
      lot,
      recalls: [c.recall.recall_number],
      caseIds: [c.case_id],
      missing: [...lot.missing],
    });
  }
}

export function readPosition(cases: Case[]): Position {
  const open = cases.filter((c) => c.status !== "notified");
  const pull = new Map<string, ShelfLot>();
  const check = new Map<string, ShelfLot>();
  const owed = new Map<string, OwedHousehold>();
  const reached = new Set<string>();
  const unreached: UnreachedCase[] = [];
  let updatedAt: string | null = null;

  for (const c of cases) {
    if (!updatedAt || c.updated_at > updatedAt) updatedAt = c.updated_at;

    if (c.delivery) {
      const lines = deliveryLines(c.notify.recipients, c.delivery);
      const missed = lines.filter((l) => l.state !== "direct");
      for (const line of lines) {
        if (line.state === "direct") reached.add(line.recipient.household_id);
      }
      if (missed.length > 0) {
        unreached.push({
          caseId: c.case_id,
          recallNumber: c.recall.recall_number,
          unreached: missed.length,
          of: lines.length,
        });
      }
    }

    if (c.status === "notified") continue;

    collect(pull, c.pull.lots, c);
    collect(check, c.needs_evidence, c);

    const delivered = new Set(
      (c.delivery?.messages ?? [])
        .filter((m) => m.mode === "direct")
        .map((m) => m.household_id),
    );
    for (const recipient of c.notify.recipients) {
      if (delivered.has(recipient.household_id)) continue;
      const held = owed.get(recipient.household_id);
      if (held) {
        if (!held.recalls.includes(c.recall.recall_number)) {
          held.recalls.push(c.recall.recall_number);
          held.units += recipient.units;
        }
        continue;
      }
      owed.set(recipient.household_id, {
        recipient,
        recalls: [c.recall.recall_number],
        units: recipient.units,
      });
    }
  }

  const pullLots = [...pull.values()];
  const checkLots = [...check.values()];
  const owedList = [...owed.values()];
  const bays = (rows: ShelfLot[]) =>
    [...new Set(rows.map((r) => r.lot.storage_location))].sort();

  return {
    openCases: open.length,
    closedCases: cases.length - open.length,
    classI: open.filter((c) => c.recall.class_i).length,
    pullLots,
    pullUnits: pullLots.reduce((n, r) => n + r.lot.units_on_hand, 0),
    pullCases: pullLots.reduce((n, r) => n + r.lot.cases_on_hand, 0),
    pullBays: bays(pullLots),
    checkLots,
    checkBays: bays(checkLots),
    owed: owedList,
    owedUnits: owedList.reduce((n, h) => n + h.units, 0),
    owedChildren: owedList.reduce((n, h) => n + h.recipient.children_under_5, 0),
    reached: [...reached].sort(),
    unreached,
    unreachedHouseholds: unreached.reduce((n, u) => n + u.unreached, 0),
    updatedAt,
  };
}

/** Lots in a bay, bays in shelf order, for a person walking the aisle. */
export interface Bay {
  name: string;
  lots: ShelfLot[];
  units: number;
  cases: number;
}

export function byBay(rows: ShelfLot[]): Bay[] {
  const bays = new Map<string, ShelfLot[]>();
  for (const row of rows) {
    const name = row.lot.storage_location;
    const held = bays.get(name);
    if (held) held.push(row);
    else bays.set(name, [row]);
  }
  return [...bays.entries()]
    .map(([name, lots]) => ({
      name,
      lots: lots.sort((a, b) => a.lot.lot_id.localeCompare(b.lot.lot_id)),
      units: lots.reduce((n, r) => n + r.lot.units_on_hand, 0),
      cases: lots.reduce((n, r) => n + r.lot.cases_on_hand, 0),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * One shelf, several notices.
 *
 * Four separate FDA actions can land on the same two jars in Dry Goods B3.
 * Each is its own recall and none of them is hidden, but the work is one
 * errand, so the queue reads the obligation once and lists the notices that
 * demand it. Cases are only grouped when they name exactly the same intake
 * lots and carry the same urgency and status, which is the only case where the
 * obligation really is identical.
 */
export interface Grouped {
  key: string;
  cases: Case[];
  lead: Case;
}

export function groupCases(cases: Case[]): Grouped[] {
  const groups = new Map<string, Case[]>();
  const order: string[] = [];
  for (const c of cases) {
    const lots = [...c.pull.lots, ...c.needs_evidence]
      .map((l) => l.lot_id)
      .sort()
      .join("+");
    // A case with no lots at all shares nothing with another case, so it keys
    // on itself rather than falling into an empty-string bucket with every
    // other lotless case.
    const key = lots
      ? `${c.urgency}|${c.status}|${lots}`
      : `case:${c.case_id}`;
    const held = groups.get(key);
    if (held) held.push(c);
    else {
      groups.set(key, [c]);
      order.push(key);
    }
  }
  return order.map((key) => {
    const rows = groups.get(key) as Case[];
    return { key, cases: rows, lead: rows[0] };
  });
}
