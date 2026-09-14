import type { Metadata } from "next";
import Link from "next/link";
import { listCases, PANTRY_ID } from "@/lib/cases";
import { Case } from "@/lib/types";
import {
  deliveryLines,
  plural,
  primaryLot,
  productLine,
  stamp,
  unreachedCount,
  urgencyMark,
} from "@/lib/present";
import { Position, readPosition, groupCases, Grouped } from "@/lib/position";
import {
  Query,
  RawParams,
  SORTS,
  applyQuery,
  baysOn,
  caseBays,
  classesOn,
  describe,
  href,
  isFiltered,
  parseQuery,
} from "@/lib/filters";
import { Masthead } from "./masthead";
import { Provenance } from "./provenance";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Best By: the decision queue",
  description:
    "Open recalls that touch this pantry's shelves, in the order they have to be handled.",
};

function Overview({ p }: { p: Position }) {
  const bayWord = p.pullBays.length === 1 ? "bay" : "bays";
  const brief =
    p.openCases === 0
      ? "Nothing under recall on these shelves."
      : `${p.openCases} open ${
          p.openCases === 1 ? "recall touches" : "recalls touch"
        } these shelves. Pull first. Then call the kitchens that already took some home.`;

  return (
    <section className="position">
      <div className="label">Shift brief · {stamp(p.updatedAt)}</div>

      <p className="position-statement">{brief}</p>

      <div className="sheets">
        <section className="sheet-panel">
          <div className="lbl">Shelf · pull sheet</div>
          <div className="count">{p.pullUnits}</div>
          <div className="verb">
            units off {p.pullBays.length} {bayWord}
          </div>
          <div className="meta">
            {plural(p.pullCases, "case", "cases")} ·{" "}
            {plural(p.pullLots.length, "intake lot", "intake lots")}
            {p.checkLots.length > 0 ? (
              <>
                <br />
                {plural(p.checkLots.length, "lot", "lots")} still need a hand
                read
              </>
            ) : null}
          </div>
          <Link className="cta" href="/pull">
            Print pull sheet
          </Link>
        </section>

        <section className="sheet-panel kitchens">
          <div className="lbl">Kitchens · call sheet</div>
          <div className="count">{p.owed.length}</div>
          <div className="verb">
            {p.owed.length === 1
              ? "household not yet told"
              : "households not yet told"}
          </div>
          <div className="meta">
            {plural(p.owedUnits, "unit", "units")} already given out
            {p.owedChildren > 0 ? (
              <>
                <br />
                <span className="hot">
                  {p.owedChildren} with a child under 5
                </span>
              </>
            ) : null}
          </div>
          <Link className="cta" href="#matched-recalls">
            Open call list
          </Link>
        </section>
      </div>

      {p.unreached.length > 0 ? (
        <div className="band band-short position-band">
          <p className="band-statement">
            {plural(p.unreachedHouseholds, "household", "households")} were sent
            a notice that did not reach them.
          </p>
          <p className="band-detail">
            Phone them. The list is on each case:{" "}
            {p.unreached.map((u, i) => (
              <span key={u.caseId}>
                {i > 0 ? ", " : ""}
                <Link className="inline-link" href={`/case/${u.caseId}`}>
                  {u.recallNumber}
                </Link>{" "}
                ({u.unreached} of {u.of})
              </span>
            ))}
            .
          </p>
        </div>
      ) : null}

      <div className="position-acts">
        <Link className="act-link" href="/passes">
          What the agent did overnight
        </Link>
      </div>

      <p className="position-note micro">
        Every figure is a count of rows in the cases table. A lot is counted
        once by its intake id and a household once by its id, however many
        notices name it.
      </p>
    </section>
  );
}

function Filters({
  q,
  open,
  shown,
}: {
  q: Query;
  open: Case[];
  shown: number;
}) {
  const classes = classesOn(open);
  const bays = baysOn(open);
  const withHouseholds = open.filter((c) => c.notify.households > 0).length;
  const shelfOnly = open.length - withHouseholds;
  const on = (active: boolean) => `chip${active ? " on" : ""}`;

  return (
    <div className="filters">
      <div className="filter-row">
        <span className="label">Hazard</span>
        <div className="chips">
          <Link className={on(q.klass === null)} href={href(q, { klass: null })}>
            all {open.length}
          </Link>
          {classes.map((k) => (
            <Link
              key={k}
              className={on(q.klass === k)}
              href={href(q, { klass: q.klass === k ? null : k })}
            >
              {k} {open.filter((c) => c.recall.classification === k).length}
            </Link>
          ))}
        </div>
      </div>

      <div className="filter-row">
        <span className="label">Bay</span>
        <div className="chips">
          <Link className={on(q.bay === null)} href={href(q, { bay: null })}>
            all {bays.length}
          </Link>
          {bays.map((b) => (
            <Link
              key={b}
              className={on(q.bay === b)}
              href={href(q, { bay: q.bay === b ? null : b })}
            >
              {b} {open.filter((c) => caseBays(c).includes(b)).length}
            </Link>
          ))}
        </div>
      </div>

      <div className="filter-row">
        <span className="label">Households</span>
        <div className="chips">
          <Link
            className={on(q.households === null)}
            href={href(q, { households: null })}
          >
            either
          </Link>
          <Link
            className={on(q.households === "yes")}
            href={href(q, {
              households: q.households === "yes" ? null : "yes",
            })}
          >
            someone took it home {withHouseholds}
          </Link>
          <Link
            className={on(q.households === "no")}
            href={href(q, { households: q.households === "no" ? null : "no" })}
          >
            shelf only {shelfOnly}
          </Link>
        </div>
      </div>

      <div className="filter-row">
        <span className="label">Order</span>
        <div className="chips">
          {SORTS.map((s) => (
            <Link
              key={s.key}
              className={on(q.sort === s.key)}
              href={href(q, { sort: s.key })}
            >
              {s.label}
            </Link>
          ))}
        </div>
      </div>

      {isFiltered(q) ? (
        <p className="filter-state">
          Showing {shown} of {open.length} open recalls. {describe(q).join(". ")}
          .{" "}
          <Link className="inline-link" href={href(q, { klass: null, bay: null, households: null })}>
            Clear the filter
          </Link>
        </p>
      ) : null}
    </div>
  );
}

function Obligations({ c }: { c: Case }) {
  const errandBays = [
    ...new Set(c.needs_evidence.map((l) => l.storage_location)),
  ];
  return (
    <div className="obligations">
      {c.pull.units > 0 ? (
        <div className="ob ob-pull">
          <div className="label">Pull</div>
          <div className="ob-count">
            {c.pull.units}{" "}
            <span>{c.pull.units === 1 ? "unit" : "units"}</span>
          </div>
          <div className="ob-where">
            {plural(c.pull.cases, "case", "cases")} in{" "}
            {c.pull.locations.join(", ")}
          </div>
        </div>
      ) : null}

      {c.notify.households > 0 ? (
        <div className="ob ob-notify">
          <div className="label">Notify</div>
          <div className="ob-count">
            {c.notify.households}{" "}
            <span>
              {c.notify.households === 1 ? "household" : "households"}
            </span>
          </div>
          <div className="ob-where">
            {plural(c.notify.units, "unit", "units")} already given out
            {c.notify.children_under_5 > 0 ? (
              <span className="under5">
                {c.notify.children_under_5} with a child under 5
              </span>
            ) : null}
          </div>
        </div>
      ) : null}

      {c.needs_evidence.length > 0 ? (
        <div className="ob ob-look">
          <div className="label">Go look</div>
          <div className="ob-count">
            {c.needs_evidence.length}{" "}
            <span>{c.needs_evidence.length === 1 ? "lot" : "lots"}</span>
          </div>
          <div className="ob-where">{errandBays.join(", ")}</div>
        </div>
      ) : null}
    </div>
  );
}

function products(c: Case): string[] {
  const seen = new Set<string>();
  for (const lot of [...c.pull.lots, ...c.needs_evidence]) {
    seen.add(productLine(lot));
  }
  return [...seen];
}

function Rail({ group }: { group: Grouped }) {
  const lead = group.lead;
  const classes = [...new Set(group.cases.map((c) => c.recall.classification))];
  return (
    <div className="rail">
      <div className={`urgency u-${lead.urgency}`}>
        {urgencyMark(lead.urgency)}
      </div>
      {group.cases.length === 1 ? (
        <div className="micro">{lead.recall.recall_number}</div>
      ) : (
        <div className="micro">
          {group.cases.length} FDA actions
        </div>
      )}
      {classes.map((k) => (
        <div
          key={k}
          className={`micro${k.includes("Class I") && !k.includes("II") ? " class-i" : ""}`}
        >
          {k}
        </div>
      ))}
      <div className="micro">{lead.recall.firm_location}</div>
    </div>
  );
}

function LotStamp({ c }: { c: Case }) {
  const lot = primaryLot(c);
  const code = lot?.lot_code?.trim() || null;
  if (code) {
    return <div className="lot-stamp">{code}</div>;
  }
  return <div className="lot-stamp look">GO LOOK</div>;
}

function RecordBody({ c }: { c: Case }) {
  return (
    <>
      <LotStamp c={c} />
      <h2 className="record-head">{c.headline}</h2>
      {products(c).map((p) => (
        <p className="record-product" key={p}>
          {p}
        </p>
      ))}
      <p className="record-hazard">{c.recall.reason}</p>
      <Obligations c={c} />
    </>
  );
}

function Record({ group }: { group: Grouped }) {
  const lead = group.lead;

  if (group.cases.length === 1) {
    return (
      <Link href={`/case/${lead.case_id}`} className="record">
        <div>
          <RecordBody c={lead} />
          <span className="record-open">Open case</span>
        </div>
        <Rail group={group} />
      </Link>
    );
  }

  return (
    <div className="record record-group">
      <div>
        <RecordBody c={lead} />
        <div className="same-shelf">
          <div className="label">
            {group.cases.length} separate notices on the same{" "}
            {plural(
              [...lead.pull.lots, ...lead.needs_evidence].length,
              "intake lot",
              "intake lots",
            )}
          </div>
          <div className="same-shelf-links">
            {group.cases.map((c) => (
              <Link
                key={c.case_id}
                href={`/case/${c.case_id}`}
                className="record-open"
              >
                {c.recall.recall_number}
              </Link>
            ))}
          </div>
        </div>
      </div>
      <Rail group={group} />
    </div>
  );
}

/** A case whose notices went out. It is not a decision any more, it is a receipt. */
function ClosedRow({ c }: { c: Case }) {
  const lines = c.delivery
    ? deliveryLines(c.notify.recipients, c.delivery)
    : [];
  const unreached = c.delivery ? unreachedCount(lines) : 0;

  return (
    <Link href={`/case/${c.case_id}`} className="closed-row">
      <span className="closed-headline">{c.headline}</span>
      <span className="closed-recall">{c.recall.recall_number}</span>
      {c.delivery ? (
        <span className={`closed-outcome${unreached > 0 ? " hz" : ""}`}>
          {unreached > 0
            ? `${unreached} of ${lines.length} households not reached`
            : `${c.delivery.direct} of ${c.delivery.attempted} households reached`}
        </span>
      ) : (
        <span className="closed-outcome">notices sent</span>
      )}
    </Link>
  );
}

function WinState({ closed }: { closed: Case[] }) {
  const households = closed.reduce((n, c) => n + c.notify.households, 0);
  const units = closed.reduce((n, c) => n + c.pull.units, 0);

  return (
    <div className="win">
      <p className="win-statement">
        Nothing under recall on these shelves.
      </p>
      <div className="cleared-stamp">Cleared</div>
      {closed.length > 0 ? (
        <dl className="win-report">
          <div className="win-row">
            <dt>Closed</dt>
            <dd>
              {plural(closed.length, "recall", "recalls")} handled without
              interrupting you
            </dd>
          </div>
          <div className="win-row">
            <dt>Pulled</dt>
            <dd>{plural(units, "unit", "units")} off the shelves</dd>
          </div>
          <div className="win-row">
            <dt>Notified</dt>
            <dd>{plural(households, "household", "households")}</dd>
          </div>
        </dl>
      ) : (
        <dl className="win-report">
          <div className="win-row">
            <dt>Pantry</dt>
            <dd>{PANTRY_ID}</dd>
          </div>
          <div className="win-row">
            <dt>Open cases</dt>
            <dd>0</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

export default async function QueuePage({
  searchParams,
}: {
  searchParams: Promise<RawParams>;
}) {
  const q = parseQuery(await searchParams);
  const { cases, error, read } = await listCases();

  if (error) {
    return (
      <main className="shell">
        <Masthead pantryName={null} pantryLocation={null} current="queue" />
        <div className="fail">
          <p>
            The cases table did not answer, so this page cannot tell you whether
            anything on your shelves is under recall. Nothing here is cached and
            nothing is guessed.
          </p>
          <p className="data">{error}</p>
          <p className="data">
            {read.table} in {read.region}, pantry {read.pantry}, asked at{" "}
            {stamp(read.at)}.
          </p>
        </div>
      </main>
    );
  }

  const open = cases.filter((c) => c.status !== "notified");
  const closed = cases.filter((c) => c.status === "notified");
  const first = cases[0];
  const position = readPosition(cases);
  const shown = applyQuery(open, q);
  const groups = groupCases(shown);
  // A closed case that did not reach everyone is not finished, so it can never
  // hide behind the win state.
  const stillOwed = closed.filter(
    (c) =>
      c.delivery &&
      unreachedCount(deliveryLines(c.notify.recipients, c.delivery)) > 0,
  ).length;

  return (
    <main className="shell">
      <Masthead
        pantryName={first?.pantry_name ?? null}
        pantryLocation={first?.pantry_location ?? null}
        current="queue"
      />

      {open.length === 0 && stillOwed === 0 ? (
        <WinState closed={closed} />
      ) : (
        <>
          <Overview p={position} />

          <div className="block-head queue-head" id="matched-recalls">
            <h1 className="block-title">Matched recalls</h1>
            <span className="block-note">
              stamp first · one card per recall, in the order they have to be handled
            </span>
          </div>

          <Filters q={q} open={open} shown={shown.length} />

          {shown.length === 0 ? (
            <p className="queue-none">
              No open recall matches {describe(q).join(", ")}. The other{" "}
              {open.length} are still waiting.
            </p>
          ) : null}

          <div>
            {groups.map((g) => (
              <Record key={g.key} group={g} />
            ))}
          </div>
        </>
      )}

      {closed.length > 0 && !(open.length === 0 && stillOwed === 0) ? (
        <section className="closed">
          <div className="block-head">
            <h2 className="block-title">Closed</h2>
            <span className={`block-note${stillOwed > 0 ? " hz" : ""}`}>
              {stillOwed > 0
                ? `${plural(stillOwed, "recall", "recalls")} did not reach every household. Phone them.`
                : `${plural(closed.length, "recall", "recalls")} already notified, nothing left to decide`}
            </span>
          </div>
          {closed.map((c) => (
            <ClosedRow key={c.case_id} c={c} />
          ))}
        </section>
      ) : null}

      <Provenance read={read} rows={cases.length} />
    </main>
  );
}
