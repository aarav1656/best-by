export function Masthead({
  pantryName,
  pantryLocation,
}: {
  pantryName: string | null;
  pantryLocation: string | null;
}) {
  return (
    <header className="masthead">
      <div className="masthead-name">Best By</div>
      <div className="masthead-pantry">
        {pantryName ?? "Pantry"}
        {pantryLocation ? `, ${pantryLocation}` : ""}
        <br />
        FDA food enforcement feed against the intake log
      </div>
    </header>
  );
}
