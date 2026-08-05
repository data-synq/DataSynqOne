<script setup lang="ts">
import { onMounted } from "vue";
import { useChatStore } from "../stores/chat";
import { useSessionsStore } from "../stores/sessions";
import IconTrash from "./icons/IconTrash.vue";

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
  const diffMs = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diffMs / 86_400_000);
  if (days <= 0) return "Heute";
  if (days === 1) return "Gestern";
  if (days < 7) return `vor ${days} Tagen`;
  return new Date(iso).toLocaleDateString("de-DE");
}
</script>

<template>
  <div class="history-panel">
    <p v-if="sessionsStore.loading" class="status">Lade...</p>
    <ul class="sessions">
      <li
        v-for="s in sessionsStore.items"
        :key="s.id"
        :class="['session-item', { 'session-item--active': s.id === chatStore.sessionId }]"
        @click="select(s.id)"
      >
        <div class="session-item__text">
          <span class="session-item__title">{{ s.title }}</span>
          <span class="session-item__date">{{ relativeDate(s.updated_at) }}</span>
        </div>
        <button type="button" class="session-item__delete" aria-label="Löschen" @click="remove(s.id, $event)">
          <IconTrash />
        </button>
      </li>
    </ul>
    <p v-if="!sessionsStore.loading && !sessionsStore.items.length" class="status">
      Noch keine gespeicherten Chats.
    </p>
  </div>
</template>

<style scoped>
.history-panel {
  border-bottom: 1px solid var(--color-border);
  padding: var(--space-2) var(--page-padding);
  max-height: 240px;
  overflow-y: auto;
}

.sessions {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.5rem 0.6rem;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.session-item:hover {
  background: var(--color-surface-muted);
}

.session-item--active {
  background: var(--color-surface-muted);
  box-shadow: var(--shadow-sm);
}

.session-item__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.session-item__title {
  color: var(--color-heading-strong);
  font-size: var(--font-size-sm);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-item__date {
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
}

.session-item__delete {
  flex: none;
  border: none;
  background: none;
  cursor: pointer;
  opacity: 0.6;
  color: var(--color-text-muted);
  display: flex;
}

.session-item__delete:hover {
  opacity: 1;
  color: var(--color-error);
}

.status {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin: 0.4rem 0;
}
</style>
