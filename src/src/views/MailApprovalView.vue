<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, ApiError, type PendingSender } from "../api/client";
import { formatDate } from "../utils/dates";

const senders = ref<PendingSender[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const tab = ref<"pending" | "approved" | "rejected">("pending");

const visible = computed(() => senders.value.filter((s) => s.status === tab.value));
const pendingCount = computed(() => senders.value.filter((s) => s.status === "pending").length);

async function load() {
  loading.value = true;
  try {
    senders.value = await api.listPendingSenders();
    error.value = null;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Absenderliste konnte nicht geladen werden.";
  } finally {
    loading.value = false;
  }
}

async function run(action: () => Promise<string>) {
  error.value = null;
  notice.value = null;
  try {
    notice.value = await action();
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Änderung ist fehlgeschlagen.";
  }
}

function approve(sender: PendingSender) {
  run(async () => {
    await api.approveSender(sender.email);
    return `${sender.email} ist jetzt freigegeben.`;
  });
}

function reject(sender: PendingSender) {
  if (!window.confirm(`${sender.email} ablehnen? E-Mails von dieser Adresse werden dann nicht verarbeitet.`))
    return;
  run(async () => {
    await api.rejectSender(sender.email);
    return `${sender.email} wurde abgelehnt.`;
  });
}

function expiresLabel(sender: PendingSender): string {
  if (!sender.expires_at) return "—";
  const days = Math.ceil((new Date(sender.expires_at).getTime() - Date.now()) / 86_400_000);
  if (days < 0) return "abgelaufen";
  if (days === 0) return "läuft heute ab";
  return `noch ${days} Tag${days === 1 ? "" : "e"}`;
}

onMounted(load);
</script>

<template>
  <div class="container senders">
    <div class="section-head">
      <h2>Absender-Freigaben</h2>
      <div class="head-actions">
        <RouterLink to="/" class="link-action">Zurück zum Dashboard</RouterLink>
      </div>
    </div>

    <p class="mono senders__hint">
      Eingehende E-Mails werden erst weiterverarbeitet, wenn der Absender freigegeben ist. Eine
      Freigabe gilt befristet — danach muss sie erneuert werden.
    </p>

    <p v-if="notice" class="notice notice--ok" role="status">{{ notice }}</p>
    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>

    <div class="tabs">
      <button
        type="button"
        class="tabs__item"
        :class="{ 'is-active': tab === 'pending' }"
        @click="tab = 'pending'"
      >
        Wartend<span v-if="pendingCount" class="badge mono">{{ pendingCount }}</span>
      </button>
      <button
        type="button"
        class="tabs__item"
        :class="{ 'is-active': tab === 'approved' }"
        @click="tab = 'approved'"
      >
        Freigegeben
      </button>
      <button
        type="button"
        class="tabs__item"
        :class="{ 'is-active': tab === 'rejected' }"
        @click="tab = 'rejected'"
      >
        Abgelehnt
      </button>
    </div>

    <p v-if="loading" class="mono senders__state">Wird geladen …</p>

    <table v-else class="table">
      <thead>
        <tr>
          <th>E-Mail</th>
          <th>Zuerst gesehen</th>
          <th>Zuletzt gesehen</th>
          <th v-if="tab === 'approved'">Gültig</th>
          <th><span class="visually-hidden">Aktionen</span></th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!visible.length">
          <td colspan="5" class="mono senders__empty">Keine Einträge.</td>
        </tr>
        <tr v-for="sender in visible" :key="sender.email">
          <td class="mono">{{ sender.email }}</td>
          <td class="mono">{{ formatDate(sender.first_seen_at) }}</td>
          <td class="mono">{{ formatDate(sender.last_seen_at) }}</td>
          <td v-if="tab === 'approved'" class="mono">{{ expiresLabel(sender) }}</td>
          <td class="actions">
            <button
              v-if="sender.status !== 'approved'"
              type="button"
              class="link-action"
              @click="approve(sender)"
            >
              Freigeben
            </button>
            <button
              v-if="sender.status !== 'rejected'"
              type="button"
              class="link-action link-action--danger"
              @click="reject(sender)"
            >
              Ablehnen
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.senders {
  padding-block: var(--space-4) var(--space-5);
}

.senders__hint {
  max-width: var(--content-narrow);
  margin-bottom: var(--space-3);
  color: var(--color-ink-4);
}

.senders__state,
.senders__empty {
  padding-block: var(--space-3);
  color: var(--color-ink-4);
}

.head-actions {
  display: flex;
  gap: var(--space-2);
}

.tabs {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  border-bottom: 1px solid var(--color-line);
}

.tabs__item {
  padding: 0.5rem 0.125rem;
  border-bottom: 2px solid transparent;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  letter-spacing: 0.04em;
  color: var(--color-ink-4);
}

.tabs__item.is-active {
  border-bottom-color: var(--color-accent);
  color: var(--color-text);
}

.badge {
  margin-left: 0.4rem;
  padding: 0.05rem 0.3rem;
  border: 1px solid var(--color-line-strong);
  color: var(--color-ink-4);
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-md);
}

.table th {
  padding: 0.5rem 0.75rem 0.5rem 0;
  border-bottom: 1px solid var(--color-line-strong);
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  font-weight: 400;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-align: left;
  color: var(--color-ink-4);
}

.table td {
  padding: 0.5rem 0.75rem 0.5rem 0;
  border-bottom: 1px solid var(--color-line-soft);
  vertical-align: baseline;
}

.actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}

.link-action--danger:hover:not(:disabled) {
  color: var(--color-error);
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

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
