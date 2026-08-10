<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  api,
  ApiError,
  type AppUser,
  type InvitationResult,
  type MailSettings,
  type ObjectAccessInput,
  type ObjectOption,
} from "../api/client";
import { useAuthStore } from "../stores/auth";
import { formatDate } from "../utils/dates";

const auth = useAuthStore();

const users = ref<AppUser[]>([]);
const objectOptions = ref<ObjectOption[]>([]);
const scopeDrafts = ref<Record<string, ObjectAccessInput>>({});
const loading = ref(true);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

const ROLES = [
  { value: "admin", label: "Administrator", hint: "Alles, inklusive Benutzerverwaltung und Sync" },
  { value: "editor", label: "Bearbeiter", hint: "Lesen und Änderungen über den Assistenten" },
  { value: "viewer", label: "Betrachter", hint: "Nur lesen, der Assistent ändert nichts" },
];

const draft = ref<{
  email: string;
  display_name: string;
  role: string;
  object_access_mode: "" | "all" | "restricted";
  object_codes: string[];
}>({ email: "", display_name: "", role: "editor", object_access_mode: "", object_codes: [] });
const creating = ref(false);

/** Nur gesetzt, wenn kein Mailversand eingerichtet ist — dann ist er der einzige Weg. */
const manualLink = ref<string | null>(null);
const mail = ref<MailSettings | null>(null);
const testing = ref(false);

async function load() {
  loading.value = true;
  try {
    users.value = await api.listUsers();
    scopeDrafts.value = Object.fromEntries(
      users.value.map((user) => [
        user.id,
        { mode: user.object_access_mode, object_codes: [...user.object_codes] },
      ]),
    );
    error.value = null;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Benutzerliste konnte nicht geladen werden.";
  } finally {
    loading.value = false;
  }
}

/** Jede Änderung meldet ihr Ergebnis an derselben Stelle.
 *  Die Aktion liefert die Meldung selbst, weil manche sie erst aus der Antwort kennen. */
async function run(action: () => Promise<string>) {
  error.value = null;
  notice.value = null;
  manualLink.value = null;
  try {
    notice.value = await action();
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Änderung ist fehlgeschlagen.";
  }
}

/** Meldung zu einer Einladung. Der Link wird nur gezeigt, wenn keine Mail rausging. */
function reportInvitation(result: InvitationResult, name: string) {
  manualLink.value = result.invitation_link;
  return result.mail_sent
    ? `Einladung an ${result.user.email} verschickt.`
    : `${name}: Es ist kein Mailversand eingerichtet — gib diesen Link persönlich weiter.`;
}

async function create() {
  if (!draft.value.object_access_mode) {
    error.value = "Wähle den Objektzugriff ausdrücklich aus.";
    return;
  }
  if (draft.value.object_access_mode === "restricted" && !draft.value.object_codes.length) {
    error.value = "Wähle mindestens ein Objekt aus.";
    return;
  }
  creating.value = true;
  const name = draft.value.display_name;
  await run(async () =>
    reportInvitation(
      await api.createUser({
        email: draft.value.email,
        display_name: draft.value.display_name,
        role: draft.value.role,
        object_access: {
          mode: draft.value.object_access_mode as "all" | "restricted",
          object_codes:
            draft.value.object_access_mode === "all" ? [] : draft.value.object_codes,
        },
      }),
      name,
    ),
  );
  creating.value = false;
  if (!error.value) {
    draft.value = {
      email: "",
      display_name: "",
      role: "editor",
      object_access_mode: "",
      object_codes: [],
    };
  }
}

function saveScope(user: AppUser) {
  const access = scopeDrafts.value[user.id];
  if (!access || (access.mode === "restricted" && !access.object_codes.length)) {
    error.value = "Eingeschränkter Zugriff benötigt mindestens ein Objekt.";
    return;
  }
  if (
    access.mode === "all" &&
    user.object_access_mode !== "all" &&
    !window.confirm(`Den Zugriff für ${user.display_name} wirklich auf alle Objekte erweitern?`)
  ) {
    return;
  }
  run(async () => {
    await api.updateObjectScope(user.id, {
      mode: access.mode,
      object_codes: access.mode === "all" ? [] : access.object_codes,
    });
    return `${user.display_name}: Objektzugriff gespeichert. Sitzungen und alte Chats wurden beendet.`;
  });
}

function resendInvitation(user: AppUser) {
  run(async () =>
    reportInvitation(await api.resendInvitation(user.id), user.display_name),
  );
}

async function copyLink() {
  if (!manualLink.value) return;
  try {
    await navigator.clipboard.writeText(manualLink.value);
    notice.value = "Link kopiert.";
  } catch {
    // clipboard braucht einen sicheren Kontext; über http bleibt der Link
    // markierbar im Feld stehen.
    error.value = "Kopieren nicht möglich — bitte den Link von Hand markieren.";
  }
}

async function sendTestMail() {
  testing.value = true;
  await run(async () => {
    const result = await api.sendTestMail();
    return `${result.detail} (${result.recipient})`;
  });
  testing.value = false;
}

function changeRole(user: AppUser, role: string) {
  if (role === user.role) return;
  run(async () => {
    await api.updateUser(user.id, { role });
    const label = ROLES.find((r) => r.value === role)?.label;
    return `${user.display_name} ist jetzt ${label}. Laufende Sitzungen wurden beendet.`;
  });
}

function toggleActive(user: AppUser) {
  run(async () => {
    await api.updateUser(user.id, { is_active: !user.is_active });
    return user.is_active
      ? `${user.display_name} wurde deaktiviert und abgemeldet.`
      : `${user.display_name} kann sich wieder anmelden.`;
  });
}

function remove(user: AppUser) {
  if (
    !window.confirm(
      `${user.display_name} (${user.email}) endgültig löschen?\n\n` +
        `Die Chat-Sitzungen dieser Person werden mitgelöscht und lassen sich nicht wiederherstellen.`,
    )
  )
    return;
  run(async () => {
    await api.deleteUser(user.id);
    return `${user.display_name} wurde gelöscht.`;
  });
}

onMounted(async () => {
  try {
    objectOptions.value = await api.listObjectOptions();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Objektliste konnte nicht geladen werden.";
  }
  await load();
  // Nur zur Anzeige: ohne sie erklärt sich ein ausbleibender Einladungslink nicht.
  try {
    mail.value = await api.mailSettings();
  } catch {
    /* der Zustand der Liste hängt nicht daran */
  }
});
</script>

<template>
  <div class="container users">
    <div class="section-head">
      <h2>Benutzer</h2>
      <div class="head-actions">
        <button type="button" class="link-action" :disabled="testing" @click="sendTestMail">
          {{ testing ? "Testmail läuft …" : "Testmail an mich" }}
        </button>
        <RouterLink to="/" class="link-action">Zurück zum Dashboard</RouterLink>
      </div>
    </div>

    <p v-if="notice" class="notice notice--ok" role="status">{{ notice }}</p>
    <p v-if="manualLink" class="notice notice--link">
      <code class="manual-link">{{ manualLink }}</code>
      <button type="button" class="link-action" @click="copyLink">Kopieren</button>
    </p>
    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>

    <p v-if="mail && !mail.enabled" class="notice notice--warn">
      Es ist kein Mailversand eingerichtet (<code>SMTP_HOST</code>,
      <code>SMTP_FROM_EMAIL</code>). Einladungen werden nicht verschickt — der Link
      erscheint stattdessen hier zum Weitergeben.
    </p>

    <p v-if="loading" class="mono users__state">Wird geladen …</p>

    <table v-else class="table">
      <thead>
        <tr>
          <th>Name</th>
          <th>E-Mail</th>
          <th>Rolle</th>
          <th>Objektzugriff</th>
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
            <details class="scope-editor">
              <summary class="link-action">
                {{ user.object_access_mode === "all" ? "Alle Objekte" : `${user.object_codes.length} Objekte` }}
              </summary>
              <fieldset v-if="scopeDrafts[user.id]" :disabled="user.id === auth.user?.id">
                <legend class="visually-hidden">Objektzugriff für {{ user.display_name }}</legend>
                <label>
                  <input v-model="scopeDrafts[user.id].mode" type="radio" value="all" />
                  Alle Objekte
                </label>
                <label>
                  <input v-model="scopeDrafts[user.id].mode" type="radio" value="restricted" />
                  Nur ausgewählte
                </label>
                <div v-if="scopeDrafts[user.id].mode === 'restricted'" class="scope-options">
                  <label v-for="object in objectOptions" :key="object.code">
                    <input
                      v-model="scopeDrafts[user.id].object_codes"
                      type="checkbox"
                      :value="object.code"
                    />
                    <span><code>{{ object.code }}</code> {{ object.label }}</span>
                  </label>
                </div>
                <button type="button" class="button--secondary" @click="saveScope(user)">
                  Speichern
                </button>
              </fieldset>
            </details>
          </td>
          <td>
            <span class="mono">{{ user.is_active ? "aktiv" : "deaktiviert" }}</span>
            <span v-if="!user.last_login_at" class="badge mono">eingeladen</span>
          </td>
          <td class="mono">{{ user.last_login_at ? formatDate(user.last_login_at) : "—" }}</td>
          <td class="actions">
            <button type="button" class="link-action" @click="resendInvitation(user)">
              {{ user.last_login_at ? "Passwort zurücksetzen" : "Einladung erneut" }}
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
      <fieldset class="field scope-create">
        <legend class="field__label">Objektzugriff</legend>
        <label>
          <input v-model="draft.object_access_mode" type="radio" value="all" required />
          Alle Objekte
        </label>
        <label>
          <input v-model="draft.object_access_mode" type="radio" value="restricted" required />
          Nur ausgewählte Objekte
        </label>
        <div v-if="draft.object_access_mode === 'restricted'" class="scope-options">
          <label v-for="object in objectOptions" :key="object.code">
            <input v-model="draft.object_codes" type="checkbox" :value="object.code" />
            <span><code>{{ object.code }}</code> {{ object.label }}</span>
          </label>
        </div>
      </fieldset>
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
      <p class="field__hint mono create__hint">
        Kein Startpasswort: die Person bekommt einen Einladungslink und vergibt es selbst.
      </p>
      <button type="submit" class="button--primary" :disabled="creating">
        {{ creating ? "Wird angelegt …" : "Anlegen und einladen" }}
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

.scope-editor {
  position: relative;
}

.scope-editor fieldset {
  position: absolute;
  z-index: 5;
  display: grid;
  gap: 0.5rem;
  width: min(24rem, 80vw);
  margin-top: 0.4rem;
  padding: var(--space-2);
  border: 1px solid var(--color-line-strong);
  background: var(--color-white);
}

.scope-options {
  display: grid;
  gap: 0.35rem;
  max-height: 14rem;
  padding: var(--space-2);
  overflow-y: auto;
  border: 1px solid var(--color-line-soft);
  background: var(--color-surface-muted);
}

.scope-options label,
.scope-create > label {
  display: flex;
  align-items: start;
  gap: 0.5rem;
}

.scope-create {
  display: grid;
  gap: 0.5rem;
  padding: 0;
  border: 0;
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

.notice--warn {
  border-left-color: var(--color-warning);
}

.notice--link {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
  border-left-color: var(--color-line-strong);
}

/* Der Link muss vollständig lesbar sein — er wird von Hand weitergegeben. */
.manual-link {
  min-width: 0;
  overflow-wrap: anywhere;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.head-actions {
  display: flex;
  gap: var(--space-2);
}

.create__hint {
  margin-bottom: var(--space-3);
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
