<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";
import { useDashboardStore } from "../stores/dashboard";
import ToolTrace from "./ToolTrace.vue";
import ChatHistoryPanel from "./ChatHistoryPanel.vue";
import { renderMarkdown } from "../markdown";
import { useAuthStore } from "../stores/auth";

const store = useChatStore();
const dashboard = useDashboardStore();
const auth = useAuthStore();
const input = ref("");
const messagesEl = ref<HTMLDivElement | null>(null);
const inputEl = ref<HTMLTextAreaElement | null>(null);

// Der Assistent antwortet über dem, was gerade auf dem Dashboard eingestellt
// ist. Das hier zu zeigen ist kein Schmuck: sonst wundert man sich, warum
// eine Frage nach "allen Fristen" nur die eines Objekts betrifft.
const context = computed(() => dashboard.selectedObject ?? "gesamter Bestand");

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  });
}

watch(() => store.messages, scrollToBottom, { deep: true });

watch(
  () => store.chatOpen,
  (open) => {
    if (open) {
      scrollToBottom();
      nextTick(() => inputEl.value?.focus());
    }
  },
);

watch(
  () => store.chatDraft,
  (draft) => {
    if (draft) {
      input.value = draft;
      store.chatDraft = null;
      nextTick(() => inputEl.value?.focus());
    }
  },
);

function onContentClick(event: MouseEvent) {
  const target = (event.target as HTMLElement).closest<HTMLElement>("[data-doc-id]");
  if (!target) return;
  const id = Number(target.dataset.docId);
  if (!Number.isNaN(id)) store.openDocument(id);
}

async function submit() {
  const text = input.value.trim();
  if (!text || store.sending) return;
  input.value = "";
  await store.sendMessage(text);
}

function onEnter(event: KeyboardEvent) {
  if (event.shiftKey) return;
  event.preventDefault();
  submit();
}

async function useSuggestion(text: string) {
  if (store.sending) return;
  await store.sendMessage(text);
}
</script>

<template>
  <!-- Angedockt statt über der Seite: kein Scrim, keine Verdunklung. Man
       fragt den Assistenten *zu* dem, was daneben steht, und muss es dabei
       weiter sehen können. Deshalb bleibt das Panel im Baum und fährt über
       transform aus — v-if würde bei jedem Öffnen den Verlauf neu aufbauen. -->
  <aside
    class="assistant"
    :class="{ 'assistant--open': store.chatOpen }"
    :aria-hidden="!store.chatOpen"
    :inert="store.chatOpen ? undefined : true"
  >
    <div class="assistant__head">
      <div class="assistant__title-group">
        <h2>Assistent</h2>
        <span class="mono assistant__context">Kontext: {{ context }}</span>
      </div>
      <div class="assistant__actions">
        <button
          type="button"
          class="link-action"
          :class="{ 'link-action--active': store.historyOpen }"
          @click="store.historyOpen = !store.historyOpen"
        >
          Verlauf
        </button>
        <button type="button" class="link-action" @click="store.newChat()">Neu</button>
        <button type="button" class="link-action" @click="store.closeChat()">Schließen</button>
      </div>
    </div>

    <ChatHistoryPanel v-if="store.historyOpen" />

    <!-- Ehrlicher, als es den Nutzer erst durch eine Absage des Assistenten
         herausfinden zu lassen, nachdem er seine Bitte formuliert hat. -->
    <p v-if="!auth.can('agent:write')" class="assistant__readonly mono">
      Nur-Lese-Zugang: der Assistent recherchiert und wertet aus, ändert aber nichts.
    </p>

    <div ref="messagesEl" class="assistant__messages">
      <p v-if="!store.messages.length" class="assistant__empty mono">
        Antworten mit Quellenangabe aus dem Dokumentenbestand.
      </p>

      <div v-for="(m, i) in store.messages" :key="i" class="turn">
        <p class="turn__label" :class="{ 'turn__label--assistant': m.role === 'assistant' }">
          {{ m.role === "user" ? "Sie" : "Antwort" }}
        </p>
        <ToolTrace v-if="m.toolCalls?.length" :tool-calls="m.toolCalls" :streaming="!!m.streaming" />
        <div v-if="m.content" class="turn__content" @click="onContentClick" v-html="renderMarkdown(m.content)" />
        <div v-else-if="m.streaming" class="typing"><span /><span /><span /></div>
        <div v-if="m.charts?.length" class="turn__charts">
          <button
            v-for="(chart, ci) in m.charts"
            :key="ci"
            type="button"
            class="turn__chart"
            @click="store.openChart(chart)"
          >
            {{ chart.title }}
          </button>
        </div>
      </div>

      <div v-if="!store.sending && store.suggestions.length" class="suggestions">
        <p class="eyebrow">Vorschläge</p>
        <button
          v-for="(s, i) in store.suggestions"
          :key="i"
          type="button"
          class="suggestions__item"
          @click="useSuggestion(s)"
        >
          {{ s }}
        </button>
      </div>
    </div>

    <form class="assistant__foot" @submit.prevent="submit">
      <div class="assistant__input-row">
        <label class="assistant__label" for="assistant-input">Frage an den Assistenten</label>
        <textarea
          id="assistant-input"
          ref="inputEl"
          v-model="input"
          rows="1"
          placeholder="Frage zur Verwaltung stellen"
          @keydown.enter="onEnter"
        />
        <button type="submit" class="button--secondary" :disabled="store.sending || !input.trim()">
          Senden
        </button>
      </div>
      <p class="assistant__hint mono">Antworten mit Quellenangabe aus dem Dokumentenbestand</p>
    </form>
  </aside>
</template>

<style scoped>
.assistant {
  position: fixed;
  z-index: 40;
  top: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  width: min(460px, 100vw);
  background: var(--color-white);
  border-left: 1px solid var(--color-line);
  transform: translateX(102%);
  transition: transform 220ms var(--ease-standard);
}

.assistant--open {
  transform: translateX(0);
}

.assistant__head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  height: 52px;
  padding-inline: 1.25rem;
  border-bottom: 1px solid var(--color-line);
}

.assistant__title-group {
  display: flex;
  align-items: baseline;
  gap: 0.5625rem;
  min-width: 0;
}

.assistant__title-group h2 {
  margin: 0;
}

.assistant__context {
  font-size: var(--font-size-2xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant__actions {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  flex: none;
}

.link-action--active {
  color: var(--color-ink);
}

.assistant__messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1.25rem;
}

.assistant__empty {
  margin: 0;
}

/* Ein Zustandsband, keine Warnung: die Rolle ist so gewollt, nicht kaputt. */
.assistant__readonly {
  margin: 0;
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

/* Belegstellen: der Akzentstrich links markiert, was aus einem Dokument
   stammt und nicht aus dem Modell. */
.turn__content :deep(.doc-link) {
  display: inline;
  padding: 0.05rem 0.25rem;
  background: var(--color-surface-muted);
  border-left: 2px solid var(--color-accent);
  color: var(--color-text);
  font: inherit;
  font-size: var(--font-size-md);
  cursor: pointer;
}

.turn__charts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.turn__chart {
  border: 1px solid var(--color-line-strong);
  background: transparent;
  padding: 0.25rem 0.625rem;
  font: inherit;
  font-size: var(--font-size-md);
  color: var(--color-text);
  cursor: pointer;
}

.turn__chart:hover {
  border-color: var(--color-ink);
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

.suggestions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
  padding-top: 1.125rem;
}

.suggestions .eyebrow {
  margin: 0 0 0.125rem;
}

.suggestions__item {
  border: 0;
  background: transparent;
  padding: 0;
  font: inherit;
  font-size: var(--font-size-md);
  color: var(--color-accent);
  text-align: left;
  cursor: pointer;
}

.suggestions__item:hover {
  text-decoration: underline;
}

.assistant__foot {
  flex: none;
  padding: 0.875rem 1.25rem 1.125rem;
  border-top: 1px solid var(--color-line);
}

.assistant__input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 0.75rem;
}

.assistant__label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.assistant__input-row textarea {
  max-height: 7rem;
  line-height: 1.4;
}

.assistant__hint {
  margin: 0.5rem 0 0;
  font-size: var(--font-size-2xs);
  color: #a0a498;
}
</style>
