import { defineStore } from "pinia";

export interface ActiveCase {
  trackingId: string;
  title: string;
  status: "open" | "closed";
}

// Getrennt von chat.ts: das hier ist Navbar-Chrome (welches Anliegen sieht man
// gerade), kein Chat-Zustand. AppTopBar.vue ist kein Kind von CaseDetailView.vue,
// daher braucht es einen eigenen Kanal statt Props, um vom aktuell offenen
// Anliegen zu erfahren.
export const useCaseContextStore = defineStore("caseContext", {
  state: () => ({
    activeCase: null as ActiveCase | null,
  }),
  actions: {
    setActiveCase(activeCase: ActiveCase) {
      this.activeCase = activeCase;
    },
    clearActiveCase() {
      this.activeCase = null;
    },
  },
});
