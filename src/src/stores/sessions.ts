import { defineStore } from "pinia";
import { api, type ChatSession } from "../api/client";
import { useChatStore } from "./chat";

export const useSessionsStore = defineStore("sessions", {
  state: () => ({
    items: [] as ChatSession[],
    loading: false,
  }),
  actions: {
    async fetch() {
      this.loading = true;
      try {
        this.items = await api.listSessions();
      } finally {
        this.loading = false;
      }
    },
    async remove(id: string) {
      await api.deleteSession(id);
      this.items = this.items.filter((s) => s.id !== id);
      const chatStore = useChatStore();
      if (chatStore.sessionId === id) chatStore.newChat();
    },
  },
});
