<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";
import { api, type PaperlessDocument, type DocSummary } from "../api/client";
import { categoryLabel, STATUS_COLORS, STATUS_LABELS } from "../theme/statusColors";
import { daysUntil, formatDate, formatDaysUntil } from "../utils/dates";

const BASE_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8001";

const store = useChatStore();
const document = ref<PaperlessDocument | null>(null);
const detail = ref<DocSummary | null>(null);
const error = ref<string | null>(null);
const loading = ref(false);
const activeTab = ref<"original" | "text">("original");

const fileUrl = computed(() => {
  const panel = store.sidePanel;
  return panel?.type === "document" ? `${BASE_URL}/documents/${panel.documentId}/file` : "";
});

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
  () => (store.sidePanel?.type === "document" ? store.sidePanel.documentId : null),
  async (id) => {
    document.value = null;
    detail.value = null;
    error.value = null;
    activeTab.value = "original";
    if (id === null) return;
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
);

function ask() {
  if (!detail.value) return;
  store.askAboutDocument(detail.value.id, detail.value.title);
}
</script>

<template>
  <div v-if="store.sidePanel !== null" class="scrim" @click.self="store.closePanel()">
    <div class="doc" role="dialog" aria-modal="true" aria-label="Dokument">
      <div class="doc__head">
        <div class="doc__ident">
          <span class="mono doc__id">DOK-{{ store.sidePanel.documentId }}</span>
          <span v-if="detail" class="doc__title">{{ detail.title }}</span>
          <span
            v-if="due && due.days < 0"
            class="mono doc__flag"
            :style="{ color: due.color, borderColor: due.color }"
          >
            Frist {{ due.label }}
          </span>
        </div>
        <button type="button" class="link-action" @click="store.closePanel()">Schließen</button>
      </div>

      <p v-if="loading" class="doc__status mono">Lade …</p>
      <p v-else-if="error" class="doc__status doc__status--error">{{ error }}</p>

      <template v-if="document && detail">
        <aside class="doc__meta">
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

          <div class="doc__actions">
            <button type="button" class="button--primary" @click="ask">Im Assistenten nachfragen</button>
          </div>
        </aside>

        <div class="doc__body">
          <div class="tabs">
            <button
              type="button"
              class="tabs__tab"
              :class="{ 'tabs__tab--active': activeTab === 'original' }"
              @click="activeTab = 'original'"
            >
              Original
            </button>
            <button
              type="button"
              class="tabs__tab"
              :class="{ 'tabs__tab--active': activeTab === 'text' }"
              @click="activeTab = 'text'"
            >
              Text (OCR)
            </button>
          </div>

          <iframe v-if="activeTab === 'original'" :src="fileUrl" class="doc__frame" title="Originaldokument" />
          <div v-else class="doc__text">{{ document.content }}</div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.scrim {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.75rem;
  background: rgba(22, 24, 20, 0.32);
}

.doc {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  grid-template-rows: 52px minmax(0, 1fr);
  width: min(1180px, 100%);
  height: min(880px, 100%);
  background: var(--color-white);
  border: 1px solid var(--color-line-strong);
}

.doc__head {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding-inline: 1.25rem;
  border-bottom: 1px solid var(--color-line);
}

.doc__ident {
  display: flex;
  align-items: baseline;
  gap: 0.625rem;
  min-width: 0;
}

.doc__id {
  flex: none;
}

.doc__title {
  font-weight: 500;
  color: var(--color-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc__flag {
  flex: none;
  padding: 0.125rem 0.4375rem;
  border: 1px solid currentColor;
  font-size: var(--font-size-2xs);
}

.doc__status {
  grid-column: 1 / -1;
  padding: 1.25rem;
  margin: 0;
}

.doc__status--error {
  color: var(--color-error);
}

.doc__meta {
  display: flex;
  flex-direction: column;
  padding: 1.375rem 1.25rem;
  border-right: 1px solid var(--color-line);
  overflow-y: auto;
}

/* Label links, Wert rechts, auf einer Achse: eine Dokumentenakte liest man
   spaltenweise nach dem Feld, das man sucht, nicht der Reihe nach. */
.facts {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 0.5625rem 0.75rem;
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

.doc__actions {
  margin-top: auto;
  padding-top: 1.25rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.625rem;
}

.doc__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 1rem 1.25rem 1.25rem;
}

.tabs {
  flex: none;
  display: flex;
  gap: 1.25rem;
  border-bottom: 1px solid var(--color-line);
}

.tabs__tab {
  margin-bottom: -1px;
  padding: 0 0 0.4375rem;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  font: inherit;
  font-size: var(--font-size-sm);
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-ink-4);
  cursor: pointer;
}

.tabs__tab--active {
  color: var(--color-ink);
  border-bottom-color: var(--color-ink);
}

.doc__frame {
  flex: 1;
  min-height: 0;
  width: 100%;
  margin-top: 1rem;
  border: 1px solid var(--color-line-soft);
}

.doc__text {
  flex: 1;
  min-height: 0;
  margin-top: 1rem;
  padding: 1.25rem 1.5rem;
  border: 1px solid var(--color-line-soft);
  overflow-y: auto;
  max-width: 68ch;
  white-space: pre-wrap;
  line-height: var(--line-height-prose);
  color: var(--color-text);
}

@media (max-width: 900px) {
  .doc {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: 52px auto minmax(0, 1fr);
  }

  .doc__meta {
    border-right: 0;
    border-bottom: 1px solid var(--color-line);
  }
}
</style>
