<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { ApiError } from "../api/client";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const email = ref("");
const password = ref("");
const error = ref<string | null>(null);
const busy = ref(false);

async function submit() {
  busy.value = true;
  error.value = null;
  try {
    await auth.login(email.value, password.value);
    // `weiter` trägt das ursprünglich angesteuerte Ziel — nur interne Pfade, damit
    // ein manipulierter Link niemanden nach dem Login auf eine fremde Seite schickt.
    const target = route.query.weiter;
    const next = typeof target === "string" && target.startsWith("/") ? target : "/";
    await router.replace(next);
  } catch (e) {
    error.value =
      e instanceof ApiError
        ? e.message
        : "Der Server ist nicht erreichbar. Bitte später erneut versuchen.";
    password.value = "";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="login">
    <form class="login__panel" @submit.prevent="submit">
      <p class="eyebrow">DataSynq One</p>
      <h1 class="login__title">Anmeldung</h1>
      <p class="login__lead">
        Die Dokumentenakte ist Personen zugeordnet. Melde dich mit deinem Konto an.
      </p>

      <div class="field">
        <label class="field__label" for="login-email">E-Mail-Adresse</label>
        <input
          id="login-email"
          v-model="email"
          type="email"
          autocomplete="username"
          required
          autofocus
        />
      </div>

      <div class="field">
        <label class="field__label" for="login-password">Passwort</label>
        <input
          id="login-password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
        />
      </div>

      <p v-if="error" class="login__error" role="alert">{{ error }}</p>

      <button type="submit" class="button--primary login__submit" :disabled="busy">
        {{ busy ? "Wird geprüft …" : "Anmelden" }}
      </button>

      <p class="login__note mono">
        Kein Konto? Konten legt ein Administrator an.
      </p>
    </form>
  </div>
</template>

<style scoped>
.login {
  display: grid;
  place-items: center;
  min-height: 100dvh;
  padding: var(--page-padding);
  background: var(--color-canvas);
}

/* Ein Blatt auf der Fläche: eine Linie ringsum, kein Schatten, kein Radius —
   dieselbe Logik wie die Panels des Dashboards. */
.login__panel {
  width: min(100%, 26rem);
  padding: var(--space-4);
  border: 1px solid var(--color-line-strong);
  background: var(--color-white);
}

.login__title {
  margin-block: 0.35rem var(--space-2);
  font-size: var(--font-size-2xl);
  font-weight: 600;
  letter-spacing: -0.02em;
}

.login__lead {
  margin-bottom: var(--space-3);
  color: var(--color-text-muted);
  font-size: var(--font-size-md);
  line-height: var(--line-height-body);
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

.login__error {
  margin-bottom: var(--space-2);
  padding: 0.5rem 0.625rem;
  border-left: 2px solid var(--color-error);
  background: var(--color-surface-muted);
  color: var(--color-error);
  font-size: var(--font-size-md);
}

.login__submit {
  width: 100%;
  min-height: 34px;
}

.login__note {
  margin-top: var(--space-2);
  margin-bottom: 0;
}
</style>
