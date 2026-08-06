<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";
import { api, type PaperlessDocument, type DocSummary } from "../api/client";
import { formatDaysUntil } from "../utils/dates";
import IconClose from "./icons/IconClose.vue";
import IconChat from "./icons/IconChat.vue";

const BASE_URL = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8001";

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
      [document.value, detail.value] = await Promise.all([api.getDocument(id), api.getDocumentDetail(id)]);
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
  <div v-if="store.sidePanel !== null" class="panel-backdrop" @click.self="store.closePanel()">
    <div class="panel">
      <button class="panel__close" @click="store.closePanel()" aria-label="Schließen"><IconClose /></button>

      <template v-if="store.sidePanel.type === 'document'">
        <p v-if="loading" class="status">Lade...</p>
        <p v-if="error" class="status status--error">{{ error }}</p>

        <div v-if="document && detail" class="panel__body">
          <aside class="panel__meta">
            <h2>{{ detail.title }}</h2>
            <p class="meta">Erstellt: {{ detail.created?.slice(0, 10) }}</p>
            <p v-if="detail.correspondent_name" class="meta">Korrespondent: {{ detail.correspondent_name }}</p>
            <p v-if="detail.document_type_name" class="meta">Typ: {{ detail.document_type_name }}</p>

            <span class="status-pill">{{ detail.status }}</span>
            <p v-if="detail.due_date" class="due-pill">
              Frist: {{ detail.due_date }} ({{ formatDaysUntil(Math.round((new Date(detail.due_date).getTime() - Date.now()) / 86400000)) }})
            </p>

            <div class="panel__tags">
              <span v-for="tag in detail.tags" :key="tag.id" class="tag-pill" :style="{ '--tag-color': tag.color }">
                {{ tag.name }}
              </span>
            </div>

            <button type="button" class="ask-button" @click="ask"><IconChat /> Im Chat nachfragen</button>
          </aside>

          <div class="panel__doc">
            <div class="tabs">
              <button
                type="button"
                :class="['tab', { 'tab--active': activeTab === 'original' }]"
                @click="activeTab = 'original'"
              >
                Original
              </button>
              <button
                type="button"
                :class="['tab', { 'tab--active': activeTab === 'text' }]"
                @click="activeTab = 'text'"
              >
                Text (OCR)
              </button>
            </div>

            <iframe v-if="activeTab === 'original'" :src="fileUrl" class="pdf-frame" title="Originaldokument" />
            <pre v-else class="content">{{ document.content }}</pre>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.panel-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(48, 79, 91, 0.28);
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-3);
  box-sizing: border-box;
}

.panel {
  position: relative;
  width: min(1100px, 92vw);
  height: min(88vh, 900px);
  background: var(--surface-glass-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: var(--space-4);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}

.panel__body {
  display: flex;
  gap: var(--space-4);
  min-height: 0;
  flex: 1;
}

.panel__meta {
  flex: 0 0 38%;
  min-width: 240px;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  overflow-y: auto;
}

.panel__doc {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.panel__close {
  position: absolute;
  top: var(--space-2);
  right: var(--space-2);
  min-height: 44px;
  min-width: 44px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-white);
  border-radius: var(--radius-pill);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  font-size: var(--font-size-base);
  color: var(--color-text-muted);
}

.meta {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin: 0;
}

.status-pill {
  align-self: flex-start;
  border-radius: var(--radius-pill);
  padding: 0.2rem 0.8rem;
  font-size: var(--font-size-xs);
  font-family: var(--font-display);
  font-weight: 600;
  background: var(--color-white);
  border: 1px solid var(--color-border-strong);
  color: var(--color-heading-strong);
  text-transform: uppercase;
}

.due-pill {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-error);
}

.panel__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.tag-pill {
  border-radius: var(--radius-pill);
  padding: 0.1rem 0.6rem;
  font-size: var(--font-size-xs);
  font-family: var(--font-display);
  font-weight: 600;
  background: var(--color-white);
  color: var(--tag-color, var(--color-text-muted));
  border: 1px solid var(--tag-color, var(--color-border));
}

.ask-button {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: auto;
  align-self: flex-start;
  border: 1px solid var(--color-brand-blue-strong);
  background: var(--color-cream-light);
  color: var(--color-brand-blue-dark);
  border-radius: var(--radius-pill);
  padding: 0.5rem 1rem;
  font: inherit;
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.tabs {
  display: flex;
  gap: 0.4rem;
  margin-bottom: var(--space-2);
}

.tab {
  border: 1px solid transparent;
  background: none;
  padding: 0.5rem 0.9rem;
  border-radius: var(--radius-pill);
  color: var(--color-text-muted);
  font: inherit;
  font-family: var(--font-display);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
}

.tab--active {
  color: var(--color-brand-blue-dark);
  background: var(--color-white);
  border-color: var(--color-border);
  box-shadow: var(--shadow-sm);
}

.pdf-frame {
  flex: 1;
  min-height: 0;
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.content {
  flex: 1;
  overflow-y: auto;
  white-space: pre-wrap;
  background: var(--color-white);
  border: 1px solid var(--color-border);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  font-family: var(--font-body);
  margin: 0;
}

.status--error {
  color: var(--color-error);
}
</style>
