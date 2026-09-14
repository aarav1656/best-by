import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  GetCommand,
  QueryCommand,
} from "@aws-sdk/lib-dynamodb";
import { Case, URGENCY_ORDER, Urgency } from "./types";

export const PANTRY_ID = process.env.BESTBY_PANTRY_ID ?? "riverbend-dayton";
const TABLE = process.env.BESTBY_TABLE ?? "bestby-cases";
const REGION = process.env.BESTBY_AWS_REGION ?? "us-east-1";

function client(): DynamoDBDocumentClient {
  const accessKeyId = process.env.BESTBY_AWS_ACCESS_KEY_ID;
  const secretAccessKey = process.env.BESTBY_AWS_SECRET_ACCESS_KEY;
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
  };
}

export interface QueueResult {
  cases: Case[];
  error: string | null;
}

export async function listCases(): Promise<QueueResult> {
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
    return { cases, error: null };
  } catch (e) {
    return { cases: [], error: e instanceof Error ? e.message : String(e) };
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
