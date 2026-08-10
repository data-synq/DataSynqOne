export function formatDaysUntil(daysUntil: number): string {
  if (daysUntil < -1) return `${Math.abs(daysUntil)} Tage über`;
  if (daysUntil === -1) return "1 Tag über";
  if (daysUntil === 0) return "heute";
  if (daysUntil === 1) return "morgen";
  return `in ${daysUntil} Tagen`;
}

/** "05.08." — Tag und Monat reichen; das Jahr steht im Kopf der Seite. */
export function formatShortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** "05.08.2026, 14:32" — für Zeitstrahl/Notizen/Anliegen, wo auch die Uhrzeit zählt. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Ganze Tage bis zu einem ISO-Datum, von heute aus. Negativ heißt überschritten. */
export function daysUntil(iso: string): number {
  const due = new Date(iso);
  if (Number.isNaN(due.getTime())) return 0;
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);
  return Math.round((due.getTime() - startOfToday.getTime()) / 86_400_000);
}

/** Fließkomma-Tage seit einem ISO-Zeitpunkt, bis jetzt. */
export function daysSince(iso: string): number {
  return (Date.now() - new Date(iso).getTime()) / 86_400_000;
}

export function isSameDay(iso: string, reference: Date = new Date()): boolean {
  const date = new Date(iso);
  return (
    date.getFullYear() === reference.getFullYear() &&
    date.getMonth() === reference.getMonth() &&
    date.getDate() === reference.getDate()
  );
}

// Ab wann ein offenes Anliegen als "wartet schon lange" gilt — an einer Stelle
// definiert, damit Kennzahl (CasesOverviewHeader) und Schnellfilter (CasesView)
// nie auseinanderlaufen.
export const STALE_CASE_DAYS = 7;
