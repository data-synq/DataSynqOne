<script setup lang="ts">
import type { Deadline } from "../../api/client";
import { useChatStore } from "../../stores/chat";
import { formatDaysUntil } from "../../utils/dates";

defineProps<{ deadlines: Deadline[] }>();
const store = useChatStore();
</script>

<template>
  <section class="deadlines">
    <h3 class="deadlines__title">Fristen</h3>
    <p v-if="!deadlines.length" class="deadlines__empty">Keine anstehenden Fristen.</p>
    <ul class="deadlines__list">
      <li
        v-for="d in deadlines"
        :key="d.document_id"
        :class="['deadline-row', { 'deadline-row--overdue': d.days_until < 0, 'deadline-row--soon': d.days_until >= 0 && d.days_until <= 3 }]"
        @click="store.openDocument(d.document_id)"
      >
        <div class="deadline-row__main">
          <span class="deadline-row__title">{{ d.title }}</span>
          <span v-if="d.correspondent_name" class="deadline-row__correspondent">{{ d.correspondent_name }}</span>
        </div>
        <span class="deadline-row__badge">{{ formatDaysUntil(d.days_until) }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.deadlines {
  background: var(--surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  padding: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  height: 100%;
  box-sizing: border-box;
}

.deadlines__title {
  margin: 0;
  font-family: var(--font-display);
  color: var(--color-heading-strong);
}

.deadlines__empty {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.deadlines__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  overflow-y: auto;
}

.deadline-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: 0.5rem 0.7rem;
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--color-border);
  background: var(--color-white);
  cursor: pointer;
}

.deadline-row--soon {
  border-left-color: var(--color-brand-gold-dark);
}

.deadline-row--overdue {
  border-left-color: var(--color-error);
}

.deadline-row__main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.deadline-row__title {
  font-size: var(--font-size-sm);
  color: var(--color-heading-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.deadline-row__correspondent {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.deadline-row__badge {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
}
</style>
