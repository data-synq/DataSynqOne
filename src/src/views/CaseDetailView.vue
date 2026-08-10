<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useCaseContextStore } from "../stores/caseContext";
import { useChatStore } from "../stores/chat";
import { api, ApiError, type CaseDetail, type CaseEvent, type PaperlessDocument } from "../api/client";
import { formatDateTime } from "../utils/dates";
import CaseDependencyGraph from "../components/CaseDependencyGraph.vue";
import CaseDocumentPicker from "../components/CaseDocumentPicker.vue";
import CaseEventTimeline from "../components/CaseEventTimeline.vue";
import ConfirmDialog from "../components/ConfirmDialog.vue";

const route = useRoute();
const router = useRouter();
const chat = useChatStore();
const caseContext = useCaseContextStore();

const detail = ref<CaseDetail | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const noteBody = ref("");
const savingNote = ref(false);
const busy = ref(false);
const showPicker = ref(false);
const pendingDetachId = ref<number | null>(null);
const documentDetails = ref<Map<number, PaperlessDocument>>(new Map());

const trackingId = computed(() => String(route.params.trackingId));

const ROLE_LABELS: Record<string, string> = {
  email: "E-Mail",
  attachment: "Anhang",
  reply: "Antwort",
  linked: "Verknüpft",
};

function docTitle(paperlessId: number): string {
  return documentDetails.value.get(paperlessId)?.title ?? `DOK-${paperlessId}`;
}

function docSnippet(paperlessId: number): string {
  return documentDetails.value.get(paperlessId)?.content ?? "";
}

function openEventLink(event: CaseEvent) {
  if (!event.link_kind || !event.link_id) return;
  if (event.link_kind === "note") {
    document.getElementById(`note-${event.link_id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  } else if (event.link_kind === "case") {
    chat.openCasePopup(event.link_id);
  } else if (event.link_kind === "document") {
    chat.openDocument(Number(event.link_id));
  } else if (event.link_kind === "session") {
    chat.openSession(event.link_id);
  }
}

async function load() {
  loading.value = true;
  try {
    detail.value = await api.getCase(trackingId.value);
    error.value = null;
    caseContext.setActiveCase({
      trackingId: detail.value.tracking_id,
      title: detail.value.title,
      status: detail.value.status,
    });
    loadDocumentDetails(detail.value.documents.map((d) => d.paperless_id));
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Das Anliegen konnte nicht geladen werden.";
  } finally {
    loading.value = false;
  }
}

// Titel und OCR-Text stehen nicht in CaseDocumentRef (nur paperless_id/role/
// added_at) — für die Übersicht in der Liste holt sich die Seite sie separat
// pro Dokument. Läuft im Hintergrund, damit die Liste nicht auf Paperless
// wartet: erst erscheint "DOK-<id>", der echte Titel/Text folgt nach.
function loadDocumentDetails(paperlessIds: number[]) {
  documentDetails.value = new Map();
  for (const id of paperlessIds) {
    api
      .getDocument(id)
      .then((doc) => documentDetails.value.set(id, doc))
      .catch(() => {
        /* einzelnes Dokument nicht erreichbar — Fallback-Anzeige bleibt bestehen */
      });
  }
}

onUnmounted(() => caseContext.clearActiveCase());

async function addNote() {
  if (!noteBody.value.trim()) return;
  savingNote.value = true;
  try {
    await api.addCaseNote(trackingId.value, noteBody.value.trim());
    noteBody.value = "";
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Notiz konnte nicht gespeichert werden.";
  } finally {
    savingNote.value = false;
  }
}

// Schneller Wechsel zwischen abhängigen Anliegen direkt in dieser Ansicht,
// ohne den Umweg über das Popup — die Route wechselt, watch(trackingId, load)
// lädt den neuen Fall nach, ohne die Seite neu zu laden.
function switchTo(otherTrackingId: string) {
  if (otherTrackingId === trackingId.value) return;
  router.push(`/anliegen/${otherTrackingId}`);
}

async function toggleStatus() {
  if (!detail.value) return;
  busy.value = true;
  error.value = null;
  try {
    if (detail.value.status === "open") {
      await api.closeCase(trackingId.value);
      notice.value = "Anliegen geschlossen.";
    } else {
      await api.reopenCase(trackingId.value);
      notice.value = "Anliegen wieder geöffnet.";
    }
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Änderung ist fehlgeschlagen.";
  } finally {
    busy.value = false;
  }
}

async function confirmLink(dependentId: string, prerequisiteId: string) {
  error.value = null;
  try {
    await api.confirmCaseLink(dependentId, prerequisiteId);
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Verknüpfung konnte nicht bestätigt werden.";
  }
}

async function rejectLink(dependentId: string, prerequisiteId: string) {
  error.value = null;
  try {
    await api.removeCaseLink(dependentId, prerequisiteId);
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Verknüpfung konnte nicht entfernt werden.";
  }
}

async function onDocumentsAttached() {
  showPicker.value = false;
  await load();
}

function requestDetach(paperlessId: number) {
  pendingDetachId.value = paperlessId;
}

async function confirmDetach() {
  if (pendingDetachId.value === null) return;
  const paperlessId = pendingDetachId.value;
  pendingDetachId.value = null;
  error.value = null;
  try {
    await api.detachCaseDocument(trackingId.value, paperlessId);
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Das Dokument konnte nicht entfernt werden.";
  }
}

watch(trackingId, load, { immediate: true });
</script>

<template>
  <div class="container case-detail">
    <p v-if="loading" class="mono case-detail__state">Wird geladen …</p>
    <p v-else-if="error && !detail" class="notice notice--error" role="alert">{{ error }}</p>

    <template v-else-if="detail">
      <div class="section-head">
        <h2>
          <span class="mono case-detail__id">{{ detail.tracking_id }}</span>
          {{ detail.title }}
        </h2>
        <div class="head-actions">
          <RouterLink
            :to="{ path: '/anliegen/graph', query: { focus: detail.tracking_id } }"
            class="link-action"
          >
            Im Graph anzeigen
          </RouterLink>
          <RouterLink to="/anliegen" class="link-action">Zurück zur Liste</RouterLink>
        </div>
      </div>

      <p v-if="notice" class="notice notice--ok" role="status">{{ notice }}</p>
      <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>

      <div class="case-detail__grid">
        <aside class="case-detail__meta">
          <dl class="facts">
            <dt class="mono">Status</dt>
            <dd :class="{ 'is-closed': detail.status === 'closed' }">
              {{ detail.status === "open" ? "Offen" : "Geschlossen" }}
            </dd>

            <dt class="mono">Absender</dt>
            <dd>{{ detail.sender_email ?? "—" }}</dd>

            <dt class="mono">Objekt</dt>
            <dd>{{ detail.object_code ?? "—" }}</dd>

            <dt class="mono">Angelegt</dt>
            <dd>{{ formatDateTime(detail.created_at) }}</dd>

            <template v-if="detail.closed_at">
              <dt class="mono">Geschlossen</dt>
              <dd>{{ formatDateTime(detail.closed_at) }}</dd>
            </template>
          </dl>

          <div v-if="detail.summary" class="case-detail__summary">
            <span class="mono case-detail__summary-label">Zusammenfassung</span>
            <p>{{ detail.summary }}</p>
          </div>

          <div class="case-detail__actions">
            <button type="button" class="button--primary" :disabled="busy" @click="toggleStatus">
              {{ detail.status === "open" ? "Anliegen schließen" : "Wieder öffnen" }}
            </button>
            <button
              type="button"
              class="button--secondary"
              @click="chat.askAboutCase(detail.tracking_id, detail.title)"
            >
              Im Assistenten nachfragen
            </button>
          </div>
        </aside>

        <div class="case-detail__body">
          <section class="case-detail__section">
            <div class="case-detail__heading-row">
              <h3 class="case-detail__heading">Dokumente</h3>
              <button type="button" class="link-action" @click="showPicker = true">+ Dokument hinzufügen</button>
            </div>
            <ul v-if="detail.documents.length" class="doc-list">
              <li v-for="doc in detail.documents" :key="doc.paperless_id">
                <button
                  type="button"
                  class="doc-list__link"
                  :title="docTitle(doc.paperless_id)"
                  @click="chat.openDocument(doc.paperless_id)"
                >
                  {{ docTitle(doc.paperless_id) }}
                </button>
                <span v-if="docSnippet(doc.paperless_id)" class="doc-list__snippet">
                  {{ docSnippet(doc.paperless_id) }}
                </span>
                <span class="badge mono">{{ ROLE_LABELS[doc.role] ?? doc.role }}</span>
                <button
                  type="button"
                  class="doc-list__remove"
                  title="Dokument von diesem Anliegen lösen"
                  @click="requestDetach(doc.paperless_id)"
                >
                  ✕
                </button>
              </li>
            </ul>
            <p v-else class="mono case-detail__empty">Keine verknüpften Dokumente.</p>

            <ConfirmDialog
              v-if="pendingDetachId !== null"
              title="Dokument entfernen"
              :message="`Dokument DOK-${pendingDetachId} von diesem Anliegen lösen?`"
              confirm-label="Entfernen"
              danger
              @confirm="confirmDetach"
              @cancel="pendingDetachId = null"
            />

            <CaseDocumentPicker
              v-if="showPicker"
              :tracking-id="detail.tracking_id"
              :existing-ids="detail.documents.map((d) => d.paperless_id)"
              @attached="onDocumentsAttached"
              @close="showPicker = false"
            />
          </section>

          <!-- Alle Änderungen an diesem Anliegen, wer (oder was) sie ausgelöst
               hat, und — wo sinnvoll — ein Klick zur Quelle. -->
          <section class="case-detail__section">
            <h3 class="case-detail__heading">Zeitstrahl</h3>
            <CaseEventTimeline :events="detail.events" @open="openEventLink" />
          </section>

          <section class="case-detail__section">
            <h3 class="case-detail__heading">Notizen</h3>
            <ul v-if="detail.notes.length" class="note-list">
              <li v-for="note in detail.notes" :key="note.id" :id="`note-${note.id}`">
                <p class="note-list__body">{{ note.body }}</p>
                <p class="mono note-list__meta">
                  {{ note.author_name ?? "Unbekannt" }} · {{ formatDateTime(note.created_at) }}
                </p>
              </li>
            </ul>
            <p v-else class="mono case-detail__empty">Noch keine Notizen.</p>

            <form class="note-form" @submit.prevent="addNote">
              <textarea v-model="noteBody" rows="3" placeholder="Notiz hinzufügen …" />
              <button type="submit" class="button--secondary" :disabled="savingNote || !noteBody.trim()">
                {{ savingNote ? "Wird gespeichert …" : "Notiz speichern" }}
              </button>
            </form>
          </section>

          <!-- Ganz unten: der Abhängigkeitsgraph braucht am meisten Platz zum
               Erkunden, dafür liest man ihn nicht beiläufig wie die Abschnitte
               darüber. -->
          <section class="case-detail__section">
            <h3 class="case-detail__heading">Abhängigkeiten</h3>
            <CaseDependencyGraph
              v-if="detail.links.length"
              :tracking-id="detail.tracking_id"
              :links="detail.links"
              class="case-detail__mini-graph"
            />
            <ul v-if="detail.links.length" class="link-list">
              <li v-for="link in detail.links" :key="`${link.dependent_tracking_id}-${link.prerequisite_tracking_id}`">
                <button
                  type="button"
                  class="mono link-list__ref"
                  :class="{ 'link-list__ref--self': link.dependent_tracking_id === detail.tracking_id }"
                  @click="switchTo(link.dependent_tracking_id)"
                >
                  {{ link.dependent_tracking_id }}
                </button>
                baut auf
                <button
                  type="button"
                  class="mono link-list__ref"
                  :class="{ 'link-list__ref--self': link.prerequisite_tracking_id === detail.tracking_id }"
                  @click="switchTo(link.prerequisite_tracking_id)"
                >
                  {{ link.prerequisite_tracking_id }}
                </button>
                auf
                <span v-if="link.status === 'proposed'" class="badge mono">Vorschlag</span>
                <span v-if="link.status === 'proposed'" class="link-list__actions">
                  <button
                    type="button"
                    class="link-action"
                    @click="confirmLink(link.dependent_tracking_id, link.prerequisite_tracking_id)"
                  >
                    Bestätigen
                  </button>
                  <button
                    type="button"
                    class="link-action link-action--danger"
                    @click="rejectLink(link.dependent_tracking_id, link.prerequisite_tracking_id)"
                  >
                    Verwerfen
                  </button>
                </span>
              </li>
            </ul>
            <p v-else class="mono case-detail__empty">Keine Abhängigkeiten.</p>
          </section>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.case-detail {
  padding-block: var(--space-4) var(--space-5);
}

.case-detail__id {
  margin-right: var(--space-2);
  color: var(--color-ink-4);
}

.case-detail__state {
  padding-block: var(--space-3);
  color: var(--color-ink-4);
}

.head-actions {
  display: flex;
  gap: var(--space-2);
}

.case-detail__grid {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: var(--space-5);
  margin-top: var(--space-4);
}

.case-detail__meta {
  display: flex;
  flex-direction: column;
}

.facts {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
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

.facts dd.is-closed {
  color: var(--color-ink-4);
}

.case-detail__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.case-detail__summary {
  margin-top: var(--space-4);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-line);
}

.case-detail__summary-label {
  display: block;
  margin-bottom: 0.375rem;
  font-size: var(--font-size-2xs);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-ink-5);
}

.case-detail__summary p {
  margin: 0;
  color: var(--color-text);
  line-height: var(--line-height-body);
}

.case-detail__body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.case-detail__section {
  border-top: 1px solid var(--color-line);
  padding-top: var(--space-3);
}

.case-detail__heading {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-md);
  font-weight: 500;
}

.case-detail__heading-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
}

.case-detail__heading-row .case-detail__heading {
  margin-bottom: 0;
}

.case-detail__empty {
  color: var(--color-ink-4);
}

.case-detail__mini-graph {
  margin-bottom: var(--space-3);
}

.doc-list,
.note-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.doc-list li {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: var(--font-size-md);
}

/* Nebeneinander statt untereinander: bei mehreren Abhängigkeiten liest sich
   eine Reihe kompakter Karten schneller als eine lange Liste voller Zeilen,
   die sich alle nur im Tracking-ID unterscheiden. */
.link-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.link-list li {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  padding: 0.4rem 0.65rem;
  border: 1px solid var(--color-line);
  font-size: var(--font-size-sm);
}

.doc-list__link {
  flex-shrink: 0;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-link);
  font: inherit;
  text-decoration: underline dotted;
  cursor: pointer;
}

.doc-list__snippet {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-ink-4);
  font-size: var(--font-size-sm);
}

.doc-list__remove {
  margin-left: auto;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-ink-4);
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.doc-list__remove:hover {
  color: var(--color-error);
}

/* Direkter Wechsel zum anderen Anliegen, ohne den Umweg über das Popup. Die
   eigene Seite (--self) ist bewusst nicht wie ein Link gestaltet — ein Klick
   darauf tut nichts (switchTo() bricht dort ab), das soll man ihr auch ansehen. */
.link-list__ref {
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-link);
  font: inherit;
  font-size: inherit;
  text-decoration: underline dotted;
  cursor: pointer;
}

.link-list__ref--self {
  color: inherit;
  text-decoration: none;
  cursor: default;
}

.badge {
  padding: 0.05rem 0.3rem;
  border: 1px solid var(--color-line-strong);
  color: var(--color-ink-4);
  font-size: var(--font-size-2xs);
}

.link-list__actions {
  display: flex;
  gap: var(--space-2);
}

.link-action--danger:hover:not(:disabled) {
  color: var(--color-error);
}

.note-list li {
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--color-line-soft);
}

.note-list__body {
  margin: 0 0 0.25rem;
  white-space: pre-wrap;
}

.note-list__meta {
  margin: 0;
  color: var(--color-ink-4);
}

.note-form {
  margin-top: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.notice {
  margin-bottom: var(--space-2);
  padding: 0.625rem 0.75rem;
  border-left: 2px solid var(--color-success);
  background: var(--color-surface-muted);
  font-size: var(--font-size-md);
}

.notice--error {
  border-left-color: var(--color-error);
  color: var(--color-error);
}

@container (max-width: 640px) {
  .case-detail__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
