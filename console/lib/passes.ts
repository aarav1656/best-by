/**
 * What the agent did while nobody was watching.
 *
 * There is no separate run table. The proof that a pass ran is written into
 * every case it touched: `timeline[]` holds one `opened` entry per case per
 * pass, and the sweep stamps the same `ran_at` on all of them, so a timestamp
 * that appears on more than one case is a pass. Everything the agent did next,
 * drafting a notice, asking for approval, recording a pull, filing the record,
 * sending the notices, happened before the next sweep and is listed under it.
 *
 * Nothing here is parsed out of a detail string. The strings are printed as the
 * agent wrote them, which is the only reason this page is evidence.
 */

import { Case, TimelineEvent } from "./types";

export interface PassEvent extends TimelineEvent {
  caseId: string;
  recallNumber: string;
  headline: string;
}

export interface Pass {
  at: string;
  /** One row per case this pass read, with the agent's own words for it. */
  opened: PassEvent[];
  /** Everything that followed, before the next pass started. */
  actions: PassEvent[];
  /** Event name to count, for the one line summary. */
  tally: { event: string; n: number }[];
  cases: number;
}

function flatten(cases: Case[]): PassEvent[] {
  const out: PassEvent[] = [];
  for (const c of cases) {
    for (const t of c.timeline) {
      out.push({
        ...t,
        caseId: c.case_id,
        recallNumber: c.recall.recall_number,
        headline: c.headline,
      });
    }
  }
  out.sort((a, b) => (a.at === b.at ? 0 : a.at < b.at ? -1 : 1));
  return out;
}

export function reconstructPasses(cases: Case[]): Pass[] {
  const events = flatten(cases);
  if (events.length === 0) return [];

  const opensAt = new Map<string, Set<string>>();
  for (const e of events) {
    if (e.event !== "opened") continue;
    const held = opensAt.get(e.at);
    if (held) held.add(e.caseId);
    else opensAt.set(e.at, new Set([e.caseId]));
  }

  // A sweep writes one timestamp across every case it read. A timestamp held by
  // a single case is the agent working that case inside a pass, not a pass.
  let starts = [...opensAt.entries()]
    .filter(([, ids]) => ids.size > 1)
    .map(([at]) => at)
    .sort();
  if (starts.length === 0) starts = [...opensAt.keys()].sort();
  if (starts.length === 0) starts = [events[0].at];
  // Anything written before the first sweep still belongs to a pass.
  if (events[0].at < starts[0]) starts[0] = events[0].at;

  const passes: Pass[] = starts.map((at) => ({
    at,
    opened: [],
    actions: [],
    tally: [],
    cases: 0,
  }));

  let cursor = 0;
  for (const e of events) {
    while (cursor + 1 < starts.length && e.at >= starts[cursor + 1]) cursor += 1;
    const pass = passes[cursor];
    if (e.event === "opened") pass.opened.push(e);
    else pass.actions.push(e);
  }

  for (const pass of passes) {
    // One case can be read twice inside a pass, once by the sweep and once by
    // the agent. The later read is the one that decided the case.
    const latest = new Map<string, PassEvent>();
    for (const e of pass.opened) latest.set(e.caseId, e);
    pass.opened = [...latest.values()].sort((a, b) =>
      a.recallNumber.localeCompare(b.recallNumber),
    );
    pass.cases = new Set([
      ...pass.opened.map((e) => e.caseId),
      ...pass.actions.map((e) => e.caseId),
    ]).size;

    const counts = new Map<string, number>();
    for (const e of pass.actions)
      counts.set(e.event, (counts.get(e.event) ?? 0) + 1);
    pass.tally = [...counts.entries()]
      .map(([event, n]) => ({ event, n }))
      .sort((a, b) => b.n - a.n);
    pass.actions.reverse();
  }

  return passes.reverse();
}

export const EVENT_WORD: Record<string, [string, string]> = {
  notice_drafted: ["notice drafted", "notices drafted"],
  approval_requested: ["approval requested", "approvals requested"],
  pulled: ["pull recorded", "pulls recorded"],
  record_filed: ["record filed", "records filed"],
  households_notified: ["notice sent", "rounds of notices sent"],
  shelf_check_requested: ["shelf check requested", "shelf checks requested"],
  timeline_trimmed: ["timeline trimmed", "timelines trimmed"],
};

export function eventWord(event: string, n: number): string {
  const pair = EVENT_WORD[event];
  if (!pair) return event.replace(/_/g, " ");
  return n === 1 ? pair[0] : pair[1];
}
