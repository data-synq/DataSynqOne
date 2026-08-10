<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { api, ApiError, type AuthSession } from "../api/client";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

/** Erstanmeldung: das Startpasswort kennt auch der Administrator, der es vergab. */
const forced = computed(() => auth.mustChangePassword);

const currentPassword = ref("");
const newPassword = ref("");
const repeatPassword = ref("");
const error = ref<string | null>(null);
const done = ref(false);
const busy = ref(false);
const authSessions = ref<AuthSession[]>([]);
const sessionsBusy = ref(false);
const sessionsError = ref<string | null>(null);

function formatDate(value: string) {
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

async function loadSessions() {
  if (forced.value) return;
  sessionsError.value = null;
  try {
    authSessions.value = await api.listAuthSessions();
  } catch (e) {
    sessionsError.value = e instanceof ApiError ? e.message : "Sitzungen konnten nicht geladen werden.";
  }
}

async function revokeSession(session: AuthSession) {
  sessionsBusy.value = true;
  sessionsError.value = null;
  try {
    await api.revokeAuthSession(session.id);
    if (session.current) {
      auth.clear();
      await router.replace({ name: "login" });
      return;
    }
    await loadSessions();
  } catch (e) {
    sessionsError.value = e instanceof ApiError ? e.message : "Die Sitzung konnte nicht beendet werden.";
  } finally {
    sessionsBusy.value = false;
  }
}

async function revokeOthers() {
  sessionsBusy.value = true;
  sessionsError.value = null;
  try {
    await api.revokeOtherAuthSessions();
    await loadSessions();
  } catch (e) {
    sessionsError.value = e instanceof ApiError ? e.message : "Die Sitzungen konnten nicht beendet werden.";
  } finally {
    sessionsBusy.value = false;
  }
}

onMounted(loadSessions);

async function submit() {
  error.value = null;
  if (newPassword.value !== repeatPassword.value) {
    error.value = "Die beiden neuen Passwörter stimmen nicht überein.";
    return;
  }
  busy.value = true;
  try {
    await auth.changePassword(currentPassword.value, newPassword.value);
    currentPassword.value = "";
    newPassword.value = "";
    repeatPassword.value = "";
    done.value = true;
    if (route.query.erstanmeldung) await router.replace("/");
  } catch (e) {
    error.value =
      e instanceof ApiError ? e.message : "Der Server ist nicht erreichbar.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="container container--narrow profile">
    <div class="section-head">
      <h2>Mein Konto</h2>
      <RouterLink v-if="!forced" to="/" class="link-action">Zurück zum Dashboard</RouterLink>
    </div>

    <dl class="facts">
      <div class="facts__row">
        <dt>Name</dt>
        <dd>{{ auth.user?.display_name }}</dd>
      </div>
      <div class="facts__row">
        <dt>E-Mail</dt>
        <dd>{{ auth.user?.email }}</dd>
      </div>
      <div class="facts__row">
        <dt>Rolle</dt>
        <dd>{{ auth.user?.role_label }}</dd>
      </div>
      <div v-if="auth.user?.role === 'admin'" class="facts__row">
        <dt>Zweiter Faktor</dt>
        <dd>{{ auth.user?.mfa_enabled ? "Aktiv" : "Einrichtung ausstehend" }}</dd>
      </div>
    </dl>

    <div class="section-head section-head--sub">
      <h2>Passwort ändern</h2>
    </div>

    <p v-if="forced" class="notice" role="alert">
      Dein Passwort wurde von einem Administrator vergeben und ist damit einer zweiten
      Person bekannt. Vergib jetzt ein eigenes, um fortzufahren.
    </p>
    <p v-else-if="done" class="notice notice--ok" role="status">
      Das Passwort wurde geändert. Andere angemeldete Geräte wurden abgemeldet.
    </p>

    <form class="form" @submit.prevent="submit">
      <div class="field">
        <label class="field__label" for="pw-current">Aktuelles Passwort</label>
        <input
          id="pw-current"
          v-model="currentPassword"
          type="password"
          autocomplete="current-password"
          required
        />
      </div>
      <div class="field">
        <label class="field__label" for="pw-new">Neues Passwort</label>
        <input
          id="pw-new"
          v-model="newPassword"
          type="password"
          autocomplete="new-password"
          minlength="12"
          required
        />
        <p class="field__hint mono">Mindestens 12 Zeichen.</p>
      </div>
      <div class="field">
        <label class="field__label" for="pw-repeat">Neues Passwort wiederholen</label>
        <input
          id="pw-repeat"
          v-model="repeatPassword"
          type="password"
          autocomplete="new-password"
          minlength="12"
          required
        />
      </div>

      <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>

      <button type="submit" class="button--primary" :disabled="busy">
        {{ busy ? "Wird gespeichert …" : "Passwort ändern" }}
      </button>
    </form>

    <section v-if="!forced" class="sessions" aria-labelledby="sessions-title">
      <div class="section-head section-head--sub">
        <h2 id="sessions-title">Aktive Sitzungen</h2>
        <button
          v-if="authSessions.some((session) => !session.current)"
          type="button"
          class="button--secondary"
          :disabled="sessionsBusy"
          @click="revokeOthers"
        >
          Alle anderen abmelden
        </button>
      </div>

      <p v-if="sessionsError" class="notice notice--error" role="alert">{{ sessionsError }}</p>
      <ul v-else class="session-list">
        <li v-for="session in authSessions" :key="session.id" class="session-list__item">
          <div>
            <strong>{{ session.current ? "Dieses Gerät" : "Weitere Sitzung" }}</strong>
            <p class="session-list__agent">{{ session.user_agent || "Unbekannter Browser" }}</p>
            <p class="field__hint mono">Zuletzt aktiv: {{ formatDate(session.last_seen_at) }}</p>
            <p class="field__hint mono">
              Spätestens abgemeldet: {{ formatDate(session.absolute_expires_at) }}
            </p>
          </div>
          <button
            type="button"
            class="button--secondary"
            :disabled="sessionsBusy"
            @click="revokeSession(session)"
          >
            Abmelden
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.profile {
  padding-block: var(--space-4) var(--space-5);
}

.section-head--sub {
  margin-top: var(--space-4);
}

.facts {
  margin: 0 0 var(--space-3);
}

.facts__row {
  display: grid;
  grid-template-columns: 8rem minmax(0, 1fr);
  gap: var(--space-2);
  padding-block: 0.5rem;
  border-bottom: 1px solid var(--color-line-soft);
}

.facts__row dt {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-ink-4);
}

.facts__row dd {
  margin: 0;
  font-size: var(--font-size-base);
}

.form {
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
  border-left: 2px solid var(--color-warning);
  background: var(--color-surface-muted);
  font-size: var(--font-size-md);
  line-height: var(--line-height-body);
}

.notice--ok {
  border-left-color: var(--color-success);
}

.notice--error {
  border-left-color: var(--color-error);
  color: var(--color-error);
}

.sessions {
  margin-top: var(--space-5);
}

.session-list {
  display: grid;
  gap: var(--space-2);
  margin: var(--space-3) 0 0;
  padding: 0;
  list-style: none;
}

.session-list__item {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2);
  border: 1px solid var(--color-line-soft);
  background: var(--color-surface-muted);
}

.session-list__agent {
  margin: 0.35rem 0;
  overflow-wrap: anywhere;
}

@media (max-width: 40rem) {
  .session-list__item {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
