<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useChatStore } from "../../stores/chat";

const store = useChatStore();
const draft = ref("");
const barEl = ref<HTMLDivElement | null>(null);
const inputEl = ref<HTMLInputElement | null>(null);

// "/" öffnet den Assistenten von überall auf dem Dashboard aus, wie die
// Sprungmarke in Slack/GitHub — außer man tippt gerade irgendwo anders.
function onKeydown(event: KeyboardEvent) {
  if (event.key !== "/" || store.focusMode) return;
  const target = event.target as HTMLElement | null;
  const typing = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable;
  if (typing) return;
  event.preventDefault();
  inputEl.value?.focus();
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));

function openFocus() {
  if (barEl.value) {
    const rect = barEl.value.getBoundingClientRect();
    store.focusOrigin = { top: rect.top, left: rect.left, width: rect.width, height: rect.height };
  }
  const text = draft.value.trim();
  if (text) {
    store.chatDraft = text;
    draft.value = "";
  }
  store.openChat();
}

function onWrapperClick(event: MouseEvent) {
  // Klicks, die schon vom Input oder Button behandelt wurden, nicht doppelt öffnen.
  if ((event.target as HTMLElement).closest("input, button")) return;
  openFocus();
}
</script>

<template>
  <div class="teaser-block">
    <p class="eyebrow">KI-Assistent</p>
    <div ref="barEl" class="teaser" @click="onWrapperClick">
      <svg class="teaser__icon" viewBox="0 0 16 16" aria-hidden="true">
        <path
          d="M8 1.5 9.4 5.6 13.5 7 9.4 8.4 8 12.5 6.6 8.4 2.5 7 6.6 5.6 8 1.5Z"
          fill="currentColor"
        />
      </svg>
      <input
        ref="inputEl"
        v-model="draft"
        type="text"
        class="teaser__input"
        placeholder="Frag den Assistenten…"
        @focus="openFocus"
        @keydown.enter.prevent="openFocus"
      />
      <button type="button" class="button--secondary teaser__send" @click.stop="openFocus">
        Senden
      </button>
    </div>
  </div>
</template>

<style scoped>
.teaser-block {
  margin: 0.75rem 0;
}

.teaser-block .eyebrow {
  margin: 0 0 0.5rem;
}

/* Präsent, aber nicht laut: dieselbe Linienoptik wie die KPI-Zeile darüber,
   und genauso breit wie sie — kein eigenes Breitenmaß, das aus dem Raster
   fällt. */
.teaser {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  height: 56px;
  padding-inline: 1.125rem;
  border: 1px solid var(--color-line);
  background: var(--color-white);
  cursor: text;
  transition: border-color var(--duration-fast) var(--ease-standard);
}

.teaser:hover {
  border-color: var(--color-line-strong);
}

.teaser__icon {
  flex: none;
  width: 18px;
  height: 18px;
  color: var(--color-accent);
}

/* Eigenständig deklariert statt auf die globale input-Regel zu vertrauen —
   die teilt sich sonst mit dem echten Chat-Input im Fokusmodus dieselbe
   Kaskade, obwohl beide unterschiedliche Breiten brauchen. */
.teaser__input {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  border: 0;
  padding: 0;
  background: transparent;
  font: inherit;
  font-size: var(--font-size-lg);
  color: var(--color-text);
}

.teaser__input:focus {
  outline: none;
}

.teaser__send {
  flex: none;
  height: 34px;
}
</style>
