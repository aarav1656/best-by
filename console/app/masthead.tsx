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
  return (
    <header className="masthead">
      <div className="masthead-left">
        <div className="masthead-name">Best By</div>
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
        {pantryName ?? "Pantry"}
        {pantryLocation ? `, ${pantryLocation}` : ""}
        <br />
        FDA food enforcement feed against the intake log
      </div>
    </header>
  );
}
