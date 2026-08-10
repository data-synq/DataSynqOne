<script setup lang="ts">
import { ref } from "vue";
import { api, ApiError, type EmailDraft } from "../api/client";
import { formatDate } from "../utils/dates";

const props = defineProps<{ draft: EmailDraft }>();

const recipient = ref(props.draft.recipient);
const subject = ref(props.draft.subject);
const body = ref(props.draft.body);
const sentAt = ref<string | null>(props.draft.sent_at ?? null);
const error = ref<string | null>(null);
const busy = ref(false);

async function send() {
  busy.value = true;
  error.value = null;
  try {
    const result = await api.sendDraft(props.draft.id, recipient.value, subject.value, body.value);
    sentAt.value = result.sent_at ?? new Date().toISOString();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Der Server ist nicht erreichbar.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="draft" :class="{ 'draft--sent': sentAt }">
    <p class="draft__head">
      <span class="eyebrow">{{ sentAt ? "Verschickt" : "Entwurf" }}</span>
      <span v-if="sentAt" class="mono draft__to">{{ recipient }}</span>
    </p>

    <template v-if="sentAt">
      <p class="draft__subject-sent">{{ subject }}</p>
      <p class="mono draft__meta">Am {{ formatDate(sentAt) }} verschickt.</p>
    </template>

    <template v-else>
      <label class="draft__label" :for="`recipient-${draft.id}`">Empfänger</label>
      <input
        :id="`recipient-${draft.id}`"
        v-model="recipient"
        type="email"
        autocomplete="off"
        class="draft__subject"
        required
      />

      <label class="draft__label" :for="`subject-${draft.id}`">Betreff</label>
      <input :id="`subject-${draft.id}`" v-model="subject" type="text" class="draft__subject" />

      <label class="draft__label" :for="`body-${draft.id}`">Text</label>
      <textarea :id="`body-${draft.id}`" v-model="body" rows="9" class="draft__body" />

      <p v-if="error" class="draft__error" role="alert">{{ error }}</p>

      <div class="draft__actions">
        <span class="mono draft__note">Wird erst auf Klick verschickt.</span>
        <button type="button" class="button--primary" :disabled="busy" @click="send">
          {{ busy ? "Wird verschickt …" : "Senden" }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* Füllt jetzt seinen Container komplett aus (das Board), statt als kleine
   Karte im Chatverlauf zu stehen — deshalb Höhe/Breite vom Elternelement statt
   eigener Kastenoptik, und der Text-Bereich wächst mit dem verfügbaren Platz
   statt eine feste Zeilenzahl zu behaupten. */
.draft {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 1.25rem 1.5rem;
}

/* Verschickt heißt: Beleg, keine Aufgabe mehr. Ein leichter Ton statt Kontur
   genügt, um das zu markieren. */
.draft--sent {
  background: var(--color-surface-muted);
}

.draft__head {
  flex: none;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
  margin: 0 0 1rem;
}

.draft__to {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--color-ink-3);
}

.draft__label {
  flex: none;
  display: block;
  margin-bottom: 0.25rem;
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-ink-5);
}

/* Größer als ein normales Eingabefeld — der Betreff liest sich hier eher wie
   eine Überschrift, die man noch anpassen kann. */
.draft__subject {
  flex: none;
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 1.25rem;
  padding-bottom: 0.375rem;
  font-size: var(--font-size-lg);
  font-weight: 500;
}

.draft__body {
  flex: 1;
  min-height: 0;
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 1rem;
  border: 1px solid var(--color-line);
  padding: 0.875rem 1rem;
  font-size: var(--font-size-md);
  line-height: var(--line-height-body);
  resize: none;
}

.draft__subject-sent {
  margin: 0 0 0.25rem;
  font-size: var(--font-size-lg);
  font-weight: 500;
}

.draft__meta {
  margin: 0;
}

.draft__error {
  flex: none;
  margin: 0 0 0.75rem;
  color: var(--color-error);
  font-size: var(--font-size-md);
}

.draft__actions {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.draft__note {
  margin: 0;
}
</style>
