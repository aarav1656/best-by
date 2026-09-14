import { NextResponse } from "next/server";

import { Refused, approveNotify, recordPull } from "@/lib/mutate";

export const dynamic = "force-dynamic";

/**
 * Two verbs, both of them things only a person standing in the pantry can assert.
 *
 * `pull` records that units physically came off a shelf, including when fewer came
 * back than the notice expected, because a short pull is the signal that some of the
 * recalled lot already left the building.
 *
 * `notify` records that the coordinator approved calling the households. It does not
 * send anything. The agent sends, because only the agent holds the SES message id
 * that proves a notice left.
 */
export async function POST(request: Request, context: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await context.params;

  let body: { action?: string; by?: string; units?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "The request body was not JSON." }, { status: 400 });
  }

  const by = (body.by ?? "").toString().trim() || "the coordinator";

  try {
    if (body.action === "pull") {
      const units = Number(body.units);
      if (!Number.isFinite(units) || units < 0 || !Number.isInteger(units)) {
        return NextResponse.json(
          { error: "Units has to be a whole number, including zero if nothing was found." },
          { status: 400 },
        );
      }
      const { item, short } = await recordPull(caseId, by, units);
      return NextResponse.json({
        ok: true,
        short,
        record: item.pull_record,
        message: short
          ? `Recorded. ${units} of ${item.pull.units} units came back, so the rest left the building before anyone looked.`
          : `Recorded. All ${units} units are off the shelf.`,
      });
    }

    if (body.action === "notify") {
      const item = await approveNotify(caseId, by);
      return NextResponse.json({
        ok: true,
        approved_at: item.approved_at,
        message:
          `Approved for ${item.notify.households} ` +
          `${item.notify.households === 1 ? "household" : "households"}. ` +
          "The next pass sends it, and nothing has reached anybody yet.",
      });
    }

    return NextResponse.json(
      { error: "Unknown action. This endpoint takes pull or notify." },
      { status: 400 },
    );
  } catch (error) {
    if (error instanceof Refused) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    return NextResponse.json(
      { error: `The write failed: ${(error as Error).message}` },
      { status: 500 },
    );
  }
}
