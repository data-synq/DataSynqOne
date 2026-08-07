// Farben aus design/dashboard/Dashboard v3.dc.html.
//
// Das System kennt genau einen Akzent. Farbe bedeutet hier deshalb
// Zustand, nicht Zugehörigkeit: was Aufmerksamkeit braucht, ist farbig,
// alles andere bleibt neutral. Eine Liste, in der jede Zeile leuchtet,
// sagt nichts darüber, wo man anfangen soll.

export const STATUS_COLORS: Record<string, string> = {
  open: "#6f7369", // wartet, aber ohne Frist im Nacken
  "in-progress": "#1f6b4f", // läuft gerade — der Akzent
  done: "#8b8f84", // erledigt, tritt zurück
  urgent: "#8a5a12", // Frist rückt heran
  overdue: "#8f3323", // Frist gerissen
  untagged: "#c9cbc2", // noch nicht eingeordnet
};

// Der Punkt vor einer Vorgangszeile ist nicht dasselbe wie die Schriftfarbe
// daneben. "Offen" tritt als Punkt weiter zurück als es sich als Text
// leisten könnte — sonst stehen in einer Liste, die überwiegend offen ist,
// vierzig gleich laute Marken, und die zwei überfälligen gehen darin unter.
export const STATUS_DOT: Record<string, string> = {
  ...STATUS_COLORS,
  open: "#c9cbc2",
};

export const STATUS_LABELS: Record<string, string> = {
  open: "Offen",
  "in-progress": "In Arbeit",
  done: "Erledigt",
  urgent: "Dringend",
  overdue: "Überfällig",
  untagged: "Ohne Tag",
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

// Die Taxonomie steht als englischer Slug in Paperless (server/app/tag_seed.py),
// gelesen wird sie auf Deutsch. "__other__" ist der Sammelposten, den die
// Übersicht schickt — kein Tag, sondern der Rest.
export const CATEGORY_LABELS: Record<string, string> = {
  invoice: "Rechnung",
  contract: "Vertrag",
  "maintenance-request": "Instandhaltung",
  legal: "Rechtliches",
  correspondence: "Korrespondenz",
  "tenant-notice": "Mieterschreiben",
  insurance: "Versicherung",
  "utility-bill": "Nebenkosten",
  __other__: "Sonstige",
};

export function categoryLabel(slug: string | null): string {
  if (!slug) return "—";
  return CATEGORY_LABELS[slug] ?? slug;
}

export function colorForTag(name: string, fallback: string): string {
  return STATUS_COLORS[name] ?? CATEGORY_COLORS[name] ?? fallback;
}
