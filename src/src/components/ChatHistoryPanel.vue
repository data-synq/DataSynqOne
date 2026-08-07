<script setup lang="ts">
import { onMounted } from "vue";
import { useChatStore } from "../stores/chat";
import { useSessionsStore } from "../stores/sessions";

const chatStore = useChatStore();
const sessionsStore = useSessionsStore();

onMounted(() => sessionsStore.fetch());

async function select(id: string) {
  await chatStore.loadSession(id);
  chatStore.historyOpen = false;
}

function remove(id: string, event: MouseEvent) {
  event.stopPropagation();
  sessionsStore.remove(id);
}

function relativeDate(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "Heute";
  if (days === 1) return "Gestern";
  if (days < 7) return `vor ${days} Tagen`;
  return new Date(iso).toLocaleDateString("de-DE");
}
</script>

<template>
  <div class="history">
    <p class="eyebrow history__head">Gespeicherte Chats</p>

    <p v-if="sessionsStore.loading" class="history__status mono">Lade …</p>
    <p v-else-if="!sessionsStore.items.length" class="history__status mono">
      Noch keine gespeicherten Chats.
    </p>

    <div
      v-for="s in sessionsStore.items"
      :key="s.id"
      class="history__row row-link"
      role="button"
      tabindex="0"
      @click="select(s.id)"
      @keydown.enter="select(s.id)"
    >
      <span class="history__title" :class="{ 'history__title--active': s.id === chatStore.sessionId }">
        {{ s.title }}
      </span>
      <span class="mono history__date">{{ relativeDate(s.updated_at) }}</span>
      <button type="button" class="link-action history__delete" aria-label="Chat löschen" @click="remove(s.id, $event)">
        Löschen
      </button>
    </div>
  </div>
</template>

<style scoped>
.history {
  flex: none;
  max-height: 216px;
  overflow-y: auto;
  padding: 0.75rem 1.25rem 0.875rem;
  border-bottom: 1px solid var(--color-line);
  background: var(--color-canvas);
}

.history__head {
  margin: 0 0 0.5rem;
}

.history__status {
  margin: 0;
}

.history__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.4375rem 0 0.5rem;
}

.history__row:hover {
  background: #f1f1ec;
}

.history__title {
  font-size: var(--font-size-md);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history__title--active {
  color: var(--color-ink);
  font-weight: 500;
}

.history__date {
  font-size: var(--font-size-2xs);
  white-space: nowrap;
}

/* Löschen ist endgültig und steht deshalb nicht permanent im Blick — es
   erscheint erst, wenn die Zeile angesteuert wird. */
.history__delete {
  font-size: var(--font-size-2xs);
  opacity: 0;
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.history__row:hover .history__delete,
.history__delete:focus-visible {
  opacity: 1;
}

.history__delete:hover {
  color: var(--color-error);
}
</style>
