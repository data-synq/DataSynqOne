import { defineStore } from "pinia";
import { api, type ChartSpec } from "../api/client";

interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
}

interface ChatEntry {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  charts?: ChartSpec[];
  streaming?: boolean;
}

export type SidePanelState = { type: "document"; documentId: number } | null;

export const useChatStore = defineStore("chat", {
  state: () => ({
    messages: [] as ChatEntry[],
    sending: false,
    sidePanel: null as SidePanelState,
    activeChart: null as ChartSpec | null,
    suggestions: [] as string[],
    sessionId: null as string | null,
    chatOpen: false as boolean,
    chatDraft: null as string | null,
    historyOpen: false as boolean,
  }),
  actions: {
    openDocument(id: number) {
      this.sidePanel = { type: "document", documentId: id };
    },
    openChat() {
      this.chatOpen = true;
    },
    closeChat() {
      this.chatOpen = false;
    },
    askAboutDocument(id: number, title: string) {
      this.chatDraft = `Erkläre mir das Dokument "${title}" (ID ${id}) und fasse den wichtigsten Inhalt zusammen.`;
      this.chatOpen = true;
    },
    openChart(chart: ChartSpec) {
      this.activeChart = chart;
    },
    closeChart() {
      this.activeChart = null;
    },
    closePanel() {
      this.sidePanel = null;
    },
    newChat() {
      this.messages = [];
      this.sessionId = null;
      this.suggestions = [];
      this.sidePanel = null;
      this.activeChart = null;
      this.historyOpen = false;
    },
    async loadSession(id: string) {
      const session = await api.getSession(id);
      this.messages = session.messages.map((m) => ({
        role: m.role as "user" | "assistant",
        content: m.content,
        toolCalls: m.tool_calls
          ? m.tool_calls.map((tc, i) => ({
              id: `${id}-${i}`,
              name: tc.name,
              arguments: tc.arguments,
              result: {},
            }))
          : undefined,
        streaming: false,
      }));
      this.sessionId = id;
      this.suggestions = [];
      this.sidePanel = null;
      this.activeChart = null;
    },
    async sendMessage(text: string) {
      const history = this.messages.map(({ role, content }) => ({ role, content }));
      this.suggestions = [];
      this.messages.push({ role: "user", content: text });

      this.messages.push({ role: "assistant", content: "", toolCalls: [], streaming: true });
      const entry = this.messages[this.messages.length - 1];

      this.sending = true;
      try {
        await api.streamChat(text, history, this.sessionId, (event) => {
          if (event.type === "tool_call") {
            entry.toolCalls!.push({
              id: event.id,
              name: event.name,
              arguments: event.arguments,
            });
          } else if (event.type === "tool_result") {
            const call = entry.toolCalls!.find((tc) => tc.id === event.id);
            if (call) call.result = event.result;
          } else if (event.type === "message") {
            entry.content = event.content;
            entry.streaming = false;
          } else if (event.type === "error") {
            entry.content = event.message;
            entry.streaming = false;
          } else if (event.type === "suggestions") {
            this.suggestions = event.items;
          } else if (event.type === "chart") {
            (entry.charts ??= []).push(event.spec);
            this.openChart(event.spec);
          } else if (event.type === "session") {
            this.sessionId = event.id;
          }
        });
      } catch (e) {
        entry.content = `Fehler: ${e instanceof Error ? e.message : String(e)}`;
        entry.streaming = false;
      } finally {
        entry.streaming = false;
        this.sending = false;
      }
    },
  },
});
