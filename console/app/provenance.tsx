import { stamp } from "@/lib/present";

/**
 * Which system produced the numbers above, and when it was asked.
 *
 * The openFDA credit names where the recall text came from. It does not say
 * where the rows came from, and those are two different claims. Nothing on
 * these pages is baked into the build, so the page has to be able to say so.
 */
export function Provenance({
  read,
  rows,
  noun = "cases",
}: {
  read: { table: string; region: string; pantry: string; at: string };
  rows: number;
  noun?: string;
}) {
  return (
    <footer className="foot">
      <span className="micro">
        Recall text from the openFDA food enforcement API.
      </span>
      <span className="micro">
        {rows} {noun} read from DynamoDB table {read.table} in {read.region},
        pantry {read.pantry}, at {stamp(read.at)}.
      </span>
    </footer>
  );
}
