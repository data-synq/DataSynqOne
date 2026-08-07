<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { ApiError } from "../api/client";

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
</style>
