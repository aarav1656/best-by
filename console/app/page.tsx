import type { Metadata } from "next";
import Link from "next/link";
import { listCases, PANTRY_ID } from "@/lib/cases";
import { Case } from "@/lib/types";
import {
  deliveryLines,
  plural,
  primaryLot,
  productLine,
  unreachedCount,
  urgencyMark,
} from "@/lib/present";
import { Masthead } from "./masthead";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Best By: the decision queue",
  description:
    "Open recalls that touch this pantry's shelves, in the order they have to be handled.",
};

function Record({ c }: { c: Case }) {
  const lot = primaryLot(c);
  const pullUnits = c.pull.units;
  const notifyHouseholds = c.notify.households;
  const errands = c.needs_evidence.length;

  return (
    <Link href={`/case/${c.case_id}`} className="record">
      <div>
        <h2 className="record-head">{c.headline}</h2>
        {lot ? <p className="record-product">{productLine(lot)}</p> : null}
        <p className="record-hazard">{c.recall.reason}</p>

        <div className="obligations">
          {pullUnits > 0 ? (
            <div className="ob ob-pull">
              <div className="label">Pull</div>
              <div className="ob-count">
                {pullUnits}{" "}
                <span>{pullUnits === 1 ? "unit" : "units"}</span>
              </div>
              <div className="ob-where">
                {plural(c.pull.cases, "case", "cases")} in{" "}
                {c.pull.locations.join(", ")}
              </div>
            </div>
          ) : null}

          {notifyHouseholds > 0 ? (
            <div className="ob ob-notify">
              <div className="label">Notify</div>
              <div className="ob-count">
                {notifyHouseholds}{" "}
                <span>
                  {notifyHouseholds === 1 ? "household" : "households"}
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

          {errands > 0 ? (
            <div className="ob ob-look">
              <div className="label">Go look</div>
              <div className="ob-count">
                {errands}{" "}
                <span>{errands === 1 ? "lot" : "lots"}</span>
              </div>
              <div className="ob-where">
                {Array.from(
                  new Set(c.needs_evidence.map((l) => l.storage_location)),
                ).join(", ")}
              </div>
            </div>
          ) : null}
        </div>

        <span className="record-open">Open the case</span>
      </div>

      <div className="rail">
        <div className={`urgency u-${c.urgency}`}>{urgencyMark(c.urgency)}</div>
        <div className="micro">{c.recall.recall_number}</div>
        <div className={`micro${c.recall.class_i ? " class-i" : ""}`}>
          {c.recall.classification}
        </div>
        <div className="micro">{c.recall.firm_location}</div>
      </div>
    </Link>
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
        Nothing on the shelves is under recall right now.
      </p>
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

export default async function QueuePage() {
  const { cases, error } = await listCases();

  if (error) {
    return (
      <main className="shell">
        <Masthead pantryName={null} pantryLocation={null} />
        <div className="fail">
          <p>
            The cases table did not answer, so this page cannot tell you whether
            anything on your shelves is under recall. Nothing here is cached and
            nothing is guessed.
          </p>
          <p className="data">{error}</p>
        </div>
      </main>
    );
  }

  const open = cases.filter((c) => c.status !== "notified");
  const closed = cases.filter((c) => c.status === "notified");
  const first = cases[0];
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
      />

      {open.length === 0 && stillOwed === 0 ? (
        <WinState closed={closed} />
      ) : (
        <>
          <div className="queue-intro">
            <div>
              <h1 className="queue-title">
                Open recalls at {first?.pantry_name ?? PANTRY_ID}
              </h1>
              <p>
                One card per recall. Decide what comes off the shelf, and who
                gets a call.
              </p>
            </div>
            <div className="count">
              {plural(open.length, "open case", "open cases")}
            </div>
          </div>
          {open.length === 0 ? (
            <p className="queue-none">
              Nothing new needs a decision. The cases below went out already.
            </p>
          ) : null}
          <div>
            {open.map((c) => (
              <Record key={c.case_id} c={c} />
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

      <footer className="foot">
        <span className="micro">Source: openFDA food enforcement reports</span>
        <span className="micro">
          {open.length} needing a decision, {closed.length} closed, for{" "}
          {PANTRY_ID}
        </span>
      </footer>
    </main>
  );
}
