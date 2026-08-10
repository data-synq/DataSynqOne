// Geteilt zwischen CaseDetailView.vue (Text-Zeitstrahl) und CaseEventTimeline.vue
// (grafischer Zeitstrahl) — eine Quelle fuer die Beschriftungen, statt zweier
// Kopien, die auseinanderlaufen koennen.
export const EVENT_LABELS: Record<string, string> = {
  received: "Eingegangen",
  filed: "Angelegt",
  tagged: "Getaggt",
  linked: "Verknüpfung",
  unlinked: "Verknüpfung entfernt",
  note_added: "Notiz hinzugefügt",
  closed: "Geschlossen",
  reopened: "Wieder geöffnet",
  reply_sent: "Antwort verschickt",
  chat_linked: "Im Chat besprochen",
};

export const LINK_LABELS: Record<string, string> = {
  note: "Notiz ansehen",
  case: "Anliegen ansehen",
  document: "Dokument ansehen",
  session: "Chat öffnen",
};
