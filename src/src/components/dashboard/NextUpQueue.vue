<script setup lang="ts">
import { computed } from "vue";
import type { DocSummary } from "../../api/client";
import { categoryLabel, STATUS_COLORS, STATUS_DOT, STATUS_LABELS } from "../../theme/statusColors";
import { useChatStore } from "../../stores/chat";
import { useDashboardStore } from "../../stores/dashboard";
import { daysUntil, formatDaysUntil, formatShortDate } from "../../utils/dates";

const props = defineProps<{ queue: DocSummary[]; totalOpen: number }>();
const store = useDashboardStore();
const chat = useChatStore();

interface Row {
  doc: DocSummary;
  dot: string;
  badge: string;
  badgeColor: string;
  secondary: string;
}

const rows = computed<Row[]>(() =>
  props.queue.map((doc) => {
    const days = doc.due_date ? daysUntil(doc.due_date) : null;
    return {
      doc,
      dot: STATUS_DOT[doc.status] ?? STATUS_DOT.untagged,
      // Ohne Frist gibt es nichts herunterzuzählen. Dann sagt die Spalte,
      // wie lange der Vorgang schon liegt — das ist die nächstbeste Antwort
      // auf "wie dringend ist das".
      badge: days === null ? `seit ${formatShortDate(doc.created)}` : formatDaysUntil(days),
      badgeColor:
        days === null
          ? "var(--color-ink-5)"
          : days < 0
            ? STATUS_COLORS.overdue
            : days <= 3
              ? STATUS_COLORS.urgent
              : "var(--color-ink-5)",
      secondary: categoryLabel(doc.category ?? doc.document_type_name),
    };
  }),
);

const label = computed(() => {
  if (store.focusedStatus) {
    return `gefiltert: ${STATUS_LABELS[store.focusedStatus] ?? store.focusedStatus}`;
  }
  return `${rows.value.length} von ${props.totalOpen} Vorgängen`;
});

function meta(doc: DocSummary): string {
  return [doc.correspondent_name, doc.object_name].filter(Boolean).join(" · ");
}
</script>

<template>
  <section class="queue">
    <div class="section-head">
      <h2>Als Nächstes</h2>
      <div class="queue__head-right">
        <span class="mono">{{ label }}</span>
        <button v-if="store.isFiltered" type="button" class="link-action queue__clear" @click="store.clearFilters()">
          Filter aufheben
        </button>
      </div>
    </div>

    <p v-if="!rows.length" class="queue__empty mono">Nichts offen.</p>

    <div
      v-for="row in rows"
      :key="row.doc.id"
      class="queue__row row-link"
      role="button"
      tabindex="0"
      @click="chat.openDocument(row.doc.id)"
      @keydown.enter="chat.openDocument(row.doc.id)"
      @keydown.space.prevent="chat.openDocument(row.doc.id)"
    >
      <span class="queue__dot" :style="{ background: row.dot }" />
      <div class="queue__main">
        <span class="queue__title">{{ row.doc.title }}</span>
        <span v-if="meta(row.doc)" class="queue__meta mono">{{ meta(row.doc) }}</span>
      </div>
      <div class="queue__right">
        <span class="queue__badge mono" :style="{ color: row.badgeColor }">{{ row.badge }}</span>
        <span class="queue__secondary">{{ row.secondary }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.queue__head-right {
  display: flex;
  align-items: baseline;
  gap: 0.875rem;
}

.queue__clear {
  color: var(--color-accent);
}

.queue__clear:hover {
  color: var(--color-accent-strong);
  text-decoration: underline;
}

.queue__empty {
  padding: 1.5rem 0;
}

.queue__row {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 0 0.75rem;
  padding: 0.75rem 0.5rem 0.8125rem 0;
}

.queue__dot {
  width: 8px;
  height: 8px;
  justify-self: start;
  position: relative;
  top: -1px;
}

.queue__main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}

.queue__title {
  color: var(--color-ink);
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue__meta {
  font-size: var(--font-size-2xs);
  letter-spacing: 0.01em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue__right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.25rem;
  text-align: right;
}

.queue__badge {
  font-size: var(--font-size-xs);
  white-space: nowrap;
}

.queue__secondary {
  font-size: var(--font-size-md);
  color: var(--color-ink-4);
  white-space: nowrap;
}
</style>
