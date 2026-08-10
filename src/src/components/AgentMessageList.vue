<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useChatStore, type ChatEntry, type ToolCall } from "../stores/chat";
import { useAuthStore } from "../stores/auth";
import type { BoardEvent } from "../api/client";
import ToolTrace from "./ToolTrace.vue";
import BoardEventChip from "./BoardEventChip.vue";
import { renderMarkdown } from "../markdown";

const store = useChatStore();
const auth = useAuthStore();
const messagesEl = ref<HTMLDivElement | null>(null);

type Segment =
  | { type: "tools"; key: string; calls: ToolCall[] }
  | { type: "board"; key: string; event: BoardEvent };

// Ohne Board-Events (der Normalfall) bleibt das genau eine Segment-Zeile —
// sichtbar unverändert gegenüber vorher. Erst ein Board-Event, das mitten in
// den Tool-Aufrufen entstanden ist, teilt die Ablaufanzeige an der Stelle.
function segments(m: ChatEntry): Segment[] {
  const calls = m.toolCalls ?? [];
  const events = m.boardEvents;
  if (!events?.length) {
    return calls.length ? [{ type: "tools", key: "tools-0", calls }] : [];
  }

  const sorted = [...events].sort((a, b) => a.toolCallIndex - b.toolCallIndex);
  const result: Segment[] = [];
  let cursor = 0;
  for (const event of sorted) {
    const end = event.toolCallIndex + 1;
    const slice = calls.slice(cursor, end);
    if (slice.length) result.push({ type: "tools", key: `tools-${cursor}`, calls: slice });
    result.push({ type: "board", key: `board-${event.id}`, event });
    cursor = end;
  }
  const rest = calls.slice(cursor);
  if (rest.length) result.push({ type: "tools", key: `tools-${cursor}`, calls: rest });
  return result;
}

defineExpose({ scrollToBottom });

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  });
}

watch(() => store.messages, scrollToBottom, { deep: true });

function onContentClick(event: MouseEvent) {
  const el = event.target as HTMLElement;
  const docTarget = el.closest<HTMLElement>("[data-doc-id]");
  if (docTarget) {
    const id = Number(docTarget.dataset.docId);
    if (!Number.isNaN(id)) store.openDocument(id);
    return;
  }
  const caseTarget = el.closest<HTMLElement>("[data-case-id]");
  if (caseTarget?.dataset.caseId) store.openCasePopup(caseTarget.dataset.caseId);
}
</script>

<template>
  <div ref="messagesEl" class="messages">
    <!-- Ehrlicher, als es den Nutzer erst durch eine Absage des Assistenten
         herausfinden zu lassen, nachdem er seine Bitte formuliert hat. -->
    <p v-if="!auth.can('agent:write')" class="messages__readonly mono">
      Nur-Lese-Zugang: der Assistent recherchiert und wertet aus, ändert aber nichts.
    </p>

    <p v-if="!store.messages.length" class="messages__empty mono">
      Antworten mit Quellenangabe aus dem Dokumentenbestand.
    </p>

    <div v-for="(m, i) in store.messages" :key="i" class="turn" :class="{ 'turn--user': m.role === 'user' }">
      <p class="turn__label" :class="{ 'turn__label--assistant': m.role === 'assistant' }">
        {{ m.role === "user" ? "Sie" : "Antwort" }}
      </p>
      <template v-for="segment in segments(m)" :key="segment.key">
        <ToolTrace v-if="segment.type === 'tools'" :tool-calls="segment.calls" :streaming="!!m.streaming" />
        <BoardEventChip v-else :event="segment.event" />
      </template>
      <div v-if="m.content" class="turn__content" @click="onContentClick" v-html="renderMarkdown(m.content)" />
      <div v-else-if="m.streaming" class="typing"><span /><span /><span /></div>
    </div>
  </div>
</template>

<style scoped>
.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1.25rem;
}

.messages__empty {
  margin: 0;
}

/* Ein Zustandsband, keine Warnung: die Rolle ist so gewollt, nicht kaputt. */
.messages__readonly {
  margin: -1.25rem -1.25rem 1.25rem;
  padding: 0.5rem 1.25rem;
  border-bottom: 1px solid var(--color-line-soft);
  background: var(--color-surface-muted);
  color: var(--color-ink-4);
}

/* Sprechblasen sind hier falsch: es ist kein Gespräch unter Gleichen, sondern
   eine Frage und eine belegte Antwort. Haarlinien trennen sie so, wie sie
   auch die Vorgangsliste trennen. */
.turn {
  padding-block: 1.125rem;
  border-bottom: 1px solid var(--color-line-soft);
}

.turn:first-child {
  padding-top: 0;
}

.turn:last-child {
  border-bottom: 0;
}

/* Ein Ton, keine Blase: die eigene Nachricht hebt sich ab, ohne wie eine
   Gesprächsblase in einem Gespräch unter Gleichen zu wirken. */
.turn--user {
  margin-inline: -1.25rem;
  padding-inline: 1.25rem;
  background: var(--color-surface-muted);
}

.turn__label {
  margin: 0 0 0.5rem;
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-ink-5);
}

.turn__label--assistant {
  color: var(--color-accent);
}

.turn__content {
  color: var(--color-text);
  line-height: var(--line-height-prose);
}

.turn__content :deep(p) {
  margin: 0 0 0.5rem;
}

.turn__content :deep(p:last-child) {
  margin-bottom: 0;
}

.turn__content :deep(ul),
.turn__content :deep(ol) {
  margin: 0 0 0.5rem;
  padding-inline-start: 1.2rem;
}

.turn__content :deep(table) {
  display: block;
  max-width: 100%;
  margin: 0 0 0.75rem;
  overflow-x: auto;
  border-collapse: collapse;
  font-size: var(--font-size-md);
}

.turn__content :deep(th),
.turn__content :deep(td) {
  padding: 0.375rem 0.625rem;
  border: 1px solid var(--color-line);
  text-align: left;
}

.turn__content :deep(th) {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-ink-5);
  background: var(--color-surface-muted);
}

/* Belegstellen: der Akzentstrich links markiert, was aus einem Dokument
   stammt und nicht aus dem Modell. Ein Textlink, keine Schaltfläche: eine
   gepunktete Unterstreichung plus schlankes Link-Icon reichen als Hinweis,
   ganz ohne Hintergrundfläche oder Rand. */
.turn__content :deep(.doc-link) {
  display: inline-flex;
  align-items: baseline;
  gap: 0.1875rem;
  vertical-align: baseline;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-text);
  font: inherit;
  font-size: var(--font-size-md);
  line-height: inherit;
  text-decoration: underline dotted;
  text-underline-offset: 2px;
  cursor: pointer;
  transition: color var(--duration-fast) var(--ease-standard);
}

.turn__content :deep(.doc-link:hover) {
  color: var(--color-accent);
}

.turn__content :deep(.doc-link__icon) {
  flex: none;
  width: 11px;
  height: 11px;
  color: var(--color-ink-5);
}

.turn__content :deep(.doc-link:hover .doc-link__icon) {
  color: var(--color-accent);
}

.typing {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.typing span {
  width: 5px;
  height: 5px;
  background: var(--color-ink-5);
  animation: typing-blink 1.1s var(--ease-standard) infinite;
}

.typing span:nth-child(2) {
  animation-delay: 0.15s;
}

.typing span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes typing-blink {
  0%,
  60%,
  100% {
    opacity: 0.3;
  }
  30% {
    opacity: 1;
  }
}
</style>
