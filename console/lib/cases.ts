import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  GetCommand,
  QueryCommand,
} from "@aws-sdk/lib-dynamodb";
import { Case, URGENCY_ORDER, Urgency } from "./types";

export const PANTRY_ID = process.env.BESTBY_PANTRY_ID ?? "riverbend-dayton";
export const TABLE = process.env.BESTBY_TABLE ?? "bestby-cases";
export const RECALLS_TABLE =
  process.env.BESTBY_RECALLS_TABLE ?? "bestby-recalls";
export const REGION = process.env.BESTBY_AWS_REGION?.trim() || "us-east-1";

function client(): DynamoDBDocumentClient {
  const accessKeyId = process.env.BESTBY_AWS_ACCESS_KEY_ID?.trim();
  const secretAccessKey = process.env.BESTBY_AWS_SECRET_ACCESS_KEY?.trim();
  const base = new DynamoDBClient({
    region: REGION,
    credentials:
      accessKeyId && secretAccessKey
        ? { accessKeyId, secretAccessKey }
        : undefined,
  });
  return DynamoDBDocumentClient.from(base, {
    marshallOptions: { removeUndefinedValues: true },
  });
}

function normalise(raw: Record<string, unknown>): Case {
  const c = raw as unknown as Case;
  return {
    ...c,
    pull: {
      cases: c.pull?.cases ?? 0,
      units: c.pull?.units ?? 0,
      locations: c.pull?.locations ?? [],
      lots: c.pull?.lots ?? [],
    },
    notify: {
      households: c.notify?.households ?? 0,
      units: c.notify?.units ?? 0,
      children_under_5: c.notify?.children_under_5 ?? 0,
      recipients: c.notify?.recipients ?? [],
    },
    needs_evidence: c.needs_evidence ?? [],
    timeline: c.timeline ?? [],
    delivery: c.delivery
      ? { ...c.delivery, messages: c.delivery.messages ?? [] }
      : null,
    pull_record: c.pull_record ?? null,
  };
}

export interface QueueResult {
  cases: Case[];
  error: string | null;
  /** Where the rows above came from, so the footer can attest it. */
  read: { table: string; region: string; pantry: string; at: string };
}

export async function listCases(): Promise<QueueResult> {
  const read = {
    table: TABLE,
    region: REGION,
    pantry: PANTRY_ID,
    at: new Date().toISOString(),
  };
  try {
    const out = await client().send(
      new QueryCommand({
        TableName: TABLE,
        KeyConditionExpression: "pantry_id = :p",
        ExpressionAttributeValues: { ":p": PANTRY_ID },
      }),
    );
    const cases = (out.Items ?? []).map((i) =>
      normalise(i as Record<string, unknown>),
    );
    cases.sort((a, b) => {
      const ua = URGENCY_ORDER[a.urgency as Urgency] ?? 9;
      const ub = URGENCY_ORDER[b.urgency as Urgency] ?? 9;
      if (ua !== ub) return ua - ub;
      const pa = a.pull.units + a.notify.units;
      const pb = b.pull.units + b.notify.units;
      if (pa !== pb) return pb - pa;
      return a.recall.recall_number.localeCompare(b.recall.recall_number);
    });
    return { cases, error: null, read };
  } catch (e) {
    return {
      cases: [],
      error: e instanceof Error ? e.message : String(e),
      read,
    };
  }
}

/**
 * How many FDA notices this pantry has been screened against. Every notice the
 * pass has ever read is recorded, matched or not, so this is the denominator
 * behind the ten cases on the queue.
 */
export async function countNoticesOnFile(): Promise<number | null> {
  try {
    let seen = 0;
    let cursor: Record<string, unknown> | undefined;
    do {
      const out = await client().send(
        new QueryCommand({
          TableName: RECALLS_TABLE,
          KeyConditionExpression: "#s = :s",
          ExpressionAttributeNames: { "#s": "source" },
          ExpressionAttributeValues: { ":s": "openFDA" },
          ProjectionExpression: "recall_number",
          ExclusiveStartKey: cursor,
        }),
      );
      seen += out.Count ?? 0;
      cursor = out.LastEvaluatedKey;
    } while (cursor);
    return seen;
  } catch {
    return null;
  }
}

export async function getCase(caseId: string): Promise<Case | null> {
  const out = await client().send(
    new GetCommand({
      TableName: TABLE,
      Key: { pantry_id: PANTRY_ID, case_id: caseId },
    }),
  );
  if (!out.Item) return null;
  return normalise(out.Item as Record<string, unknown>);
}
