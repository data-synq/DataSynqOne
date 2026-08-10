<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, ApiError, type MfaSetup } from "../api/client";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const setup = ref<MfaSetup | null>(null);
const code = ref("");
const recoveryCodes = ref<string[]>([]);
const busy = ref(false);
const error = ref<string | null>(null);
const isSetup = computed(() => auth.authStage === "mfa_setup");

onMounted(async () => {
  if (!isSetup.value) return;
  try {
    setup.value = await api.setupMfa();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "MFA konnte nicht vorbereitet werden.";
  }
});

async function submit() {
  busy.value = true;
  error.value = null;
  try {
    if (isSetup.value) {
      recoveryCodes.value = await auth.confirmMfa(code.value);
    } else {
      await auth.verifyMfa(code.value);
      await continueToApp();
    }
    code.value = "";
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Der MFA-Code konnte nicht geprüft werden.";
    code.value = "";
  } finally {
    busy.value = false;
  }
}

async function continueToApp() {
  const target = route.query.weiter;
  const next = typeof target === "string" && target.startsWith("/") ? target : "/";
  await router.replace(next);
}
</script>

<template>
  <div class="mfa-page">
    <section class="mfa-card">
      <p class="eyebrow">DataSynq One · Kontoschutz</p>

      <template v-if="recoveryCodes.length">
        <h1>Recovery-Codes sichern</h1>
        <p>
          Jeder Code funktioniert genau einmal. Speichere sie jetzt außerhalb dieses Geräts; sie
          können später nicht erneut angezeigt werden.
        </p>
        <ol class="recovery-codes" aria-label="Recovery-Codes">
          <li v-for="recoveryCode in recoveryCodes" :key="recoveryCode" class="mono">
            {{ recoveryCode }}
          </li>
        </ol>
        <button type="button" class="button--primary" @click="continueToApp">
          Ich habe die Codes gesichert
        </button>
      </template>

      <template v-else>
        <h1>{{ isSetup ? "Zweiten Faktor einrichten" : "Zweiten Faktor bestätigen" }}</h1>
        <p v-if="isSetup">
          Füge den folgenden Schlüssel in einer TOTP-App hinzu. Danach bestätigst du die
          Einrichtung mit dem aktuellen sechsstelligen Code.
        </p>
        <p v-else>
          Gib den aktuellen Code deiner TOTP-App oder einen noch unbenutzten Recovery-Code ein.
        </p>

        <div v-if="isSetup && setup" class="setup-secret">
          <span class="field__label">Manueller Schlüssel</span>
          <code>{{ setup.secret }}</code>
        </div>

        <form class="form" @submit.prevent="submit">
          <div class="field">
            <label class="field__label" for="mfa-code">MFA- oder Recovery-Code</label>
            <input
              id="mfa-code"
              v-model="code"
              type="text"
              :inputmode="isSetup ? 'numeric' : 'text'"
              autocomplete="one-time-code"
              minlength="6"
              maxlength="100"
              required
              autofocus
            />
          </div>
          <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>
          <button type="submit" class="button--primary" :disabled="busy || (isSetup && !setup)">
            {{ busy ? "Wird geprüft …" : "Code prüfen" }}
          </button>
        </form>
      </template>
    </section>
  </div>
</template>

<style scoped>
.mfa-page {
  display: grid;
  place-items: center;
  min-height: 100dvh;
  padding: var(--page-padding);
  background: var(--color-canvas);
}

.mfa-card {
  width: min(100%, 34rem);
  padding: var(--space-4);
  border: 1px solid var(--color-line-strong);
  background: var(--color-white);
}

.mfa-card h1 {
  margin-block: 0.35rem var(--space-2);
  font-size: var(--font-size-2xl);
}

.setup-secret {
  margin-block: var(--space-3);
  padding: var(--space-2);
  border-left: 2px solid var(--color-accent);
  background: var(--color-surface-muted);
}

.setup-secret code {
  display: block;
  margin-top: 0.4rem;
  overflow-wrap: anywhere;
}

.form,
.field {
  margin-top: var(--space-3);
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

.notice {
  margin-bottom: var(--space-2);
  padding: 0.625rem 0.75rem;
  border-left: 2px solid var(--color-error);
  background: var(--color-surface-muted);
  color: var(--color-error);
}

.recovery-codes {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem var(--space-3);
  margin-block: var(--space-3);
  padding: var(--space-3);
  background: var(--color-surface-muted);
}

@media (max-width: 34rem) {
  .recovery-codes {
    grid-template-columns: 1fr;
  }
}
</style>
