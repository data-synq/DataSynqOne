<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";
import DocumentDetailView from "./DocumentDetailView.vue";

const store = useChatStore();
const activeTab = ref<"original" | "text">("original");

watch(
  () => store.sidePanel,
  () => {
    activeTab.value = "original";
  },
);

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && store.sidePanel !== null) store.closePanel();
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <div v-if="store.sidePanel !== null" class="scrim" @click.self="store.closePanel()">
    <div class="doc" role="dialog" aria-modal="true" aria-label="Dokument">
      <div class="doc__head">
        <span class="mono doc__id">DOK-{{ store.sidePanel.documentId }}</span>

        <div class="doc__tabs">
          <button
            type="button"
            class="doc__tab"
            :class="{ 'doc__tab--active': activeTab === 'original' }"
            @click="activeTab = 'original'"
          >
            Original
          </button>
          <button
            type="button"
            class="doc__tab"
            :class="{ 'doc__tab--active': activeTab === 'text' }"
            @click="activeTab = 'text'"
          >
            Text (OCR)
          </button>
        </div>

        <button type="button" class="link-action" @click="store.closePanel()">Schließen</button>
      </div>

      <DocumentDetailView :document-id="store.sidePanel.documentId" :active-tab="activeTab" class="doc__detail" />
    </div>
  </div>
</template>

<style scoped>
.scrim {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.75rem;
  background: rgba(22, 24, 20, 0.32);
}

.doc {
  display: flex;
  flex-direction: column;
  width: min(1180px, 100%);
  height: min(880px, 100%);
  background: var(--color-white);
  border: 1px solid var(--color-line-strong);
}

.doc__head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 1.25rem;
  height: 44px;
  padding-inline: 1.125rem;
  border-bottom: 1px solid var(--color-line);
}

.doc__id {
  flex: none;
}

.doc__tabs {
  flex: 1;
  min-width: 0;
  display: flex;
  gap: 1rem;
}

.doc__tab {
  border: 0;
  background: transparent;
  padding: 0;
  font: inherit;
  font-size: var(--font-size-sm);
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-ink-4);
  cursor: pointer;
}

.doc__tab--active {
  color: var(--color-ink);
}

.doc__detail {
  flex: 1;
  min-height: 0;
  container-type: inline-size;
}
</style>
