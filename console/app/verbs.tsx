"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/**
 * The obligation blocks stop being labels and become the two things a coordinator
 * does on a shift. Everything here writes to the live table, so the row a person
 * just cleared is gone from the queue on the next render rather than sitting there
 * looking identical to the ones nobody has touched.
 *
 * The pull control asks how many units actually came back, defaulted to the number
 * the notice expects. Defaulting it means one tap for the normal case, and the field
 * is still there for the case that matters: fewer units than expected, meaning part
 * of the recalled lot already left the building.
 */

type Result = { ok: true; message: string; short?: boolean } | { ok: false; message: string };

function useVerb(caseId: string) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);

  async function run(action: string, extra: Record<string, unknown> = {}) {
    setBusy(action);
    setResult(null);
    try {
      const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action, by: "Morning recall pass volunteer", ...extra }),
      });
      const body = (await res.json()) as { error?: string; message?: string; short?: boolean };
      if (!res.ok) {
        setResult({ ok: false, message: body.error ?? `The write failed with status ${res.status}.` });
        setBusy(null);
        return;
      }
      setResult({ ok: true, message: body.message ?? "Recorded.", short: body.short });
      setBusy(null);
      router.refresh();
    } catch (error) {
      setResult({ ok: false, message: (error as Error).message });
      setBusy(null);
    }
  }

  return { busy, result, run };
}

export function PullVerb({
  caseId,
  units,
  cases,
  bay,
  lot,
  done,
}: {
  caseId: string;
  units: number;
  cases: number;
  bay: string;
  lot: string | null;
  done: { at: string; by: string; destroyed: number; expected: number; complete: boolean } | null;
}) {
  const { busy, result, run } = useVerb(caseId);
  const [back, setBack] = useState(String(units));

  if (done) {
    return (
      <div className="ob ob-pull verb-done">
        <div className="lbl">Pulled</div>
        <div className="verb-receipt">
          {done.destroyed} of {done.expected} units off {bay}
          {done.complete ? "" : `, short by ${done.expected - done.destroyed}`}
        </div>
        <div className="verb-stamp">
          {done.by} · {done.at.slice(0, 16).replace("T", " ")} UTC
          {lot ? ` · lot ${lot}` : ""}
        </div>
      </div>
    );
  }

  return (
    <div className="ob ob-pull">
      <div className="lbl">Pull</div>
      <div className="ob-count">
        {units} <span>units</span>
      </div>
      <div className="ob-where">
        {cases} {cases === 1 ? "case" : "cases"} in {bay}
        {lot ? (
          <>
            <br />
            lot <span className="verb-lot">{lot}</span>
          </>
        ) : null}
      </div>
      <div className="verb-row">
        <label className="verb-field">
          <span className="micro">units back</span>
          <input
            className="verb-input"
            inputMode="numeric"
            value={back}
            onChange={(e) => setBack(e.target.value.replace(/[^0-9]/g, ""))}
            aria-label="Units actually pulled off the shelf"
          />
        </label>
        <button
          type="button"
          className="btn"
          disabled={busy !== null || back === ""}
          onClick={() => run("pull", { units: Number(back) })}
        >
          {busy === "pull" ? "Recording" : "Mark pulled"}
        </button>
      </div>
      {result ? (
        <p className={result.ok ? "verb-note" : "verb-note verb-note-bad"}>{result.message}</p>
      ) : null}
    </div>
  );
}

export function NotifyVerb({
  caseId,
  households,
  units,
  children5,
  approvedAt,
  delivered,
}: {
  caseId: string;
  households: number;
  units: number;
  children5: number;
  approvedAt: string | null;
  delivered: boolean;
}) {
  const { busy, result, run } = useVerb(caseId);

  if (delivered) {
    return (
      <div className="ob ob-notify verb-done">
        <div className="lbl">Called</div>
        <div className="verb-receipt">
          {households} {households === 1 ? "household" : "households"} sent a notice
        </div>
        <div className="verb-stamp">Receipts are on the case</div>
      </div>
    );
  }

  if (approvedAt) {
    return (
      <div className="ob ob-notify verb-done">
        <div className="lbl">Approved</div>
        <div className="verb-receipt">
          {households} {households === 1 ? "household" : "households"} waiting on the next pass
        </div>
        <div className="verb-stamp">
          {approvedAt.slice(0, 16).replace("T", " ")} UTC · nothing sent yet
        </div>
      </div>
    );
  }

  return (
    <div className="ob ob-notify">
      <div className="lbl">Notify</div>
      <div className="ob-count">
        {households} <span>{households === 1 ? "household" : "households"}</span>
      </div>
      <div className="ob-where">
        {units} {units === 1 ? "unit" : "units"} already given out
        {children5 > 0 ? (
          <>
            <br />
            <span className="under5">{children5} with a child under 5</span>
          </>
        ) : null}
      </div>
      <div className="verb-row">
        <button
          type="button"
          className="btn"
          disabled={busy !== null}
          onClick={() => run("notify")}
        >
          {busy === "notify" ? "Recording" : "Approve the calls"}
        </button>
      </div>
      {result ? (
        <p className={result.ok ? "verb-note" : "verb-note verb-note-bad"}>{result.message}</p>
      ) : null}
    </div>
  );
}
