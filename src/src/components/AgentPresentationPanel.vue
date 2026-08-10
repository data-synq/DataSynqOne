<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useChatStore } from "../stores/chat";
import DocumentDetailView from "./DocumentDetailView.vue";
import BoardChartView from "./BoardChartView.vue";
import BoardEmailView from "./BoardEmailView.vue";

const store = useChatStore();

// Gehört konzeptionell zum Dokument-Inhalt, sitzt aber im Kopf des Panels
// statt in einer zweiten Zeile darunter — deshalb lebt der Zustand hier statt
// in DocumentDetailView, das nur noch anzeigt, was ihm übergeben wird.
const activeTab = ref<"original" | "text">("original");

watch(
  () => store.presentationContent,
  () => {
    activeTab.value = "original";
  },
);

const title = computed(() => {
  const content = store.presentationContent;
  if (!content) return "";
  if (content.type === "document") return `DOK-${content.documentId}`;
  if (content.type === "chart") return content.spec.title;
  if (content.type === "email") return "E-Mail-Entwurf";
  if (content.type === "html") return "Ansicht";
  return "Formular";
});

// Rail und offenes Board schließen sich aus: die Übersicht ist nur der Weg
// zurück zu etwas, das gerade NICHT zu sehen ist.
const panelClass = computed(() => {
  if (store.presentationContent) return `panel--${store.presentationPanelState}`;
  return store.allBoardEvents.length ? "panel--rail" : "panel--collapsed";
});

function cycleState() {
  const order: Record<string, "collapsed" | "default" | "maximized"> = {
    default: "maximized",
    maximized: "default",
    collapsed: "default",
  };
  const next = order[store.presentationPanelState];
  store.setPresentationPanelState(next);
  // Bei voller Breite ist links kein Platz mehr für die Historie — sie
  // entsperrt sich von selbst, sobald wieder verkleinert wird (siehe
  // historyLocked in ChatHistorySidebar.vue).
  if (next === "maximized") store.historyOpen = false;
}
</script>

<template>
  <aside
    class="panel"
    :class="panelClass"
    :aria-hidden="!store.presentationContent && !store.allBoardEvents.length"
  >
    <div v-if="store.presentationContent" class="panel__inner">
      <div class="panel__head">
        <span class="mono panel__title">{{ title }}</span>

        <div v-if="store.presentationContent.type === 'document'" class="panel__tabs">
          <button
            type="button"
            class="panel__tab"
            :class="{ 'panel__tab--active': activeTab === 'original' }"
            @click="activeTab = 'original'"
          >
            Original
          </button>
          <button
            type="button"
            class="panel__tab"
            :class="{ 'panel__tab--active': activeTab === 'text' }"
            @click="activeTab = 'text'"
          >
            Text (OCR)
          </button>
        </div>

        <div class="panel__actions">
          <button type="button" class="button--secondary" @click="cycleState">
            {{ store.presentationPanelState === "maximized" ? "Verkleinern" : "Vergrößern" }}
          </button>
          <button type="button" class="link-action" @click="store.closePresentation()">Schließen</button>
        </div>
      </div>

      <div class="panel__body">
        <DocumentDetailView
          v-if="store.presentationContent.type === 'document'"
          :document-id="store.presentationContent.documentId"
          :active-tab="activeTab"
        />
        <BoardChartView v-else-if="store.presentationContent.type === 'chart'" :spec="store.presentationContent.spec" />
        <BoardEmailView v-else-if="store.presentationContent.type === 'email'" :draft-id="store.presentationContent.draftId" />
      </div>
    </div>

    <!-- Nur sichtbar, solange kein Board offen ist — der einzige Zweck ist,
         zu etwas Gezeigtem zurückzufinden, das gerade nicht zu sehen ist. -->
    <div v-else-if="store.allBoardEvents.length" class="panel__rail">
      <button
        v-for="event in store.allBoardEvents"
        :key="event.id"
        type="button"
        class="panel__rail-btn"
        :aria-label="`${event.title} erneut öffnen`"
        :title="event.title"
        @click="store.reopenBoardEvent(event)"
      >
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path
            d="M3.5 1.5h6l3 3v10h-9v-13Z"
            fill="none"
            stroke="currentColor"
            stroke-width="1.2"
            stroke-linejoin="round"
          />
          <path d="M5.5 8h5M5.5 10.5h5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
        </svg>
      </button>
    </div>
  </aside>
</template>

<style scoped>
/* Feste Pixel-/Calc-Breiten statt fr/auto: nur so lässt sich die Spalte im
   umgebenden Grid überhaupt animiert ein- und ausfahren. */
.panel {
  min-width: 0;
  height: 100%;
  overflow: hidden;
  border-left: 1px solid var(--color-line);
  background: var(--color-white);
  transition: width var(--duration-slow) var(--ease-emphasized);
}

.panel--collapsed {
  width: 0px;
  border-left-width: 0;
}

.panel--default {
  width: 720px;
}

.panel--maximized {
  width: calc(100vw - 360px);
}

.panel--rail {
  width: 48px;
}

.panel__rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.625rem;
  height: 100%;
}

.panel__rail-btn {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--color-line-strong);
  background: transparent;
  padding: 0;
  color: var(--color-ink-4);
  cursor: pointer;
}

.panel__rail-btn:hover {
  color: var(--color-ink);
  border-color: var(--color-ink);
}

.panel__rail-btn svg {
  width: 15px;
  height: 15px;
}

.panel__inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
}

/* Eine einzige Kopfzeile statt zweier gestapelter: Titel, Tabs (falls das
   Dokument sie braucht) und die Panel-Aktionen stehen nebeneinander, nicht
   in getrennten Balken. Niedriger als vorher — oben soll möglichst wenig
   Platz verschenkt werden. */
.panel__head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 1.25rem;
  height: 44px;
  padding-inline: 1.125rem;
  border-bottom: 1px solid var(--color-line);
}

.panel__title {
  flex: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel__tabs {
  flex: 1;
  min-width: 0;
  display: flex;
  gap: 1rem;
}

.panel__tab {
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

.panel__tab--active {
  color: var(--color-ink);
}

.panel__actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 0.875rem;
  margin-left: auto;
}

.panel__body {
  flex: 1;
  min-height: 0;
  container-type: inline-size;
}
</style>
