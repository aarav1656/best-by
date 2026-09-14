import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, GetCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";

import { PANTRY_ID, REGION, TABLE } from "./cases";
import type { Case, TimelineEvent } from "./types";

/**
 * The console's write path.
 *
 * A coordinator standing at a shelf is the only person who can say the units
 * actually came off it. That fact does not exist anywhere until they record it,
 * which is why this file exists: reading a queue is not the job, clearing it is.
 *
 * Both writes are conditional on the status the reader saw. If a scheduled pass
 * moved the case between the render and the click, the condition fails and the
 * coordinator is told, rather than silently overwriting a newer truth.
 */

function client(): DynamoDBDocumentClient {
  const accessKeyId = process.env.BESTBY_AWS_ACCESS_KEY_ID?.trim();
  const secretAccessKey = process.env.BESTBY_AWS_SECRET_ACCESS_KEY?.trim();
  const base = new DynamoDBClient({
    region: REGION,
    credentials: accessKeyId && secretAccessKey ? { accessKeyId, secretAccessKey } : undefined,
  });
  return DynamoDBDocumentClient.from(base, {
    marshallOptions: { removeUndefinedValues: true },
  });
}

function now(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function entry(event: string, detail: string): TimelineEvent {
  return { at: now(), event, detail };
}

export class Refused extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function readCase(caseId: string): Promise<Case> {
  const out = await client().send(
    new GetCommand({ TableName: TABLE, Key: { pantry_id: PANTRY_ID, case_id: caseId } }),
  );
  if (!out.Item) {
    throw new Refused("No case with that id in this pantry's table.", 404);
  }
  return out.Item as Case;
}

/**
 * `expected` is the status the page rendered. The write refuses if the row has
 * moved on, so two coordinators on two phones cannot both mark the same pull.
 */
async function move(
  caseId: string,
  expected: string,
  status: string,
  events: TimelineEvent[],
  extra: Record<string, unknown> = {},
): Promise<Case> {
  const names: Record<string, string> = { "#s": "status", "#t": "timeline", "#u": "updated_at" };
  const values: Record<string, unknown> = {
    ":s": status,
    ":expected": expected,
    ":t": events,
    ":empty": [] as TimelineEvent[],
    ":u": now(),
  };
  const sets = ["#s = :s", "#t = list_append(if_not_exists(#t, :empty), :t)", "#u = :u"];

  let i = 0;
  for (const [key, value] of Object.entries(extra)) {
    const n = `#x${i}`;
    const v = `:x${i}`;
    names[n] = key;
    values[v] = value;
    sets.push(`${n} = ${v}`);
    i += 1;
  }

  try {
    const out = await client().send(
      new UpdateCommand({
        TableName: TABLE,
        Key: { pantry_id: PANTRY_ID, case_id: caseId },
        UpdateExpression: `SET ${sets.join(", ")}`,
        ConditionExpression: "#s = :expected",
        ExpressionAttributeNames: names,
        ExpressionAttributeValues: values,
        ReturnValues: "ALL_NEW",
      }),
    );
    return out.Attributes as Case;
  } catch (error) {
    if ((error as { name?: string }).name === "ConditionalCheckFailedException") {
      throw new Refused(
        "This case moved while the page was open. Reload to see where it stands now.",
        409,
      );
    }
    throw error;
  }
}

/**
 * The shelf half. The coordinator says the units are off the shelf and how many
 * actually came back, because a short pull is the interesting case: it means part
 * of the recalled lot left the building before anyone looked.
 */
export async function recordPull(
  caseId: string,
  by: string,
  unitsBack: number,
): Promise<{ item: Case; short: boolean }> {
  const item = await readCase(caseId);
  if (item.pull_record) {
    throw new Refused("This pull was already recorded.", 409);
  }
  if (!item.pull || item.pull.units === 0) {
    throw new Refused("This case has nothing to pull off a shelf.", 409);
  }

  const expected = item.pull.units;
  const short = unitsBack < expected;
  const record = {
    at: now(),
    pulled_by: by,
    units_expected: expected,
    units_destroyed: unitsBack,
    complete: !short,
  };

  const detail = short
    ? `${by} pulled ${unitsBack} of ${expected} units. The pull is short by ${expected - unitsBack}.`
    : `${by} pulled all ${unitsBack} units off the shelf.`;

  // Status is not a pull state. `pull_record` is the fact, and the queue reads it,
  // so recording a pull never invents a status the rest of the system cannot parse.
  const updated = await move(caseId, item.status, item.status, [entry("pulled", detail)], {
    pull_record: record,
  });
  return { item: updated, short };
}

/**
 * The kitchens half, and the irreversible one. This records the coordinator's
 * approval and nothing else. It never writes `notified` and never writes a message
 * id, because a message id is proof a notice left and only the agent that called
 * SES holds one. A console that could stamp `notified` could claim a household was
 * warned when nobody was.
 */
export async function approveNotify(caseId: string, by: string): Promise<Case> {
  const item = await readCase(caseId);
  if (item.notify.households === 0) {
    throw new Refused("No household took any of this lot home, so there is nobody to call.", 409);
  }
  if (item.delivery) {
    throw new Refused("These households were already sent a notice.", 409);
  }
  if (item.approved_at) {
    throw new Refused("This notice is already approved and waiting on the next pass.", 409);
  }

  const households = item.notify.households;
  const kids = item.notify.children_under_5;
  const detail =
    `${by} approved the notice to ${households} ${households === 1 ? "household" : "households"}` +
    (kids > 0 ? `, ${kids} with a child under 5.` : ".") +
    " The next pass sends it. Nothing has reached anybody yet.";

  return move(caseId, item.status, item.status, [entry("approval.granted", detail)], {
    approved_at: now(),
    approved_by: by,
  });
}
