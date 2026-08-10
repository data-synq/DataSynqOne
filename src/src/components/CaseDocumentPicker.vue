<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { api, ApiError, type CaseDocumentRef, type PaperlessDocument } from "../api/client";

const props = defineProps<{ trackingId: string; existingIds: number[] }>();
const emit = defineEmits<{ attached: [docs: CaseDocumentRef[]]; close: [] }>();

const BASE_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8001";

const query = ref("");
const results = ref<PaperlessDocument[]>([]);
const searching = ref(false);
const searchError = ref<string | null>(null);
const selectedIds = ref<Set<number>>(new Set());
// Bleibt stehen, statt beim Verlassen der Zeile zu verschwinden — man soll die
// zuletzt betrachtete Vorschau noch sehen koennen, waehrend man weitersucht.
const previewDoc = ref<PaperlessDocument | null>(null);
const saving = ref(false);
const saveError = ref<string | null>(null);

const SEARCH_DEBOUNCE_MS = 250;

let debounce: ReturnType<typeof setTimeout> | null = null;
// Wie in AppTopBar.vue: schnelleres Tippen als Antworten eintreffen darf die
// letzte Eingabe nicht mit einer veralteten, aber später eintreffenden Antwort
// überschreiben.
let latestRequest = 0;

watch(query, (value) => {
  if (debounce) clearTimeout(debounce);
  const term = value.trim();
  if (term.length < 2) {
    results.value = [];
    searchError.value = null;
    searching.value = false;
    return;
  }
  searching.value = true;
  debounce = setTimeout(async () => {
    const request = ++latestRequest;
    try {
      const page = await api.searchDocuments(term);
      if (request !== latestRequest) return;
      results.value = page.results;
      searchError.value = null;
    } catch (e) {
      if (request !== latestRequest) return;
      results.value = [];
      searchError.value = e instanceof TypeError ? "Server nicht erreichbar." : "Suche fehlgeschlagen.";
    } finally {
      if (request === latestRequest) searching.value = false;
    }
  }, SEARCH_DEBOUNCE_MS);
});

function thumbnailUrl(id: number): string {
  return `${BASE_URL}/documents/${id}/thumbnail`;
}

function fileUrl(id: number): string {
  return `${BASE_URL}/documents/${id}/file`;
}

function isAttached(id: number): boolean {
  return props.existingIds.includes(id);
}

function toggleSelect(doc: PaperlessDocument) {
  if (isAttached(doc.id)) return;
  if (selectedIds.value.has(doc.id)) selectedIds.value.delete(doc.id);
  else selectedIds.value.add(doc.id);
  previewDoc.value = doc;
}

async function submit() {
  if (!selectedIds.value.size || saving.value) return;
  saving.value = true;
  saveError.value = null;
  try {
    const docs = await api.attachCaseDocuments(props.trackingId, [...selectedIds.value]);
    emit("attached", docs);
    emit("close");
  } catch (e) {
    saveError.value = e instanceof ApiError ? e.message : "Dokumente konnten nicht zugeordnet werden.";
  } finally {
    saving.value = false;
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") emit("close");
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <div class="scrim" @click.self="emit('close')">
    <div class="picker" role="dialog" aria-modal="true" aria-label="Dokumente zuordnen">
      <div class="picker__head">
        <h3 class="picker__title">Dokumente zuordnen</h3>
        <button type="button" class="picker__close" title="Schließen" @click="emit('close')">✕</button>
      </div>

      <input
        v-model="query"
        type="search"
        class="picker__search"
        placeholder="Dokumente durchsuchen …"
        autocomplete="off"
        autofocus
      />

      <div class="picker__body">
        <div class="picker__list">
          <p v-if="searching" class="mono picker__note">Suche läuft …</p>
          <p v-else-if="searchError" class="picker__note picker__note--error">{{ searchError }}</p>
          <p v-else-if="query.trim().length < 2" class="mono picker__note">Mindestens 2 Zeichen eingeben.</p>
          <p v-else-if="!results.length" class="mono picker__note">Kein Treffer.</p>

          <label
            v-for="doc in results"
            :key="doc.id"
            class="picker__row"
            :class="{ 'picker__row--disabled': isAttached(doc.id) }"
            @mouseenter="previewDoc = doc"
          >
            <input
              type="checkbox"
              :checked="selectedIds.has(doc.id)"
              :disabled="isAttached(doc.id)"
              @change="toggleSelect(doc)"
            />
            <img class="picker__thumb" loading="lazy" :src="thumbnailUrl(doc.id)" alt="" />
            <span class="picker__row-info">
              <span class="picker__row-title">{{ doc.title }}</span>
              <span v-if="doc.original_file_name" class="mono picker__row-filename">{{ doc.original_file_name }}</span>
              <span v-if="doc.content" class="picker__row-snippet">{{ doc.content }}</span>
            </span>
            <span v-if="isAttached(doc.id)" class="badge mono">Bereits verknüpft</span>
          </label>
        </div>

        <div class="picker__preview">
          <template v-if="previewDoc && selectedIds.has(previewDoc.id)">
            <iframe
              class="picker__preview-frame"
              :src="fileUrl(previewDoc.id)"
              title="Dokumentvorschau"
              sandbox=""
              referrerpolicy="no-referrer"
            />
            <span class="picker__preview-title">{{ previewDoc.title }}</span>
          </template>
          <template v-else-if="previewDoc">
            <img class="picker__preview-img" :src="thumbnailUrl(previewDoc.id)" alt="" />
            <span class="picker__preview-title">{{ previewDoc.title }}</span>
            <span class="mono picker__preview-date">{{ previewDoc.created?.slice(0, 10) }}</span>
          </template>
          <p v-else class="mono picker__note">Dokument auswählen, um eine Vorschau zu sehen.</p>
        </div>
      </div>

      <p v-if="saveError" class="notice notice--error">{{ saveError }}</p>

      <div class="picker__footer">
        <span class="mono picker__count">{{ selectedIds.size }} ausgewählt</span>
        <button type="button" class="link-action" @click="emit('close')">Abbrechen</button>
        <button type="button" class="button--primary" :disabled="!selectedIds.size || saving" @click="submit">
          Hinzufügen ({{ selectedIds.size }})
        </button>
      </div>
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

.picker {
  display: flex;
  flex-direction: column;
  width: min(1040px, 96vw);
  max-height: min(760px, 92vh);
  padding: 1.25rem 1.5rem;
  background: var(--color-white);
  border: 1px solid var(--color-line-strong);
}

.picker__head {
  display: flex;
  align-items: center;
  margin-bottom: 0.75rem;
}

.picker__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: 500;
}

.picker__close {
  margin-left: auto;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-ink-4);
  cursor: pointer;
  font-size: var(--font-size-md);
}

.picker__close:hover {
  color: var(--color-error);
}

.picker__search {
  height: 30px;
  margin-bottom: 0.75rem;
  font-size: var(--font-size-md);
}

.picker__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: var(--space-3);
  min-height: 0;
  flex: 1;
}

.picker__list {
  overflow-y: auto;
  border: 1px solid var(--color-line);
}

.picker__note {
  margin: 0;
  padding: 0.75rem;
  color: var(--color-ink-4);
  font-size: var(--font-size-sm);
}

.picker__note--error {
  color: var(--color-error);
}

.picker__row {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.625rem;
  padding: 0.5rem 0.625rem;
  border-bottom: 1px solid var(--color-line-soft);
  cursor: pointer;
}

.picker__row:last-child {
  border-bottom: 0;
}

.picker__row:hover {
  background: var(--color-surface-muted);
}

.picker__row--disabled {
  cursor: default;
  opacity: 0.55;
}

.picker__thumb {
  width: 32px;
  height: 42px;
  object-fit: cover;
  background: var(--color-surface-muted);
  border: 1px solid var(--color-line-soft);
}

.picker__row-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.picker__row-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text);
}

.picker__row-filename,
.picker__row-snippet {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picker__row-filename {
  color: var(--color-ink-4);
  font-size: var(--font-size-xs);
}

.picker__row-snippet {
  color: var(--color-ink-5);
  font-size: var(--font-size-xs);
}

.picker__preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: var(--space-3);
  overflow-y: auto;
  background: var(--color-surface-muted);
  border: 1px solid var(--color-line);
  text-align: center;
}

.picker__preview-img {
  max-width: 100%;
  max-height: 320px;
  border: 1px solid var(--color-line-strong);
  background: var(--color-white);
}

/* Volle, mehrseitige Ansicht — nur fuer bereits ausgewaehlte Dokumente, damit
   nicht bei jedem fluechtigen Hover ein ganzes PDF geladen wird. */
.picker__preview-frame {
  width: 100%;
  flex: 1;
  min-height: 420px;
  border: 1px solid var(--color-line-strong);
  background: var(--color-white);
}

.picker__preview-title {
  font-size: var(--font-size-sm);
  color: var(--color-text);
}

.picker__preview-date {
  color: var(--color-ink-4);
  font-size: var(--font-size-xs);
}

.badge {
  padding: 0.05rem 0.3rem;
  border: 1px solid var(--color-line-strong);
  color: var(--color-ink-4);
  font-size: var(--font-size-2xs);
  white-space: nowrap;
}

.notice {
  margin: 0.75rem 0 0;
  padding: 0.5rem 0.75rem;
  border-left: 2px solid var(--color-error);
  background: var(--color-surface-muted);
  font-size: var(--font-size-sm);
  color: var(--color-error);
}

.picker__footer {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: 0.75rem;
  padding-top: 0.5rem;
}

.picker__count {
  margin-right: auto;
  color: var(--color-ink-4);
  font-size: var(--font-size-xs);
}
</style>
