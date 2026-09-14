import type { Metadata } from "next";
import Link from "next/link";
import { listCases } from "@/lib/cases";
import { plural, productLine, stamp } from "@/lib/present";
import { byBay, readPosition, ShelfLot } from "@/lib/position";
import { Masthead } from "../masthead";
import { Provenance } from "../provenance";
import { PrintButton } from "./print-button";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Best By: the pull sheet",
  description:
    "Every recalled lot still on this pantry's shelves, grouped by bay, checkable and printable.",
};

function LotRow({ row }: { row: ShelfLot }) {
  const lot = row.lot;
  return (
    <label className="pull-row">
      <input type="checkbox" className="tick" />
      <span className="pull-body">
        <span className="pull-product">{productLine(lot)}</span>
        <span className="pull-facts">
          <span className="pull-fact">
            <span className="label">Lot code</span>
            <span className="pull-code">{lot.lot_code ?? "none printed"}</span>
          </span>
          <span className="pull-fact">
            <span className="label">Take</span>
            <span className="data">
              {plural(lot.cases_on_hand, "case", "cases")}, {lot.units_on_hand}{" "}
              units
            </span>
          </span>
          <span className="pull-fact">
            <span className="label">Best by</span>
            <span className="data">{lot.best_by ?? "not recorded"}</span>
          </span>
          <span className="pull-fact">
            <span className="label">Intake</span>
            <span className="data">{lot.lot_id}</span>
          </span>
          <span className="pull-fact">
            <span className="label">
              {row.recalls.length === 1 ? "Notice" : "Notices"}
            </span>
            <span className="data">{row.recalls.join(", ")}</span>
          </span>
        </span>
      </span>
    </label>
  );
}

function ErrandRow({ row }: { row: ShelfLot }) {
  const lot = row.lot;
  const missing = row.missing;
  return (
    <label className="pull-row pull-row-look">
      <input type="checkbox" className="tick" />
      <span className="pull-body">
        <span className="pull-product">{productLine(lot)}</span>
        <span className="pull-errands">
          {missing.map((m) => (
            <span className="pull-errand" key={m}>
              {m}
            </span>
          ))}
        </span>
        <span className="pull-facts">
          <span className="pull-fact">
            <span className="label">On hand</span>
            <span className="data">
              {plural(lot.cases_on_hand, "case", "cases")}, {lot.units_on_hand}{" "}
              units
            </span>
          </span>
          <span className="pull-fact">
            <span className="label">Intake</span>
            <span className="data">{lot.lot_id}</span>
          </span>
          <span className="pull-fact">
            <span className="label">
              {row.recalls.length === 1 ? "Notice" : "Notices"}
            </span>
            <span className="data">{row.recalls.join(", ")}</span>
          </span>
        </span>
      </span>
    </label>
  );
}

export default async function PullSheet({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const raw = params.bay;
  const bayFilter = Array.isArray(raw) ? raw[0] : (raw ?? null);
  const { cases, error, read } = await listCases();
  const first = cases[0];

  if (error) {
    return (
      <main className="shell">
        <Masthead pantryName={null} pantryLocation={null} current="pull" />
        <div className="fail">
          <p>
            The cases table did not answer, so there is no pull sheet to print.
            An out of date printout is worse than none, so nothing is cached
            here.
          </p>
          <p className="data">{error}</p>
        </div>
      </main>
    );
  }

  const p = readPosition(cases);
  const allBays = byBay(p.pullLots);
  const bays = bayFilter
    ? allBays.filter((b) => b.name === bayFilter)
    : allBays;
  const lookBays = bayFilter
    ? byBay(p.checkLots).filter((b) => b.name === bayFilter)
    : byBay(p.checkLots);
  const units = bays.reduce((n, b) => n + b.units, 0);
  const caseCount = bays.reduce((n, b) => n + b.cases, 0);
  const lookCount = lookBays.reduce((n, b) => n + b.lots.length, 0);

  // A zero is a thing to read and an absence is not, so a sheet with nothing to
  // read by hand says nothing about reading by hand.
  const take =
    bays.length === 0
      ? null
      : `Take ${units} units off ${
          bays.length === 1 ? "one bay" : `${bays.length} bays`
        }`;
  const look =
    lookCount === 0
      ? null
      : `read ${plural(lookCount, "lot", "lots")} by hand`;
  const statement = take
    ? look
      ? `${take}, and ${look}.`
      : `${take}.`
    : look
      ? `${look[0].toUpperCase()}${look.slice(1)}.`
      : bayFilter
        ? `Nothing in ${bayFilter} is named by an open notice.`
        : "There is nothing to take off the shelf.";

  return (
    <main className="shell">
      <Masthead
        pantryName={first?.pantry_name ?? null}
        pantryLocation={first?.pantry_location ?? null}
        current="pull"
      />

      <div className="print-head">
        <div className="print-title">Best By pull sheet</div>
        <div className="print-meta">
          {first?.pantry_name ?? read.pantry}
          {first?.pantry_location ? `, ${first.pantry_location}` : ""} ·{" "}
          {caseCount} cases, {units} units, {bays.length}{" "}
          {bays.length === 1 ? "bay" : "bays"} · read from {read.table} at{" "}
          {stamp(read.at)}
        </div>
      </div>

      <div className="sheet-head">
        <div className="label">
          Pull sheet, read at {stamp(read.at)}
        </div>
        <h1 className="sheet-statement">{statement}</h1>
        <p className="sheet-sub">
          Every row is one intake lot that a live FDA notice names. Tick it when
          the cases are off the shelf and in the destroy bin. A lot appears once
          however many notices name it.
        </p>

        <div className="sheet-acts">
          <PrintButton />
          <Link className="act-link" href="/">
            Back to the queue
          </Link>
        </div>

        {allBays.length > 1 ? (
          <div className="filter-row sheet-bays">
            <span className="label">Bay</span>
            <div className="chips">
              <Link className={`chip${bayFilter ? "" : " on"}`} href="/pull">
                every bay {allBays.length}
              </Link>
              {allBays.map((b) => (
                <Link
                  key={b.name}
                  className={`chip${bayFilter === b.name ? " on" : ""}`}
                  href={
                    bayFilter === b.name
                      ? "/pull"
                      : `/pull?bay=${encodeURIComponent(b.name)}`
                  }
                >
                  {b.name} {b.units}
                </Link>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      {bays.map((bay) => (
        <section className="bay" key={bay.name}>
          <div className="block-head">
            <h2 className="block-title">{bay.name}</h2>
            <span className="block-note">
              {plural(bay.cases, "case", "cases")}, {bay.units} units,{" "}
              {plural(bay.lots.length, "lot", "lots")}
            </span>
          </div>
          {bay.lots.map((row) => (
            <LotRow key={row.lot.lot_id} row={row} />
          ))}
        </section>
      ))}

      {bays.length === 0 ? (
        <p className="queue-none">
          Nothing on {bayFilter ?? "these shelves"} is named by an open notice
          with a code this pantry can check.
          {lookCount > 0
            ? " The lots below still have to be read by hand."
            : " Every lot here was compared against a recalled code and stays where it is."}
        </p>
      ) : null}

      {lookBays.map((bay) => (
        <section className="bay bay-look" key={`look-${bay.name}`}>
          <div className="block-head">
            <h2 className="block-title">{bay.name}, read by hand</h2>
            <span className="block-note">
              {plural(bay.lots.length, "lot", "lots")} the notice cannot decide
              without a photograph
            </span>
          </div>
          {bay.lots.map((row) => (
            <ErrandRow key={row.lot.lot_id} row={row} />
          ))}
        </section>
      ))}

      {/* Nothing to pull is nothing to sign for. */}
      {units > 0 ? (
      <section className="signoff">
        <div className="label">When the cart comes back</div>
        <div className="signoff-grid">
          <div className="signoff-field">
            <span className="label">Pulled by</span>
            <span className="rule-line" />
          </div>
          <div className="signoff-field">
            <span className="label">Units destroyed</span>
            <span className="rule-line" />
          </div>
          <div className="signoff-field">
            <span className="label">Date and time</span>
            <span className="rule-line" />
          </div>
        </div>
        <p className="signoff-note micro">
          {units} units are expected. A pull that comes back short is recorded
          as short, never as done.
        </p>
      </section>
      ) : null}

      <Provenance read={read} rows={cases.length} />
    </main>
  );
}
