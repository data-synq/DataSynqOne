<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, ApiError, type AppUser } from "../api/client";
import { useAuthStore } from "../stores/auth";
import { formatDate } from "../utils/dates";

const auth = useAuthStore();

const users = ref<AppUser[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

const ROLES = [
  { value: "admin", label: "Administrator", hint: "Alles, inklusive Benutzerverwaltung und Sync" },
  { value: "editor", label: "Bearbeiter", hint: "Lesen und Änderungen über den Assistenten" },
  { value: "viewer", label: "Betrachter", hint: "Nur lesen, der Assistent ändert nichts" },
];

const draft = ref({ email: "", display_name: "", role: "editor", password: "" });
const creating = ref(false);

async function load() {
  loading.value = true;
  try {
    users.value = await api.listUsers();
    error.value = null;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Benutzerliste konnte nicht geladen werden.";
  } finally {
    loading.value = false;
  }
}

/** Jede Änderung meldet ihr Ergebnis an derselben Stelle. */
async function run(action: () => Promise<unknown>, success: string) {
  error.value = null;
  notice.value = null;
  try {
    await action();
    notice.value = success;
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Änderung ist fehlgeschlagen.";
  }
}

async function create() {
  creating.value = true;
  await run(
    () => api.createUser({ ...draft.value }),
    `${draft.value.display_name} wurde angelegt. Das Startpasswort ist beim ersten Login zu ändern.`,
  );
  creating.value = false;
  if (!error.value) draft.value = { email: "", display_name: "", role: "editor", password: "" };
}

function changeRole(user: AppUser, role: string) {
  if (role === user.role) return;
  run(
    () => api.updateUser(user.id, { role }),
    `${user.display_name} ist jetzt ${ROLES.find((r) => r.value === role)?.label}. Laufende Sitzungen wurden beendet.`,
  );
}

function toggleActive(user: AppUser) {
  run(
    () => api.updateUser(user.id, { is_active: !user.is_active }),
    user.is_active
      ? `${user.display_name} wurde deaktiviert und abgemeldet.`
      : `${user.display_name} kann sich wieder anmelden.`,
  );
}

function resetPassword(user: AppUser) {
  const password = window.prompt(
    `Neues Startpasswort für ${user.display_name} (mindestens 12 Zeichen).\n` +
      `Es muss beim nächsten Login geändert werden.`,
  );
  if (!password) return;
  run(
    () => api.resetUserPassword(user.id, password),
    `Passwort für ${user.display_name} gesetzt. Alle Sitzungen wurden beendet.`,
  );
}

function remove(user: AppUser) {
  if (
    !window.confirm(
      `${user.display_name} (${user.email}) endgültig löschen?\n\n` +
        `Die Chat-Sitzungen dieser Person werden mitgelöscht und lassen sich nicht wiederherstellen.`,
    )
  )
    return;
  run(() => api.deleteUser(user.id), `${user.display_name} wurde gelöscht.`);
}

onMounted(load);
</script>

<template>
  <div class="container users">
    <div class="section-head">
      <h2>Benutzer</h2>
      <RouterLink to="/" class="link-action">Zurück zum Dashboard</RouterLink>
    </div>

    <p v-if="notice" class="notice notice--ok" role="status">{{ notice }}</p>
    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>

    <p v-if="loading" class="mono users__state">Wird geladen …</p>

    <table v-else class="table">
      <thead>
        <tr>
          <th>Name</th>
          <th>E-Mail</th>
          <th>Rolle</th>
          <th>Status</th>
          <th>Letzter Login</th>
          <th><span class="visually-hidden">Aktionen</span></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="user in users" :key="user.id" :class="{ 'is-inactive': !user.is_active }">
          <td>
            {{ user.display_name }}
            <span v-if="user.id === auth.user?.id" class="badge mono">du</span>
          </td>
          <td class="mono">{{ user.email }}</td>
          <td>
            <label class="visually-hidden" :for="`role-${user.id}`">Rolle</label>
            <select
              :id="`role-${user.id}`"
              :value="user.role"
              @change="changeRole(user, ($event.target as HTMLSelectElement).value)"
            >
              <option v-for="role in ROLES" :key="role.value" :value="role.value">
                {{ role.label }}
              </option>
            </select>
          </td>
          <td>
            <span class="mono">{{ user.is_active ? "aktiv" : "deaktiviert" }}</span>
            <span v-if="user.must_change_password" class="badge mono">Passwort offen</span>
          </td>
          <td class="mono">{{ user.last_login_at ? formatDate(user.last_login_at) : "—" }}</td>
          <td class="actions">
            <button type="button" class="link-action" @click="resetPassword(user)">
              Passwort
            </button>
            <button
              type="button"
              class="link-action"
              :disabled="user.id === auth.user?.id"
              @click="toggleActive(user)"
            >
              {{ user.is_active ? "Deaktivieren" : "Aktivieren" }}
            </button>
            <button
              type="button"
              class="link-action link-action--danger"
              :disabled="user.id === auth.user?.id"
              @click="remove(user)"
            >
              Löschen
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <div class="section-head section-head--sub">
      <h2>Benutzer anlegen</h2>
    </div>

    <form class="create" @submit.prevent="create">
      <div class="field">
        <label class="field__label" for="new-name">Name</label>
        <input id="new-name" v-model="draft.display_name" type="text" required />
      </div>
      <div class="field">
        <label class="field__label" for="new-email">E-Mail</label>
        <input id="new-email" v-model="draft.email" type="email" required />
      </div>
      <div class="field">
        <label class="field__label" for="new-role">Rolle</label>
        <select id="new-role" v-model="draft.role">
          <option v-for="role in ROLES" :key="role.value" :value="role.value">
            {{ role.label }}
          </option>
        </select>
        <p class="field__hint mono">{{ ROLES.find((r) => r.value === draft.role)?.hint }}</p>
      </div>
      <div class="field">
        <label class="field__label" for="new-password">Startpasswort</label>
        <input
          id="new-password"
          v-model="draft.password"
          type="text"
          minlength="12"
          required
          autocomplete="off"
        />
        <p class="field__hint mono">
          Mindestens 12 Zeichen. Wird beim ersten Login geändert.
        </p>
      </div>
      <button type="submit" class="button--primary" :disabled="creating">
        {{ creating ? "Wird angelegt …" : "Anlegen" }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.users {
  padding-block: var(--space-4) var(--space-5);
}

.section-head--sub {
  margin-top: var(--space-5);
}

.users__state {
  padding-block: var(--space-3);
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

/* Deaktivierte Konten bleiben lesbar, treten aber zurück — sie sind Bestand,
   keine offene Aufgabe. */
.is-inactive td {
  color: var(--color-ink-5);
}

.table select {
  width: auto;
  min-width: 9rem;
  font-size: var(--font-size-md);
}

.badge {
  margin-left: 0.5rem;
  padding: 0.05rem 0.3rem;
  border: 1px solid var(--color-line-strong);
  color: var(--color-ink-4);
}

.actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}

.link-action:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.link-action--danger:hover:not(:disabled) {
  color: var(--color-error);
}

.create {
  max-width: var(--content-narrow);
  margin-top: var(--space-3);
}

.field {
  margin-bottom: var(--space-3);
}

.field__label {
  display: block;
  margin-bottom: 0.35rem;
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-ink-4);
}

.field__hint {
  margin: 0.35rem 0 0;
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
