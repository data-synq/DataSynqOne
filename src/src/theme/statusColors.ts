export const STATUS_COLORS: Record<string, string> = {
  open: "#83afc2",
  "in-progress": "#d7c394",
  done: "#527661",
  urgent: "#a8443b",
  overdue: "#8c3a32",
  untagged: "#87979d",
};

export const CATEGORY_COLORS: Record<string, string> = {
  invoice: "#587d8d",
  contract: "#456774",
  "maintenance-request": "#b59d68",
  legal: "#304f5b",
  correspondence: "#a8c5d2",
  "tenant-notice": "#d7c394",
  insurance: "#718087",
  "utility-bill": "#83afc2",
};

export function colorForTag(name: string, fallback: string): string {
  return STATUS_COLORS[name] ?? CATEGORY_COLORS[name] ?? fallback;
}
