export function formatDaysUntil(daysUntil: number): string {
  if (daysUntil < 0) return `überfällig seit ${Math.abs(daysUntil)} Tag(en)`;
  if (daysUntil === 0) return "heute fällig";
  return `in ${daysUntil} Tag(en)`;
}
