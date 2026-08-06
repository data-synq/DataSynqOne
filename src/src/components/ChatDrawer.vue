<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";
import ToolTrace from "./ToolTrace.vue";
import ChatHistoryPanel from "./ChatHistoryPanel.vue";
import IconClose from "./icons/IconClose.vue";
import IconHistory from "./icons/IconHistory.vue";
import IconPlus from "./icons/IconPlus.vue";
import IconSend from "./icons/IconSend.vue";
import IconChart from "./icons/IconChart.vue";
import { renderMarkdown } from "../markdown";

const store = useChatStore();
const input = ref("");
const messagesEl = ref<HTMLDivElement | null>(null);
const inputEl = ref<HTMLTextAreaElement | null>(null);

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

function toggleHistory() {
  store.historyOpen = !store.historyOpen;
}
</script>

<template>
  <div v-if="store.chatOpen" class="drawer-backdrop" @click.self="store.closeChat()">
    <aside class="drawer">
      <div class="drawer__header">
        <span class="drawer__title">Chat</span>
        <div class="drawer__actions">
          <button
            type="button"
            class="icon-button"
            :class="{ 'icon-button--active': store.historyOpen }"
            title="Verlauf"
            @click="toggleHistory"
          >
            <IconHistory />
          </button>
          <button type="button" class="icon-button" title="Neuer Chat" @click="store.newChat()">
            <IconPlus />
          </button>
          <button type="button" class="icon-button" title="Schließen" @click="store.closeChat()">
            <IconClose />
          </button>
        </div>
      </div>

      <ChatHistoryPanel v-if="store.historyOpen" />

      <div class="chat">
        <div class="messages" ref="messagesEl">
          <div v-for="(m, i) in store.messages" :key="i" :class="['bubble', `bubble--${m.role}`]">
            <span class="bubble__label">{{ m.role === "user" ? "Du" : "Agent" }}</span>
            <ToolTrace v-if="m.toolCalls?.length" :tool-calls="m.toolCalls" :streaming="!!m.streaming" />
            <div
              v-if="m.content"
              class="bubble__content"
              @click="onContentClick"
              v-html="renderMarkdown(m.content)"
            ></div>
            <div v-else-if="m.streaming" class="typing-indicator">
              <span /><span /><span />
            </div>
            <div v-if="m.charts?.length" class="chart-chips">
              <button
                v-for="(chart, ci) in m.charts"
                :key="ci"
                type="button"
                class="chart-chip"
                @click="store.openChart(chart)"
              >
                <IconChart /> {{ chart.title }}
              </button>
            </div>
          </div>
        </div>

        <div v-if="!store.sending && store.suggestions.length" class="suggestions">
          <button
            v-for="(s, i) in store.suggestions"
            :key="i"
            type="button"
            class="suggestion-chip"
            @click="useSuggestion(s)"
          >
            {{ s }}
          </button>
        </div>

        <form class="input-row" @submit.prevent="submit">
          <textarea
            ref="inputEl"
            v-model="input"
            rows="1"
            placeholder="Frage zum Fall oder Dokument..."
            @keydown.enter="onEnter"
          />
          <button type="submit" class="send-button" :disabled="store.sending || !input.trim()" aria-label="Senden">
            <IconSend />
          </button>
        </form>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(48, 79, 91, 0.28);
  z-index: 40;
  display: flex;
  justify-content: flex-end;
}

.drawer {
  position: relative;
  width: clamp(480px, 42vw, 720px);
  max-width: 100%;
  height: 100%;
  background: var(--surface-glass-strong);
  border-radius: var(--radius-lg) 0 0 var(--radius-lg);
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  transition: transform var(--duration-normal) var(--ease-emphasized);
}

.drawer__header {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--page-padding);
  border-bottom: 1px solid var(--color-border);
}

.drawer__title {
  font-family: var(--font-display);
  font-weight: 700;
  color: var(--color-heading-strong);
}

.drawer__actions {
  display: flex;
  gap: 0.4rem;
}

.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  min-width: 38px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-white);
  border-radius: var(--radius-pill);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  color: var(--color-text-muted);
  font-size: 1rem;
  transition:
    color var(--duration-fast) var(--ease-standard),
    box-shadow var(--duration-fast) var(--ease-standard);
}

.icon-button:hover {
  color: var(--color-brand-blue-dark);
}

.icon-button--active {
  color: var(--color-brand-blue-dark);
  box-shadow: var(--shadow-md);
}

.chat {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: var(--space-3) var(--page-padding);
  box-sizing: border-box;
}

.messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-block: var(--space-2);
}

.bubble {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  max-width: min(720px, 90%);
  padding: 0.75rem 1.1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  font-size: var(--font-size-sm);
}

.bubble--user {
  align-self: flex-end;
  background: var(--color-surface-muted);
  text-align: right;
}

.bubble--assistant {
  align-self: flex-start;
  background: var(--surface-glass-strong);
}

.bubble__label {
  color: var(--color-text-muted);
  font-family: var(--font-display);
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.bubble__content :deep(p) {
  margin: 0 0 0.5rem;
}

.bubble__content :deep(p:last-child) {
  margin-bottom: 0;
}

.bubble__content :deep(ul),
.bubble__content :deep(ol) {
  margin: 0 0 0.5rem;
  padding-inline-start: 1.2rem;
}

.bubble__content :deep(a) {
  color: var(--color-link);
}

.typing-indicator {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.2rem 0;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-text-muted);
  animation: typing-bounce 1.1s var(--ease-standard) infinite;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.15s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes typing-bounce {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.5;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

.chart-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.3rem;
}

.chart-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border: 1px solid var(--color-brand-blue-strong);
  background: var(--color-cream-light);
  color: var(--color-brand-blue-dark);
  border-radius: var(--radius-pill);
  padding: 0.2rem 0.7rem;
  font: inherit;
  font-size: var(--font-size-xs);
  cursor: pointer;
}

.bubble__content :deep(.doc-link) {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  border: 1px solid var(--color-brand-blue-strong);
  background: var(--color-cream-light);
  color: var(--color-brand-blue-dark);
  border-radius: var(--radius-pill);
  padding: 0.2rem 0.7rem;
  font: inherit;
  font-size: var(--font-size-xs);
  cursor: pointer;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding-block: var(--space-2);
}

.suggestion-chip {
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-pill);
  background: var(--surface-glass);
  color: var(--color-heading-strong);
  padding: 0.55rem 1rem;
  font: inherit;
  font-size: var(--font-size-xs);
  font-weight: 500;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition:
    transform var(--duration-fast) var(--ease-standard),
    box-shadow var(--duration-normal) var(--ease-standard);
}

.suggestion-chip:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: var(--space-1);
  padding: 0.5rem;
  border-radius: var(--radius-lg);
  background: var(--surface-glass-strong);
  box-shadow: var(--shadow-sm);
}

.input-row textarea {
  flex: 1;
  border: none;
  background: transparent;
  box-shadow: none;
  min-height: 24px;
  max-height: 7.5rem;
  resize: none;
  padding: 0.5rem 0.6rem;
  font: inherit;
  line-height: 1.4;
}

.input-row textarea:focus {
  box-shadow: none;
  outline: none;
}

.send-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: var(--radius-pill);
  background: var(--color-brand-blue-dark);
  color: var(--color-white);
  cursor: pointer;
  font-size: 1.1rem;
  transition:
    background-color var(--duration-fast) var(--ease-standard),
    transform var(--duration-fast) var(--ease-standard);
}

.send-button:hover:not(:disabled) {
  background: var(--color-heading-strong);
  transform: translateY(-1px);
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
