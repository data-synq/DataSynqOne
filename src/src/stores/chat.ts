import { defineStore } from "pinia";
import { api, type BoardEvent, type ChartSpec } from "../api/client";
import { useSessionsStore } from "./sessions";

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
}

export interface ChatEntry {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  boardEvents?: BoardEvent[];
  streaming?: boolean;
}

export type SidePanelState = { type: "document"; documentId: number } | null;

export type PresentationContent =
  | { type: "document"; documentId: number }
  | { type: "chart"; spec: ChartSpec }
  | { type: "email"; draftId: string }
  | { type: "html"; html: string }
  | { type: "form"; formId: string }
  | null;

export type PresentationPanelState = "collapsed" | "default" | "maximized";

export type FocusOrigin = { top: number; left: number; width: number; height: number } | null;

export const useChatStore = defineStore("chat", {
  state: () => ({
    messages: [] as ChatEntry[],
    sending: false,
    sidePanel: null as SidePanelState,
    suggestions: [] as string[],
    sessionId: null as string | null,
    focusMode: false as boolean,
    focusOrigin: null as FocusOrigin,
    chatDraft: null as string | null,
    historyOpen: true as boolean,
    presentationContent: null as PresentationContent,
    presentationPanelState: "collapsed" as PresentationPanelState,
    // Global statt lokal in einer Komponente: dieselbe Karte muss vom großen
    // Graphen, vom eingebetteten Mini-Graphen auf der Detailseite und von
    // einem `case:`-Verweis im Chat aus gleichermaßen öffenbar sein.
    casePopupTrackingId: null as string | null,
  }),
  getters: {
    // Für die vertikale Übersichtsleiste rechts: alle Board-Events der Sitzung,
    // in der Reihenfolge, in der sie entstanden sind.
    allBoardEvents(state): BoardEvent[] {
      return state.messages.flatMap((m) => m.boardEvents ?? []);
    },
  },
  actions: {
    openDocument(id: number) {
      // sidePanel und presentationContent schließen sich gegenseitig aus —
      // sonst taucht dasselbe Dokument nach dem Schließen des Fokusmodus im
      // alten Modal noch einmal auf.
      if (this.focusMode) {
        this.sidePanel = null;
        this.openPresentation({ type: "document", documentId: id });
      } else {
        this.sidePanel = { type: "document", documentId: id };
      }
    },
    openChat() {
      this.sidePanel = null;
      this.focusMode = true;
    },
    closeChat() {
      this.focusMode = false;
      this.focusOrigin = null;
    },
    askAboutDocument(id: number, title: string) {
      this.chatDraft = `Erkläre mir das Dokument "${title}" (ID ${id}) und fasse den wichtigsten Inhalt zusammen.`;
      this.sidePanel = null;
      this.focusMode = true;
    },
    askAboutCase(trackingId: string, title: string) {
      this.chatDraft = `Fasse mir den Stand von Anliegen ${trackingId} ("${title}") zusammen.`;
      this.sidePanel = null;
      this.focusMode = true;
    },
    // Für einen Zeitstrahl-Verweis auf "in diesem Chat besprochen": lädt die
    // Sitzung wie ChatHistorySidebar.vue es tut, öffnet zusätzlich den
    // Fokusmodus — die Sidebar braucht das nicht, weil sie nur sichtbar ist,
    // während der Fokusmodus ohnehin schon offen ist; von der Anliegen-Seite
    // aus ist das nicht der Fall.
    async openSession(id: string) {
      await this.loadSession(id);
      this.sidePanel = null;
      this.focusMode = true;
    },
    openCasePopup(trackingId: string) {
      this.casePopupTrackingId = trackingId;
    },
    closeCasePopup() {
      this.casePopupTrackingId = null;
    },
    closePanel() {
      this.sidePanel = null;
    },
    openPresentation(content: PresentationContent) {
      this.presentationContent = content;
      if (this.presentationPanelState === "collapsed") {
        this.presentationPanelState = "default";
      }
      // Das Board braucht den Platz, den die Historie sonst links belegt.
      this.historyOpen = false;
    },
    closePresentation() {
      this.presentationContent = null;
      this.presentationPanelState = "collapsed";
    },
    setPresentationPanelState(state: PresentationPanelState) {
      this.presentationPanelState = state;
    },
    // Eigener Name statt direkt openPresentation() an den Aufrufstellen (Chip,
    // Übersichtsleiste) — macht dort deutlich, dass hier ein bereits gezeigter
    // Board-Inhalt erneut geöffnet wird, kein neuer. Der Schalter nach `kind`
    // ist der Punkt, der bei einer neuen Board-Art erweitert werden muss.
    reopenBoardEvent(event: BoardEvent) {
      if (event.kind === "document") {
        this.openPresentation({ type: "document", documentId: event.payload.documentId });
      } else if (event.kind === "chart") {
        this.openPresentation({ type: "chart", spec: event.payload.spec });
      } else if (event.kind === "email") {
        this.openPresentation({ type: "email", draftId: event.payload.draftId });
      }
    },
    newChat() {
      this.messages = [];
      this.sessionId = null;
      this.suggestions = [];
      this.sidePanel = null;
      this.presentationContent = null;
      this.presentationPanelState = "collapsed";
      this.historyOpen = true;
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
        boardEvents: m.board_events?.map(
          (ev) =>
            ({
              id: ev.id,
              toolCallIndex: ev.tool_call_index,
              kind: ev.kind,
              title: ev.title,
              payload: ev.payload,
            }) as BoardEvent,
        ),
        streaming: false,
      }));
      this.sessionId = id;
      this.suggestions = [];
      this.sidePanel = null;
      this.presentationContent = null;
      this.presentationPanelState = "collapsed";
    },
    async sendMessage(text: string) {
      this.suggestions = [];
      this.messages.push({ role: "user", content: text });

      this.messages.push({
        role: "assistant",
        content: "",
        toolCalls: [],
        streaming: true,
      });
      const entry = this.messages[this.messages.length - 1];

      this.sending = true;
      try {
        await api.streamChat(text, this.sessionId, (event) => {
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
          } else if (event.type === "board") {
            // Der Index zeigt auf den Tool-Aufruf, der dieses Event ausgelöst hat —
            // an genau dieser Stelle teilt AgentMessageList die Ablaufanzeige.
            const boardEvent = {
              id: event.id,
              toolCallIndex: entry.toolCalls!.length - 1,
              kind: event.kind,
              title: event.title,
              payload: event.payload,
            } as BoardEvent;
            (entry.boardEvents ??= []).push(boardEvent);
            if (event.kind === "document") {
              this.openPresentation({ type: "document", documentId: event.payload.documentId });
            } else if (event.kind === "chart") {
              this.openPresentation({ type: "chart", spec: event.payload.spec });
            }
            // kind === "email": bewusst kein Auto-Öffnen — der Entwurf verlangt eine
            // Entscheidung per Klick auf die Karte im Verlauf, kein ungefragtes Board.
          } else if (event.type === "session") {
            this.sessionId = event.id;
            // Ohne das bliebe die Historie eingeklappt, falls sie es vom vorigen
            // Board her noch war — die neue Sitzung existiert dort ja noch gar
            // nicht, und eingeklappt sähe es aus, als wäre sie nie aufgetaucht.
            this.historyOpen = true;
            useSessionsStore().fetch();
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
