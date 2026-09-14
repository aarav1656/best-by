import Link from "next/link";

const ROUTES: { href: string; label: string; key: string }[] = [
  { href: "/", label: "Queue", key: "queue" },
  { href: "/pull", label: "Pull sheet", key: "pull" },
  { href: "/passes", label: "Passes", key: "passes" },
];

export function Masthead({
  pantryName,
  pantryLocation,
  current,
}: {
  pantryName: string | null;
  pantryLocation: string | null;
  current?: string;
}) {
  const pantry = pantryName ?? "Pantry";
  return (
    <header className="masthead">
      <div className="masthead-left">
        <div className="masthead-name">
          Best By <span className="masthead-pantry-inline">· {pantry}</span>
        </div>
        <nav className="masthead-nav">
          {ROUTES.map((r) => (
            <Link
              key={r.key}
              href={r.href}
              className={`nav-link${current === r.key ? " here" : ""}`}
              aria-current={current === r.key ? "page" : undefined}
            >
              {r.label}
            </Link>
          ))}
        </nav>
      </div>
      <div className="masthead-pantry">
        {pantryLocation ? `${pantryLocation}` : ""}
        {pantryLocation ? <br /> : null}
        Lot codes on the case, matched to the FDA feed
      </div>
    </header>
  );
}
