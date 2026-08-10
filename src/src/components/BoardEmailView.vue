<script setup lang="ts">
import { ref, watch } from "vue";
import { api, ApiError, type EmailDraft } from "../api/client";
import EmailDraftCard from "./EmailDraftCard.vue";

const props = defineProps<{ draftId: string }>();

const draft = ref<EmailDraft | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

watch(
  () => props.draftId,
  async (id) => {
    draft.value = null;
    error.value = null;
    loading.value = true;
    try {
      draft.value = await api.getDraft(id);
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : "Der Server ist nicht erreichbar.";
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);
</script>

<template>
  <div class="board-email">
    <p v-if="loading" class="board-email__status mono">Lade …</p>
    <p v-else-if="error" class="board-email__status board-email__status--error">{{ error }}</p>
    <EmailDraftCard v-else-if="draft" :draft="draft" class="board-email__card" />
  </div>
</template>

<style scoped>
/* Füllt die ganze Panel-Fläche — die Karte selbst übernimmt Höhe und Breite
   vollständig, damit sie mit dem Board (collapsed/default/maximized) mit
   skaliert statt bei einer festen Breite zu verharren. */
.board-email {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.board-email__status {
  margin: 1.25rem 1.5rem;
}

.board-email__status--error {
  color: var(--color-error);
}

.board-email__card {
  flex: 1;
  min-height: 0;
}
</style>
