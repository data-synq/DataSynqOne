import { defineStore } from "pinia";
import { api, type DashboardOverview, type Deadline, type DocSummary } from "../api/client";

const POLL_INTERVAL_MS = 15_000;

export const useDashboardStore = defineStore("dashboard", {
  state: () => ({
    overview: null as DashboardOverview | null,
    loading: false,
    error: null as string | null,
    lastLoadedAt: null as string | null,
    focusedStatus: null as string | null,
    selectedObject: null as string | null,
    pollHandle: null as ReturnType<typeof setInterval> | null,
    visibilityHandler: null as (() => void) | null,
  }),
  getters: {
    // Die beiden Filter liegen hier und nicht in den Komponenten: Objektwahl
    // und Statusfokus wirken auf Vorgangsliste, Fristen und Korrespondenz
    // gleichzeitig. Dreimal dieselbe Bedingung wäre dreimal die Gelegenheit,
    // dass eine Ansicht etwas anderes zeigt als die daneben.
    matchesObject(state) {
      return (objectName: string | null) =>
        state.selectedObject === null || objectName === state.selectedObject;
    },
    filteredQueue(state): DocSummary[] {
      return (state.overview?.queue ?? []).filter(
        (d) =>
          this.matchesObject(d.object_name) &&
          (state.focusedStatus === null || d.status === state.focusedStatus),
      );
    },
    filteredDeadlines(state): Deadline[] {
      return (state.overview?.deadlines ?? []).filter((d) => this.matchesObject(d.object_name));
    },
    filteredRecent(state): DocSummary[] {
      return (state.overview?.recent ?? []).filter((d) => this.matchesObject(d.object_name));
    },
    isFiltered(state): boolean {
      return state.focusedStatus !== null || state.selectedObject !== null;
    },
  },
  actions: {
    async load() {
      if (this.loading) return;
      this.loading = true;
      if (!this.overview) this.error = null;
      try {
        this.overview = await api.getDashboardOverview();
        this.lastLoadedAt = new Date().toISOString();
        this.error = null;
      } catch (e) {
        // TypeError("Failed to fetch") heißt: Backend nicht erreichbar.
        // Die rohe Browsermeldung hilft niemandem — benennen, was los ist
        // und was zu tun wäre. Alles andere (HTTP-Fehler aus client.ts)
        // trägt seine Statusnummer bereits im Text.
        this.error =
          e instanceof TypeError
            ? "Server nicht erreichbar — läuft das Backend? Es wird automatisch weiter versucht."
            : e instanceof Error
              ? e.message
              : String(e);
      } finally {
        this.loading = false;
      }
    },
    startPolling() {
      if (this.pollHandle) return;
      this.pollHandle = setInterval(() => {
        if (document.visibilityState === "visible") this.load();
      }, POLL_INTERVAL_MS);
      this.visibilityHandler = () => {
        if (document.visibilityState === "visible") this.load();
      };
      document.addEventListener("visibilitychange", this.visibilityHandler);
    },
    stopPolling() {
      if (this.pollHandle) {
        clearInterval(this.pollHandle);
        this.pollHandle = null;
      }
      if (this.visibilityHandler) {
        document.removeEventListener("visibilitychange", this.visibilityHandler);
        this.visibilityHandler = null;
      }
    },
    // Ein zweiter Klick auf dieselbe Kennzahl hebt den Fokus wieder auf —
    // sonst braucht man für den Weg zurück ein anderes Bedienelement.
    focusStatus(status: string | null) {
      this.focusedStatus = status !== null && this.focusedStatus === status ? null : status;
    },
    selectObject(objectName: string | null) {
      this.selectedObject = objectName;
    },
    clearFilters() {
      this.focusedStatus = null;
      this.selectedObject = null;
    },
  },
});
