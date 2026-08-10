<script setup lang="ts">
import type { BoardEvent } from "../api/client";
import { useChatStore } from "../stores/chat";

defineProps<{ event: BoardEvent }>();

const store = useChatStore();
</script>

<template>
  <button type="button" class="button--secondary chip" @click="store.reopenBoardEvent(event)">
    <span class="chip__dot" />
    {{ event.title }} im Board geöffnet
  </button>
</template>

<style scoped>
/* Eigene, dezentere Randfarbe statt der Standard-Schaltfläche — im
   Chatverlauf soll das eher als Hinweis lesbar sein denn als Aktionsknopf. */
.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.75rem 0;
  border-color: var(--color-line);
}

.chip__dot {
  width: 6px;
  height: 6px;
  flex: none;
  background: var(--color-accent);
}
</style>
