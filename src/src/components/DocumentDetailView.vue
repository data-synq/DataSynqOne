<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";
import { api, type PaperlessDocument, type DocSummary } from "../api/client";
import { categoryLabel, STATUS_COLORS, STATUS_LABELS } from "../theme/statusColors";
import { daysUntil, formatDate, formatDaysUntil } from "../utils/dates";

const props = defineProps<{ documentId: number; activeTab: "original" | "text" }>();

const BASE_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8001";

const store = useChatStore();
const document = ref<PaperlessDocument | null>(null);
const detail = ref<DocSummary | null>(null);
const error = ref<string | null>(null);
const loading = ref(false);
const metaCollapsed = ref(false);

const fileUrl = computed(() => `${BASE_URL}/documents/${props.documentId}/file`);

const due = computed(() => {
  if (!detail.value?.due_date) return null;
  const days = daysUntil(detail.value.due_date);
  return {
    days,
    label: formatDaysUntil(days),
    date: formatDate(detail.value.due_date),
    color: days < 0 ? STATUS_COLORS.overdue : days <= 3 ? STATUS_COLORS.urgent : "var(--color-text)",
  };
});

const statusColor = computed(() =>
  detail.value ? (STATUS_COLORS[detail.value.status] ?? "var(--color-text)") : "var(--color-text)",
);

// Nur die inhaltlichen Schlagworte. Frist, Objekt, Status und Kategorie
// stehen bereits als eigene Zeilen darüber — ein zweites Mal als Rohtag
// wären sie Rauschen in genau dem Feld, das den Rest tragen soll.
const STRUCTURAL_TAG = /^(due:|obj-)/i;
const topicTags = computed(
  () =>
    detail.value?.tags.filter(
      (t) =>
        !STRUCTURAL_TAG.test(t.name) &&
        t.name !== detail.value?.status &&
        t.name !== detail.value?.category,
    ) ?? [],
);

watch(
  () => props.documentId,
  async (id) => {
    document.value = null;
    detail.value = null;
    error.value = null;
    if (id === null || id === undefined) return;
    loading.value = true;
    try {
      [document.value, detail.value] = await Promise.all([
        api.getDocument(id),
        api.getDocumentDetail(id),
      ]);
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

function ask() {
  if (!detail.value) return;
  store.askAboutDocument(detail.value.id, detail.value.title);
}
</script>

<template>
  <div class="detail">
    <p v-if="loading" class="detail__status mono">Lade …</p>
    <p v-else-if="error" class="detail__status detail__status--error">{{ error }}</p>

    <template v-if="document && detail">
      <aside class="detail__meta" :class="{ 'detail__meta--collapsed': metaCollapsed }">
        <button
          type="button"
          class="detail__meta-toggle"
          :aria-label="metaCollapsed ? 'Metadaten einblenden' : 'Metadaten ausblenden'"
          :title="metaCollapsed ? 'Metadaten einblenden' : 'Metadaten ausblenden'"
          @click="metaCollapsed = !metaCollapsed"
        >
          <svg viewBox="0 0 16 16" aria-hidden="true" :class="{ 'detail__meta-toggle-icon--flipped': metaCollapsed }">
            <path d="M10 3 5 8 10 13" fill="none" stroke="currentColor" stroke-width="1.5" />
          </svg>
        </button>

        <template v-if="!metaCollapsed">
          <dl class="facts">
            <dt class="mono">Status</dt>
            <dd :style="{ color: statusColor }">{{ STATUS_LABELS[detail.status] ?? detail.status }}</dd>

            <template v-if="due">
              <dt class="mono">Frist</dt>
              <dd :style="{ color: due.color }">{{ due.date }} · {{ due.label }}</dd>
            </template>

            <dt class="mono">Erstellt</dt>
            <dd>{{ formatDate(detail.created) }}</dd>

            <dt class="mono">Korrespondent</dt>
            <dd>{{ detail.correspondent_name ?? "—" }}</dd>

            <dt class="mono">Kategorie</dt>
            <dd>{{ categoryLabel(detail.category) }}</dd>

            <template v-if="detail.document_type_name">
              <dt class="mono">Typ</dt>
              <dd>{{ detail.document_type_name }}</dd>
            </template>

            <dt class="mono">Objekt</dt>
            <dd>{{ detail.object_name ?? "—" }}</dd>

            <dt class="mono">Schlagworte</dt>
            <dd>{{ topicTags.length ? topicTags.map((t) => t.name).join(", ") : "—" }}</dd>
          </dl>

          <div class="detail__actions">
            <button type="button" class="button--primary" @click="ask">Im Assistenten nachfragen</button>
          </div>
        </template>
      </aside>

      <div class="detail__body">
        <iframe
          v-if="activeTab === 'original'"
          :src="fileUrl"
          class="detail__frame"
          title="Dokumentvorschau"
          sandbox="allow-scripts allow-same-origin allow-downloads"
          referrerpolicy="no-referrer"
        />
        <div v-else class="detail__text">{{ document.content }}</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* auto statt einer festen Spaltenbreite: die Breite kommt von .detail__meta
   selbst, damit sie sich beim Ein-/Ausklappen mit animieren lässt — ein fixer
   Grid-Track würde das Kind zwar schmaler zeichnen, die Spalte selbst aber
   nicht mitschrumpfen lassen. */
.detail {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  min-height: 0;
  height: 100%;
}

.detail__status {
  grid-column: 1 / -1;
  padding: 1.25rem;
  margin: 0;
}

.detail__status--error {
  color: var(--color-error);
}

.detail__meta {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 260px;
  padding: 1.375rem 1.25rem;
  border-right: 1px solid var(--color-line);
  overflow-y: auto;
  transition: width var(--duration-slow) var(--ease-emphasized);
}

/* Auf eine schmale Randleiste zusammengefaltet: nur der Umschalter bleibt,
   die PDF-/Textansicht daneben gewinnt den frei werdenden Platz — dieselbe
   Breitenlogik wie bei der Historie- und Board-Randleiste. */
.detail__meta--collapsed {
  width: 36px;
  padding-inline: 0;
  align-items: center;
  overflow: hidden;
}

.detail__meta-toggle {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-bottom: 0.75rem;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-ink-4);
  cursor: pointer;
}

.detail__meta-toggle:hover {
  color: var(--color-ink);
}

.detail__meta-toggle svg {
  width: 13px;
  height: 13px;
  transition: transform var(--duration-fast) var(--ease-standard);
}

.detail__meta-toggle-icon--flipped {
  transform: rotate(180deg);
}

/* Label links, Wert rechts, auf einer Achse: eine Dokumentenakte liest man
   spaltenweise nach dem Feld, das man sucht, nicht der Reihe nach. */
.facts {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 0.5625rem 0.625rem;
  margin: 0;
  font-size: var(--font-size-md);
}

.facts dt {
  font-size: var(--font-size-2xs);
  letter-spacing: 0.04em;
  color: var(--color-ink-5);
}

.facts dd {
  margin: 0;
  color: var(--color-text);
  overflow-wrap: anywhere;
}

.detail__actions {
  margin-top: auto;
  padding-top: 1.25rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.625rem;
}

.detail__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 1rem 1.25rem 1.25rem;
}

.detail__frame {
  flex: 1;
  min-height: 0;
  width: 100%;
  border: 1px solid var(--color-line-soft);
}

.detail__text {
  flex: 1;
  min-height: 0;
  padding: 1.25rem 1.5rem;
  border: 1px solid var(--color-line-soft);
  overflow-y: auto;
  max-width: 68ch;
  white-space: pre-wrap;
  line-height: var(--line-height-prose);
  color: var(--color-text);
}

/* Reagiert auf die Breite des Boards selbst, nicht auf die des Fensters —
   das Board kann schmal sein, auch wenn der Bildschirm breit ist. */
@container (max-width: 560px) {
  .detail {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
  }

  .detail__meta {
    width: 100%;
    border-right: 0;
    border-bottom: 1px solid var(--color-line);
  }

  .detail__meta--collapsed {
    width: 100%;
    height: 40px;
    flex-direction: row;
  }

  .detail__meta--collapsed .detail__meta-toggle {
    margin-bottom: 0;
  }
}
</style>
