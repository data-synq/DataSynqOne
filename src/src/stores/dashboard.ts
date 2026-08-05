import { defineStore } from "pinia";
import { api, type DashboardOverview } from "../api/client";

const POLL_INTERVAL_MS = 15_000;

export const useDashboardStore = defineStore("dashboard", {
  state: () => ({
    overview: null as DashboardOverview | null,
    loading: false,
    error: null as string | null,
    lastLoadedAt: null as string | null,
    focusedStatus: null as string | null,
    pollHandle: null as ReturnType<typeof setInterval> | null,
    visibilityHandler: null as (() => void) | null,
  }),
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
        this.error = e instanceof Error ? e.message : String(e);
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
    focusStatus(status: string | null) {
      this.focusedStatus = status;
    },
  },
});
