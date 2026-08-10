<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";
import { useSessionsStore } from "../stores/sessions";
import AgentMessageList from "./AgentMessageList.vue";
import AgentPresentationPanel from "./AgentPresentationPanel.vue";
import ChatHistorySidebar from "./ChatHistorySidebar.vue";
import AccountMenu from "./dashboard/AccountMenu.vue";

const store = useChatStore();
const sessionsStore = useSessionsStore();

const input = ref("");
const inputEl = ref<HTMLTextAreaElement | null>(null);

const title = computed(() => {
  if (!store.sessionId) return "Assistent";
  return sessionsStore.items.find((s) => s.id === store.sessionId)?.title ?? "Assistent";
});

watch(
  () => store.chatDraft,
  (draft) => {
    if (draft) {
      input.value = draft;
      store.chatDraft = null;
      nextTick(() => inputEl.value?.focus());
    }
  },
);

async function submit() {
  const text = input.value.trim();
  if (!text || store.sending) return;
  input.value = "";
  await store.sendMessage(text);
}

function onInputEnter(event: KeyboardEvent) {
  if (event.shiftKey) return;
  event.preventDefault();
  submit();
}

async function useSuggestion(text: string) {
  if (store.sending) return;
  await store.sendMessage(text);
}

function close() {
  store.closeChat();
}

function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
}

// Esc schließt immer nur die oberste offene Ebene, nicht alles auf einmal:
// erst das Board (falls offen), erst dann den ganzen Fokusmodus. Das
// Account-Menü kümmert sich per stopPropagation() selbst darum, hierher gar
// nicht erst durchzukommen.
function onKeydown(event: KeyboardEvent) {
  if (!store.focusMode) return;

  if (event.key === "Escape") {
    if (store.presentationContent) {
      store.closePresentation();
    } else {
      close();
    }
    return;
  }

  if (isTypingTarget(event.target)) return;
  if (event.key === "n") {
    store.newChat();
  } else if (event.key === "h" && store.presentationPanelState !== "maximized") {
    // Gleiche Sperre wie der Ausklapp-Button in ChatHistorySidebar.vue —
    // bei maximiertem Board ist links kein Platz.
    store.historyOpen = !store.historyOpen;
  }
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => {
  window.removeEventListener("keydown", onKeydown);
  document.body.style.overflow = "";
});

// Der Vollbild-Overlay ist position:fixed — das hindert die dahinterliegende
// Seite nicht am Scrollen, wenn sie länger als der Bildschirm ist. Ohne das
// hier bliebe die globale Bildlaufleiste sichtbar, obwohl man sie nicht
// erreichen kann.
watch(
  () => store.focusMode,
  (open) => {
    document.body.style.overflow = open ? "hidden" : "";
  },
);

// Reines FLIP über Inline-Styles: die Ziel-Transition (top/left/width/height)
// steht fest im Stylesheet, die JS-Hooks setzen nur Start- und Endzustand.
function onBeforeEnter(el: Element) {
  const node = el as HTMLElement;
  const origin = store.focusOrigin;
  if (origin) {
    node.style.top = `${origin.top}px`;
    node.style.left = `${origin.left}px`;
    node.style.width = `${origin.width}px`;
    node.style.height = `${origin.height}px`;
    node.classList.add("focus--flip");
  } else {
    node.style.opacity = "0";
    node.style.transform = "scale(0.98)";
  }
}

// Ruft done() garantiert genau einmal auf — per transitionend, oder spätestens
// nach der Übergangsdauer als Netz. Ohne das bleibt der Vollbild-Overlay bei
// jedem CSS-Fehler, der eine Transition versehentlich stumm schaltet,
// unsichtbar aber unentfernt im DOM stehen und blockiert Klicks darunter.
function callOnce(fn: () => void): () => void {
  let called = false;
  return () => {
    if (called) return;
    called = true;
    fn();
  };
}

function onEnter(el: Element, done: () => void) {
  const node = el as HTMLElement;
  const finish = callOnce(done);
  requestAnimationFrame(() => {
    if (store.focusOrigin) {
      node.style.top = "0px";
      node.style.left = "0px";
      node.style.width = "100vw";
      node.style.height = "100dvh";
    } else {
      node.style.opacity = "1";
      node.style.transform = "scale(1)";
    }
    node.addEventListener("transitionend", finish, { once: true });
    setTimeout(finish, 700);
  });
  nextTick(() => inputEl.value?.focus());
}

function onAfterEnter(el: Element) {
  const node = el as HTMLElement;
  node.style.removeProperty("top");
  node.style.removeProperty("left");
  node.style.removeProperty("width");
  node.style.removeProperty("height");
  node.classList.remove("focus--flip");
}

function onLeave(el: Element, done: () => void) {
  const node = el as HTMLElement;
  const origin = store.focusOrigin;
  const finish = callOnce(done);

  // Esc/Zurück löschen focusOrigin synchron, bevor diese Transition überhaupt
  // startet — hier ist es also so gut wie immer null. .focus--flip transitioniert
  // nur top/left/width/height, nicht opacity/transform: würde die Klasse auch im
  // Fade-Zweig gesetzt, liefe die Opacity-Änderung ohne Übergang, transitionend
  // bliebe aus und done() würde nie aufgerufen — genau der Bug, der den Overlay
  // unsichtbar aber unentfernt im DOM zurückließ und die Teaser-Bar blockierte.
  if (origin) {
    const rect = node.getBoundingClientRect();
    node.style.top = `${rect.top}px`;
    node.style.left = `${rect.left}px`;
    node.style.width = `${rect.width}px`;
    node.style.height = `${rect.height}px`;
    node.classList.add("focus--flip");
    requestAnimationFrame(() => {
      node.style.top = `${origin.top}px`;
      node.style.left = `${origin.left}px`;
      node.style.width = `${origin.width}px`;
      node.style.height = `${origin.height}px`;
      node.addEventListener("transitionend", finish, { once: true });
      setTimeout(finish, 700);
    });
  } else {
    requestAnimationFrame(() => {
      node.style.opacity = "0";
      node.style.transform = "scale(0.98)";
      node.addEventListener("transitionend", finish, { once: true });
      setTimeout(finish, 700);
    });
  }
}
</script>

<template>
  <Transition
    :css="false"
    @before-enter="onBeforeEnter"
    @enter="onEnter"
    @after-enter="onAfterEnter"
    @leave="onLeave"
  >
    <div v-if="store.focusMode" class="focus">
      <div class="focus__head">
        <div class="focus__head-left">
          <button type="button" class="link-action" @click="close">← Zurück</button>
        </div>

        <h1 class="focus__title">{{ title }}</h1>

        <div class="focus__head-right">
          <AccountMenu />
        </div>
      </div>

      <div class="focus__body">
        <ChatHistorySidebar />

        <div class="focus__chat">
          <div class="focus__chat-inner">
            <AgentMessageList />

            <div class="focus__foot">
              <div v-if="!store.sending && store.suggestions.length" class="suggestions">
                <p class="eyebrow">Vorschläge</p>
                <button
                  v-for="(s, i) in store.suggestions"
                  :key="i"
                  type="button"
                  class="suggestions__item"
                  @click="useSuggestion(s)"
                >
                  {{ s }}
                </button>
              </div>

              <form class="input-row" @submit.prevent="submit">
                <label class="visually-hidden" for="focus-input">Frage an den Assistenten</label>
                <textarea
                  id="focus-input"
                  ref="inputEl"
                  v-model="input"
                  rows="1"
                  placeholder="Frage zur Verwaltung stellen"
                  @keydown.enter="onInputEnter"
                />
                <button type="submit" class="button--secondary" :disabled="store.sending || !input.trim()">
                  Senden
                </button>
              </form>
            </div>
          </div>
        </div>

        <AgentPresentationPanel />
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.focus {
  position: fixed;
  z-index: 80;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100dvh;
  display: grid;
  grid-template-rows: 52px minmax(0, 1fr);
  background: var(--color-white);
  opacity: 1;
  transform: scale(1);
  overflow: hidden;
  transition:
    opacity var(--duration-slow) var(--ease-emphasized),
    transform var(--duration-slow) var(--ease-emphasized);
}

.focus--flip {
  transition:
    top var(--duration-slow) var(--ease-emphasized),
    left var(--duration-slow) var(--ease-emphasized),
    width var(--duration-slow) var(--ease-emphasized),
    height var(--duration-slow) var(--ease-emphasized);
}

.focus__head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 1rem;
  height: 52px;
  padding-inline: 1.25rem;
  border-bottom: 1px solid var(--color-line);
}

.focus__head-left {
  display: flex;
  align-items: center;
  gap: 0.875rem;
}

.focus__head-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.focus__title {
  margin: 0;
  font-size: var(--font-size-md);
  font-weight: 500;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.focus__body {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  min-height: 0;
}

.focus__chat {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  /* Ein leichter Ton gegen das reine Weiß von Sidebar und Panel — sonst
     verschwimmt die Chatspalte mit allem drumherum. */
  background: var(--color-canvas);
}

.focus__chat-inner {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  width: 100%;
  max-width: 760px;
  margin-inline: auto;
}

/* Löst sich vom unteren Rand statt dort zu kleben, und hebt sich als eigene
   Fläche vom Verlaufshintergrund ab. */
.focus__foot {
  flex: none;
  margin: 0 1.25rem 1.75rem;
  padding: 0.875rem 1.125rem 1rem;
  background: var(--color-white);
  border: 1px solid var(--color-line);
}

.suggestions {
  display: flex;
  flex-direction: column;
  padding-bottom: 0.75rem;
}

.suggestions .eyebrow {
  margin: 0 0 0.375rem;
}

/* Zeilen statt Pillen: eine Liste, kein umbrechendes Wortgewusel. Nur oben
   und unten eine Linie — links/rechts bleibt offen, die Breite trägt sich
   selbst. */
.suggestions__item {
  border: 0;
  border-top: 1px solid var(--color-line-soft);
  background: transparent;
  padding: 0.5rem 0;
  font: inherit;
  font-size: var(--font-size-md);
  color: var(--color-accent);
  text-align: left;
  cursor: pointer;
}

.suggestions__item:last-child {
  border-bottom: 1px solid var(--color-line-soft);
}

.suggestions__item:hover {
  text-decoration: underline;
}

.input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 0.75rem;
}

.input-row textarea {
  max-height: 7rem;
  line-height: 1.4;
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
