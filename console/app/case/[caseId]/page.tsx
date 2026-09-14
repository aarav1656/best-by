import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getCase } from "@/lib/cases";
import { Check, LANGUAGE_NAME, Lot } from "@/lib/types";
import {
  evidenceBucket,
  plural,
  productLine,
  stamp,
  urgencyMark,
} from "@/lib/present";
import { Masthead } from "../../masthead";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ caseId: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { caseId } = await params;
  const c = await getCase(caseId);
  if (!c) return { title: "Best By: case not found" };
  return {
    title: `Best By: ${c.recall.recall_number}, ${c.headline}`,
    description: c.recall.reason,
  };
}

function Field({
  label,
  value,
  hazard,
}: {
  label: string;
  value: string;
  hazard?: boolean;
}) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd className={hazard ? "hz" : undefined}>{value}</dd>
    </div>
  );
}

function CheckRow({ check }: { check: Check }) {
  return (
    <div className={`check ${check.passed ? "passed" : "failed"}`}>
      <span className="check-mark">{check.passed ? "yes" : "no"}</span>
      <span className="check-name">{check.name.replace(/_/g, " ")}</span>
      <span className="check-detail">{check.detail}</span>
    </div>
  );
}

function LotBlock({ lot }: { lot: Lot }) {
  return (
    <article className="lot">
      <div className="lot-top">
        <h3 className="lot-product">{productLine(lot)}</h3>
        <div className="lot-bay">{lot.storage_location}</div>
      </div>

      <dl className="lot-grid">
        <Field label="Cases on hand" value={String(lot.cases_on_hand)} />
        <Field
          label="Units on hand"
          value={`${lot.units_on_hand} (${lot.units_per_case} per case)`}
        />
        <Field label="Lot code" value={lot.lot_code ?? "none printed"} />
        <Field label="Best by" value={lot.best_by ?? "not recorded"} />
        <Field label="Intake lot" value={lot.lot_id} />
        <Field label="Received" value={lot.received_on ?? "not recorded"} />
        <Field
          label="Already given out"
          value={plural(lot.units_distributed, "unit", "units")}
          hazard={lot.units_distributed > 0}
        />
        <Field label="Donor" value={lot.donor ?? "not recorded"} />
      </dl>

      <div className="checks">
        {lot.checks.map((ch) => (
          <CheckRow key={`${lot.lot_id}-${ch.name}`} check={ch} />
        ))}
      </div>
      <p className="decided">
        Decided by {lot.decided_by.replace(/_/g, " ")}. Evidence id{" "}
        {lot.evidence_id}.
      </p>
    </article>
  );
}

export default async function CasePage({ params }: Params) {
  const { caseId } = await params;
  const c = await getCase(caseId);
  if (!c) notFound();

  const r = c.recall;

  return (
    <main className="shell">
      <Masthead pantryName={c.pantry_name} pantryLocation={c.pantry_location} />

      <Link href="/" className="back">
        Back to the queue
      </Link>

      <div className="case-head">
        <div className={`urgency u-${c.urgency}`}>{urgencyMark(c.urgency)}</div>
        <h1 className="case-headline">{c.headline}</h1>
        <p className="case-hazard">{r.reason}</p>

        <dl className="case-facts">
          <Field label="Recall number" value={r.recall_number} />
          <Field
            label="Classification"
            value={r.classification}
            hazard={r.class_i}
          />
          <Field label="Recall status" value={r.recall_status} />
          <Field label="Firm" value={r.firm} />
          <Field label="Firm location" value={r.firm_location} />
          <Field label="Recall date" value={r.recall_date ?? "not published"} />
          <Field label="Report date" value={r.report_date ?? "not published"} />
          <Field label="Recalled quantity" value={r.quantity ?? "not published"} />
          <Field label="Distribution" value={r.distribution_pattern} />
          <Field label="Case status" value={c.status.replace(/_/g, " ")} />
        </dl>
      </div>

      <section className="block">
        <div className="block-head">
          <h2 className="block-title">The notice</h2>
          <span className="block-note">from {r.source}</span>
        </div>
        <p className="notice">{r.title}</p>
      </section>

      {c.pull.lots.length > 0 ? (
        <section className="block">
          <div className="block-head">
            <h2 className="block-title">Pull list</h2>
            <span className="block-note">
              {plural(c.pull.cases, "case", "cases")},{" "}
              {plural(c.pull.units, "unit", "units")},{" "}
              {c.pull.locations.join(", ")}
            </span>
          </div>
          {c.pull.lots.map((lot) => (
            <LotBlock key={lot.lot_id} lot={lot} />
          ))}
        </section>
      ) : null}

      {c.needs_evidence.length > 0 ? (
        <section className="block">
          <div className="block-head">
            <h2 className="block-title">Go look at the shelf</h2>
            <span className="block-note">
              {plural(c.needs_evidence.length, "lot", "lots")} cannot be decided
              from the notice alone
            </span>
          </div>
          {c.needs_evidence.map((lot) => (
            <div key={lot.lot_id}>
              <div className="errand">
                <div className="errand-bay">{lot.storage_location}</div>
                <p className="errand-product">{productLine(lot)}</p>
                <div className="errand-items">
                  {lot.missing.map((m, i) => (
                    <div className="errand-item" key={m}>
                      <span>{i + 1}.</span>
                      <span>{m}</span>
                    </div>
                  ))}
                </div>
              </div>
              <LotBlock lot={lot} />
            </div>
          ))}
        </section>
      ) : null}

      {c.notify.recipients.length > 0 ? (
        <section className="block">
          <div className="block-head">
            <h2 className="block-title">Notify list</h2>
            <span className="block-note">
              {plural(c.notify.households, "household", "households")},{" "}
              {plural(c.notify.units, "unit", "units")} already in kitchens
              {c.notify.children_under_5 > 0
                ? `, ${c.notify.children_under_5} with a child under 5`
                : ""}
            </span>
          </div>
          <table className="households">
            <thead>
              <tr>
                <th>Household</th>
                <th>Name</th>
                <th className="num">Units</th>
                <th>Last given</th>
                <th className="num">Under 5</th>
                <th>Language</th>
              </tr>
            </thead>
            <tbody>
              {c.notify.recipients.map((h) => (
                <tr key={h.household_id}>
                  <td className="id">{h.household_id}</td>
                  <td>{h.name}</td>
                  <td className="num">{h.units}</td>
                  <td>{h.last_given_on ?? "not recorded"}</td>
                  <td
                    className={`num ${h.children_under_5 > 0 ? "hz" : ""}`.trim()}
                  >
                    {h.children_under_5 > 0 ? h.children_under_5 : ""}
                  </td>
                  <td>{LANGUAGE_NAME[h.language] ?? h.language}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {c.notice_text ? (
        <section className="block">
          <div className="block-head">
            <h2 className="block-title">Drafted notice</h2>
            <span className="block-note">sent to each household above</span>
          </div>
          <p className="notice">{c.notice_text}</p>
        </section>
      ) : null}

      <section className="block">
        <div className="block-head">
          <h2 className="block-title">Record</h2>
          <span className="block-note">case {c.case_id}</span>
        </div>
        <div className="timeline">
          {c.timeline.map((t, i) => (
            <div className="tl-row" key={`${t.at}-${t.event}-${i}`}>
              <span>{stamp(t.at)}</span>
              <span className="ev">{t.event.replace(/_/g, " ")}</span>
              <span>{t.detail}</span>
            </div>
          ))}
        </div>
        <dl className="case-facts">
          <Field label="Opened" value={stamp(c.created_at)} />
          <Field label="Updated" value={stamp(c.updated_at)} />
          {c.evidence_uri ? (
            <Field
              label="Compliance record"
              value={evidenceBucket(c.evidence_uri)}
            />
          ) : null}
        </dl>
      </section>

      <footer className="foot">
        <span className="micro">Source: openFDA food enforcement reports</span>
        <span className="micro">
          {c.pantry_name}, {c.pantry_location}
        </span>
      </footer>
    </main>
  );
}
