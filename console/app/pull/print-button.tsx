"use client";

/**
 * The sheet is meant to leave the screen. The browser's own print dialog is the
 * only thing that can start that, so this is the one button in the console that
 * needs the browser.
 */
export function PrintButton() {
  return (
    <button type="button" className="btn" onClick={() => window.print()}>
      Print this sheet
    </button>
  );
}
