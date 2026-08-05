<script setup lang="ts">
import type { DocSummary } from "../../api/client";
import { STATUS_COLORS } from "../../theme/statusColors";
import DocumentCard from "./DocumentCard.vue";

const props = defineProps<{
  byStatus: Record<string, DocSummary[]>;
  kpis: Record<string, number>;
  focusedStatus: string | null;
}>();

const columns = [
  { key: "open", label: "Offen" },
  { key: "urgent", label: "Dringend" },
  { key: "overdue", label: "Überfällig" },
];
</script>

<template>
  <section class="board">
    <div
      v-for="col in columns"
      :key="col.key"
      :class="['board__col', { 'board__col--focused': focusedStatus === col.key }]"
    >
      <h3 class="board__col-title" :style="{ '--accent': STATUS_COLORS[col.key] }">
        {{ col.label }}
        <span class="board__count">
          {{ (props.byStatus[col.key] ?? []).length }}
          <template v-if="(props.kpis[col.key] ?? 0) > (props.byStatus[col.key] ?? []).length">
            / {{ props.kpis[col.key] }}
          </template>
        </span>
      </h3>
      <div class="board__col-list">
        <DocumentCard v-for="doc in props.byStatus[col.key] ?? []" :key="doc.id" :doc="doc" />
        <p v-if="!(props.byStatus[col.key] ?? []).length" class="board__empty">Keine Dokumente.</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.board {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-2);
}

.board__col {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  border-radius: var(--radius-md);
  transition: box-shadow var(--duration-normal) var(--ease-standard);
}

.board__col--focused {
  box-shadow: var(--shadow-md);
}

.board__col-title {
  margin: 0;
  font-family: var(--font-display);
  color: var(--color-heading-strong);
  border-bottom: 2px solid var(--accent, var(--color-border));
  padding-bottom: 0.3rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.board__count {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.board__col-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.board__empty {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}
</style>
