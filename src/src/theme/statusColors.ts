// Farben aus design/dashboard/Dashboard v2.dc.html.
//
// Das neue System kennt genau einen Akzent. Farbe bedeutet hier deshalb
// Zustand, nicht Zugehörigkeit: was Aufmerksamkeit braucht, ist farbig,
// alles andere bleibt neutral. Ein Board, auf dem jede Spalte leuchtet,
// sagt nichts darüber, wo man anfangen soll.

export const STATUS_COLORS: Record<string, string> = {
  open: "#6f7369", // wartet, aber ohne Frist im Nacken
  "in-progress": "#1f6b4f", // läuft gerade — der Akzent
  done: "#8b8f84", // erledigt, tritt zurück
  urgent: "#8a5a12", // Frist rückt heran
  overdue: "#8f3323", // Frist gerissen
  untagged: "#c9cbc2", // noch nicht eingeordnet
};

// Dokumentarten sind keine Zustände. Sie bekommen deshalb keine eigenen
// Signalfarben, sondern Stufen derselben warmen Grauachse — unterscheidbar
// genug für eine Legende, leise genug, um die Statusfarben nicht zu
// übertönen. Nur Rechtliches liegt auf dem Akzent, weil es als einzige
// Kategorie regelmäßig eine Frist mitbringt.
export const CATEGORY_COLORS: Record<string, string> = {
  invoice: "#52564c",
  contract: "#24261f",
  "maintenance-request": "#7c8076",
  legal: "#1f6b4f",
  correspondence: "#8b8f84",
  "tenant-notice": "#6f7369",
  insurance: "#a0a49a",
  "utility-bill": "#c9cbc2",
};

export function colorForTag(name: string, fallback: string): string {
  return STATUS_COLORS[name] ?? CATEGORY_COLORS[name] ?? fallback;
}
