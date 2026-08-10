import { defineStore } from "pinia";
import {
  api,
  setUnauthorizedHandler,
  UnauthorizedError,
  type CurrentUser,
  type PermissionName,
} from "../api/client";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: null as CurrentUser | null,
    /** Solange false, ist noch unbekannt, ob eine Sitzung besteht. */
    resolved: false,
  }),
  getters: {
    hasSession: (state) => state.user !== null,
    isAuthenticated: (state) => state.user?.auth_stage === "ready",
    authStage: (state) => state.user?.auth_stage ?? null,
    /** Der Passwortwechsel steht vor allem anderen, wenn er erzwungen ist. */
    mustChangePassword: (state) => state.user?.auth_stage === "password_change",
  },
  actions: {
    can(permission: PermissionName): boolean {
      return this.user?.permissions.includes(permission) ?? false;
    },

    /** Einmal pro Seitenaufruf: besteht eine Sitzung? */
    async resolve() {
      if (this.resolved) return;
      try {
        this.user = await api.me();
      } catch (e) {
        if (!(e instanceof UnauthorizedError)) throw e;
        this.user = null;
      } finally {
        this.resolved = true;
      }
    },

    async login(email: string, password: string) {
      this.user = await api.login(email, password);
      this.resolved = true;
    },

    async changePassword(currentPassword: string, newPassword: string) {
      this.user = await api.changePassword(currentPassword, newPassword);
    },

    async confirmMfa(code: string) {
      const result = await api.confirmMfa(code);
      this.user = result.user;
      return result.recovery_codes;
    },

    async verifyMfa(code: string) {
      this.user = await api.verifyMfa(code);
    },

    async logout() {
      try {
        await api.logout();
      } finally {
        this.clear();
      }
    },

    /** Lokaler Zustand ohne Serveraufruf — für den Fall eines 401. */
    clear() {
      this.user = null;
      this.resolved = true;
    },
  },
});

/** Ein 401 aus irgendeinem Aufruf beendet die Sitzung auch in der Oberfläche.
 *  Ohne das zeigt nach einem Ablauf jede Kachel des Dashboards nur „401“ an. */
export function registerAuthInterceptor() {
  setUnauthorizedHandler(() => {
    const auth = useAuthStore();
    if (auth.hasSession) auth.clear();
  });
}
