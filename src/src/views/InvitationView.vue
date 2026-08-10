<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, ApiError, type InvitationInfo } from "../api/client";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const token = String(route.params.token ?? "");
const info = ref<InvitationInfo | null>(null);
const loading = ref(true);
const linkError = ref<string | null>(null);

const password = ref("");
const repeat = ref("");
const error = ref<string | null>(null);
const busy = ref(false);

onMounted(async () => {
  try {
    info.value = await api.invitationInfo(token);
  } catch (e) {
    linkError.value =
      e instanceof ApiError ? e.message : "Der Server ist nicht erreichbar.";
  } finally {
    loading.value = false;
  }
});

async function submit() {
  error.value = null;
  if (password.value !== repeat.value) {
    error.value = "Die beiden Passwörter stimmen nicht überein.";
    return;
  }
  busy.value = true;
  try {
    // Der Endpunkt meldet direkt an und setzt das Cookie — von hier geht es ohne
    // zweiten Anmeldeschritt weiter.
    auth.user = await api.redeemInvitation(token, password.value);
    auth.resolved = true;
    await router.replace("/");
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Der Server ist nicht erreichbar.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="invite">
    <div class="invite__panel">
      <p class="eyebrow">DataSynq One</p>

      <p v-if="loading" class="mono invite__state">Link wird geprüft …</p>

      <template v-else-if="linkError">
        <h1 class="invite__title">Link ungültig</h1>
        <p class="invite__lead">{{ linkError }}</p>
        <RouterLink to="/login" class="button--secondary invite__submit">Zur Anmeldung</RouterLink>
      </template>

      <form v-else @submit.prevent="submit">
        <h1 class="invite__title">
          {{ info?.purpose === "password_reset" ? "Neues Passwort" : "Willkommen" }}
        </h1>
        <p class="invite__lead">
          {{ info?.display_name }}, vergib hier dein Passwort. Danach bist du angemeldet.
        </p>

        <div class="field">
          <label class="field__label" for="invite-password">Passwort</label>
          <input
            id="invite-password"
            v-model="password"
            type="password"
            autocomplete="new-password"
            minlength="12"
            required
            autofocus
          />
          <p class="field__hint mono">Mindestens 12 Zeichen.</p>
        </div>

        <div class="field">
          <label class="field__label" for="invite-repeat">Passwort wiederholen</label>
          <input
            id="invite-repeat"
            v-model="repeat"
            type="password"
            autocomplete="new-password"
            minlength="12"
            required
          />
        </div>

        <p v-if="error" class="invite__error" role="alert">{{ error }}</p>

        <button type="submit" class="button--primary invite__submit" :disabled="busy">
          {{ busy ? "Wird gespeichert …" : "Passwort setzen und anmelden" }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.invite {
  display: grid;
  place-items: center;
  min-height: 100dvh;
  padding: var(--page-padding);
  background: var(--color-canvas);
}

.invite__panel {
  width: min(100%, 26rem);
  padding: var(--space-4);
  border: 1px solid var(--color-line-strong);
  background: var(--color-white);
}

.invite__title {
  margin-block: 0.35rem var(--space-2);
  font-size: var(--font-size-2xl);
  font-weight: 600;
  letter-spacing: -0.02em;
}

.invite__lead {
  margin-bottom: var(--space-3);
  color: var(--color-text-muted);
  font-size: var(--font-size-md);
  line-height: var(--line-height-body);
}

.invite__state {
  padding-block: var(--space-2);
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

.invite__error {
  margin-bottom: var(--space-2);
  padding: 0.5rem 0.625rem;
  border-left: 2px solid var(--color-error);
  background: var(--color-surface-muted);
  color: var(--color-error);
  font-size: var(--font-size-md);
}

.invite__submit {
  width: 100%;
  min-height: 34px;
}
</style>
