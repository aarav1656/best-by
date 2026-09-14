import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Best By: no such case",
};

export default function NotFound() {
  return (
    <main className="shell">
      <div className="win">
        <p className="win-statement">
          There is no case with that id in this pantry&apos;s table.
        </p>
        <Link href="/" className="back">
          Back to the queue
        </Link>
      </div>
    </main>
  );
}
