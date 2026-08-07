<script setup lang="ts">
import { computed } from "vue";
import type { Deadline } from "../../api/client";
import { STATUS_COLORS } from "../../theme/statusColors";
import { useChatStore } from "../../stores/chat";
import { formatDaysUntil } from "../../utils/dates";

const props = defineProps<{ deadlines: Deadline[] }>();
const chat = useChatStore();

// Drei Gruppen statt einer durchlaufenden Liste: der Unterschied zwischen
// "gerissen" und "steht an" ist der einzige, der hier über die Reihenfolge
// des Tages entscheidet — er darf nicht davon abhängen, dass jemand die
// Datumsspalte liest.
const groups = computed(() => {
  const defs = [
    { key: "over", head: "Überschritten", color: STATUS_COLORS.overdue, test: (d: number) => d < 0 },
    {
      key: "week",
      head: "Diese Woche",
      color: STATUS_COLORS.urgent,
      test: (d: number) => d >= 0 && d <= 7,
    },
    { key: "later", head: "Später", color: "var(--color-ink-5)", test: (d: number) => d > 7 },
  ];
  return defs
    .map((def) => ({ ...def, items: props.deadlines.filter((d) => def.test(d.days_until)) }))
    .filter((group) => group.items.length);
});

const soonCount = computed(
  () => props.deadlines.filter((d) => d.days_until >= 0 && d.days_until <= 3).length,
);

function color(daysUntil: number): string {
  if (daysUntil < 0) return STATUS_COLORS.overdue;
  if (daysUntil <= 3) return STATUS_COLORS.urgent;
  return "var(--color-ink-4)";
}

function meta(deadline: Deadline): string {
  return [deadline.correspondent_name, deadline.object_name].filter(Boolean).join(" · ");
}
</script>

<template>
  <aside class="deadlines">
    <div class="section-head">
      <h2>Fristen</h2>
      <span class="mono">{{ soonCount }} in 3 Tagen fällig</span>
    </div>

    <p v-if="!groups.length" class="deadlines__empty mono">Keine anstehenden Fristen.</p>

    <div v-for="group in groups" :key="group.key" class="deadlines__group">
      <p class="deadlines__group-head" :style="{ color: group.color }">{{ group.head }}</p>
      <div
        v-for="d in group.items"
        :key="d.document_id"
        class="deadlines__row row-link"
        role="button"
        tabindex="0"
        @click="chat.openDocument(d.document_id)"
        @keydown.enter="chat.openDocument(d.document_id)"
        @keydown.space.prevent="chat.openDocument(d.document_id)"
      >
        <div class="deadlines__main">
          <span class="deadlines__title">{{ d.title }}</span>
          <span v-if="meta(d)" class="deadlines__meta mono">{{ meta(d) }}</span>
        </div>
        <span class="deadlines__badge mono" :style="{ color: color(d.days_until) }">
          {{ formatDaysUntil(d.days_until) }}
        </span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.deadlines__empty {
  padding: 1.5rem 0;
}

.deadlines__group {
  margin-top: 0.875rem;
}

.deadlines__group-head {
  margin: 0;
  padding-bottom: 0.3125rem;
  border-bottom: 1px solid var(--color-line);
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.deadlines__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.5625rem 0 0.625rem;
}

.deadlines__main {
  display: flex;
  flex-direction: column;
  gap: 0.1875rem;
  min-width: 0;
}

.deadlines__title {
  font-size: var(--font-size-md);
  color: var(--color-text);
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.deadlines__meta {
  font-size: var(--font-size-2xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.deadlines__badge {
  font-size: var(--font-size-xs);
  white-space: nowrap;
}
</style>
