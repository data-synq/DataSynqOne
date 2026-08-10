<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";
import { api, ApiError, type CaseDetail } from "../api/client";
import { formatDateTime } from "../utils/dates";

const chat = useChatStore();

const detail = ref<CaseDetail | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

watch(
  () => chat.casePopupTrackingId,
  async (trackingId) => {
    detail.value = null;
    error.value = null;
    if (!trackingId) return;
    loading.value = true;
    try {
      detail.value = await api.getCase(trackingId);
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : "Das Anliegen konnte nicht geladen werden.";
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && chat.casePopupTrackingId !== null) chat.closeCasePopup();
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <div v-if="chat.casePopupTrackingId !== null" class="scrim" @click.self="chat.closeCasePopup()">
    <div class="popup" role="dialog" aria-modal="true" aria-label="Anliegen">
      <p v-if="loading" class="mono popup__status">Lade …</p>
      <p v-else-if="error" class="popup__status popup__status--error">{{ error }}</p>

      <template v-else-if="detail">
        <div class="popup__head">
          <span class="mono popup__id">{{ detail.tracking_id }}</span>
          <span class="popup__status-badge" :class="{ 'is-closed': detail.status === 'closed' }">
            {{ detail.status === "open" ? "Offen" : "Geschlossen" }}
          </span>
          <button type="button" class="popup__close" title="Schließen" @click="chat.closeCasePopup()">✕</button>
        </div>

        <h3 class="popup__title">{{ detail.title }}</h3>
        <p v-if="detail.summary" class="popup__summary">{{ detail.summary }}</p>

        <dl class="facts">
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

        <div v-if="detail.links.length" class="popup__links">
          <span class="mono popup__links-label">Abhängigkeiten</span>
          <ul>
            <li v-for="link in detail.links" :key="`${link.dependent_tracking_id}-${link.prerequisite_tracking_id}`">
              <span class="mono">{{ link.dependent_tracking_id }}</span>
              baut auf
              <span class="mono">{{ link.prerequisite_tracking_id }}</span>
              auf
              <span v-if="link.status === 'proposed'" class="badge mono">Vorschlag</span>
            </li>
          </ul>
        </div>

        <div class="popup__actions">
          <RouterLink
            :to="`/anliegen/${detail.tracking_id}`"
            class="button--primary"
            @click="chat.closeCasePopup()"
          >
            Vollständige Ansicht öffnen
          </RouterLink>
          <button type="button" class="link-action" @click="chat.closeCasePopup()">Schließen</button>
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

.popup {
  display: flex;
  flex-direction: column;
  width: min(460px, 100%);
  max-height: min(640px, 100%);
  overflow-y: auto;
  padding: 1.25rem 1.5rem;
  background: var(--color-white);
  border: 1px solid var(--color-line-strong);
}

.popup__status {
  margin: 0;
  color: var(--color-ink-4);
}

.popup__status--error {
  color: var(--color-error);
}

.popup__head {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  margin-bottom: 0.75rem;
}

.popup__id {
  color: var(--color-ink-4);
}

.popup__status-badge {
  padding: 0.05rem 0.4rem;
  border: 1px solid var(--color-accent);
  color: var(--color-accent);
  font-size: var(--font-size-2xs);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.popup__status-badge.is-closed {
  border-color: var(--color-line-strong);
  color: var(--color-ink-4);
}

.popup__close {
  margin-left: auto;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-ink-4);
  cursor: pointer;
  font-size: var(--font-size-md);
}

.popup__close:hover {
  color: var(--color-error);
}

.popup__title {
  margin: 0 0 0.5rem;
  font-size: var(--font-size-lg);
  font-weight: 500;
}

.popup__summary {
  margin: 0 0 1rem;
  color: var(--color-ink-3);
}

.facts {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 0.5rem 0.625rem;
  margin: 0 0 1rem;
  font-size: var(--font-size-md);
}

.facts dt {
  font-size: var(--font-size-2xs);
  letter-spacing: 0.04em;
  color: var(--color-ink-5);
}

.facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.popup__links {
  margin-bottom: 1.125rem;
}

.popup__links-label {
  display: block;
  margin-bottom: 0.375rem;
  font-size: var(--font-size-2xs);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-ink-5);
}

.popup__links ul {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: var(--font-size-sm);
}

.badge {
  padding: 0.05rem 0.3rem;
  border: 1px solid var(--color-line-strong);
  color: var(--color-ink-4);
  font-size: var(--font-size-2xs);
}

.popup__actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: auto;
  padding-top: 0.5rem;
}
</style>
