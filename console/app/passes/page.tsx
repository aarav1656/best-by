import type { Metadata } from "next";
import Link from "next/link";
import { countNoticesOnFile, listCases, RECALLS_TABLE } from "@/lib/cases";
import { plural, stamp, stampExact } from "@/lib/present";
import { Pass, eventWord, reconstructPasses } from "@/lib/passes";
import { Masthead } from "../masthead";
import { Provenance } from "../provenance";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Best By: what the agent did",
  description:
    "Every pass the agent has made over this pantry's shelves, read out of the case timelines it wrote.",
};

function PassBlock({ pass, latest }: { pass: Pass; latest: boolean }) {
  return (
    <section className="pass">
      <div className="block-head">
        <h2 className="block-title">{stampExact(pass.at)}</h2>
        <span className="block-note">
          {latest ? "latest pass, " : ""}
          {plural(pass.cases, "case", "cases")} touched
        </span>
      </div>

      {pass.tally.length > 0 ? (
        <p className="pass-tally">
          {pass.tally.map((t, i) => (
            <span key={t.event}>
              {i > 0 ? ", " : ""}
              <span className="fig">{t.n}</span> {eventWord(t.event, t.n)}
            </span>
          ))}
          .
        </p>
      ) : (
        <p className="pass-tally pass-tally-quiet">
          Read every case and changed nothing.
        </p>
      )}

      <div className="pass-opened">
        {pass.opened.map((e) => (
          <Link className="pass-row" key={e.caseId} href={`/case/${e.caseId}`}>
            <span className="pass-recall">{e.recallNumber}</span>
            <span className="pass-headline">{e.headline}</span>
            <span className="pass-detail">{e.detail}</span>
          </Link>
        ))}
      </div>

      {pass.actions.length > 0 ? (
        <details className="pass-actions">
          <summary>
            {plural(pass.actions.length, "action", "actions")} taken in this
            pass
          </summary>
          <div className="pass-log">
            {pass.actions.map((e, i) => (
              <div className="pass-log-row" key={`${e.at}-${e.caseId}-${i}`}>
                <span className="micro">{stampExact(e.at)}</span>
                <span className="ev">{e.event.replace(/_/g, " ")}</span>
                <span className="pass-log-detail">
                  <span className="pass-recall">{e.recallNumber}</span>{" "}
                  {e.detail}
                </span>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}

export default async function PassesPage() {
  const [{ cases, error, read }, notices] = await Promise.all([
    listCases(),
    countNoticesOnFile(),
  ]);
  const first = cases[0];

  if (error) {
    return (
      <main className="shell">
        <Masthead pantryName={null} pantryLocation={null} current="passes" />
        <div className="fail">
          <p>
            The cases table did not answer, so this page cannot show you when
            the agent last ran. The schedule may still be running. This page
            simply does not know.
          </p>
          <p className="data">{error}</p>
        </div>
      </main>
    );
  }

  const passes = reconstructPasses(cases);
  const events = cases.reduce((n, c) => n + c.timeline.length, 0);
  const last = passes[0];

  return (
    <main className="shell">
      <Masthead
        pantryName={first?.pantry_name ?? null}
        pantryLocation={first?.pantry_location ?? null}
        current="passes"
      />

      <div className="sheet-head">
        <div className="label">Passes on record</div>
        <h1 className="sheet-statement">
          {last ? (
            <>
              The last pass ran at <span className="fig">{stamp(last.at)}</span>{" "}
              and read <span className="fig">{last.cases}</span>{" "}
              {last.cases === 1 ? "case" : "cases"}.
            </>
          ) : (
            "No pass has written anything to a case yet."
          )}
        </h1>
        <p className="sheet-sub">
          There is no separate run log. A pass proves itself by writing the same
          timestamp into every case it read, so this page is reconstructed from
          the case timelines and every string below is the agent&apos;s own
          wording, unedited.
        </p>

        <dl className="figures">
          <div className="figure">
            <dt>Passes</dt>
            <dd>
              <span className="figure-n">{passes.length}</span>
              <span className="figure-note">
                each one a timestamp shared across cases
              </span>
            </dd>
          </div>
          <div className="figure">
            <dt>Notices on file</dt>
            <dd>
              <span className="figure-n">{notices ?? 0}</span>
              <span className="figure-note">
                {notices === null
                  ? `${RECALLS_TABLE} did not answer`
                  : `every FDA notice screened, in ${RECALLS_TABLE}`}
              </span>
            </dd>
          </div>
          <div className="figure">
            <dt>Cases opened</dt>
            <dd>
              <span className="figure-n">{cases.length}</span>
              <span className="figure-note">
                notices that reached a shelf in this pantry
              </span>
            </dd>
          </div>
          <div className="figure">
            <dt>Events written</dt>
            <dd>
              <span className="figure-n">{events}</span>
              <span className="figure-note">
                across every case timeline
              </span>
            </dd>
          </div>
        </dl>

        <div className="sheet-acts">
          <Link className="act-link" href="/">
            Back to the queue
          </Link>
        </div>
      </div>

      {passes.map((pass, i) => (
        <PassBlock key={pass.at} pass={pass} latest={i === 0} />
      ))}

      <Provenance read={read} rows={cases.length} />
    </main>
  );
}
