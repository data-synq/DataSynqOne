<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useChatStore } from "../stores/chat";
import { useSessionsStore } from "../stores/sessions";

const chatStore = useChatStore();
const sessionsStore = useSessionsStore();

onMounted(() => sessionsStore.fetch());

// Bei maximiertem Board ist links kein Platz für die Historie — sie bleibt
// gesperrt, bis wieder verkleinert wird (siehe cycleState() im Panel).
const historyLocked = computed(() => chatStore.presentationPanelState === "maximized");

async function select(id: string) {
  await chatStore.loadSession(id);
}

function remove(id: string, event: MouseEvent) {
  event.stopPropagation();
  sessionsStore.remove(id);
}

function relativeDate(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "Heute";
  if (days === 1) return "Gestern";
  if (days < 7) return `vor ${days} Tagen`;
  return new Date(iso).toLocaleDateString("de-DE");
}
</script>

<template>
  <aside class="history" :class="{ 'history--open': chatStore.historyOpen }">
    <!-- Eingeklappt und ausgeklappt schließen sich aus, statt übereinander zu
         liegen — sonst verschwinden Bedienelemente der einen Ansicht unter
         der anderen, wie es der Overlay-Ansatz zuvor getan hat. -->
    <Transition name="rail">
      <div v-if="!chatStore.historyOpen" class="history__rail">
        <button
          type="button"
          class="history__rail-btn"
          :disabled="historyLocked"
          :aria-label="historyLocked ? 'Verlauf gesperrt, solange das Board maximiert ist' : 'Verlauf ausklappen'"
          :title="historyLocked ? 'Erst verkleinern, um die Historie zu öffnen' : undefined"
          @click="chatStore.historyOpen = true"
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M6 3 11 8 6 13" fill="none" stroke="currentColor" stroke-width="1.5" />
          </svg>
        </button>
        <button type="button" class="history__rail-btn" aria-label="Neuer Chat" @click="chatStore.newChat()">
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path
              d="M10.5 2.5 13.5 5.5 5.5 13.5 2 14 2.5 10.5 10.5 2.5Z"
              fill="none"
              stroke="currentColor"
              stroke-width="1.3"
              stroke-linejoin="round"
              stroke-linecap="round"
            />
            <path d="M9 4 12 7" stroke="currentColor" stroke-width="1.3" />
          </svg>
        </button>
      </div>
    </Transition>

    <div v-if="chatStore.historyOpen" class="history__panel">
      <div class="history__head">
        <button type="button" class="button--secondary history__new" @click="chatStore.newChat()">
          Neuer Chat
        </button>
        <button
          type="button"
          class="history__collapse"
          aria-label="Verlauf einklappen"
          @click="chatStore.historyOpen = false"
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M10 3 5 8 10 13" fill="none" stroke="currentColor" stroke-width="1.5" />
          </svg>
        </button>
      </div>

      <div class="history__list">
        <p class="eyebrow history__eyebrow">Gespeicherte Chats</p>

        <p v-if="sessionsStore.loading" class="history__status mono">Lade …</p>
        <p v-else-if="!sessionsStore.items.length" class="history__status mono">
          Noch keine gespeicherten Chats.
        </p>

        <div
          v-for="s in sessionsStore.items"
          :key="s.id"
          class="history__row row-link"
          role="button"
          tabindex="0"
          @click="select(s.id)"
          @keydown.enter="select(s.id)"
        >
          <span class="history__title" :class="{ 'history__title--active': s.id === chatStore.sessionId }">
            {{ s.title }}
          </span>

          <!-- Titel nimmt die volle Breite, erst beim Hover schiebt sich
               rechts ein ausblendender Verlauf darüber, der Datum und
               Löschen trägt — der linke Teil des Titels bleibt unverdeckt. -->
          <div class="history__row-fade">
            <span class="mono history__date">{{ relativeDate(s.updated_at) }}</span>
            <button type="button" class="history__delete" aria-label="Chat löschen" @click="remove(s.id, $event)">
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path
                  d="M3.5 4.5h9M6.5 4.5V3a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v1.5M6.5 7.5v4M9.5 7.5v4M4.5 4.5l.6 8a1 1 0 0 0 1 .9h3.8a1 1 0 0 0 1-.9l.6-8"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
/* Feste Pixelbreiten statt fr/auto: nur so lässt sich die Spalte im
   umgebenden Grid überhaupt animiert ein- und ausfahren. */
.history {
  min-width: 0;
  height: 100%;
  overflow: hidden;
  border-right: 1px solid var(--color-line-strong);
  background: var(--color-canvas);
  transition: width var(--duration-slow) var(--ease-emphasized);
  width: 48px;
}

.history--open {
  width: 320px;
}

.history__rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  width: 48px;
  height: 100%;
  padding-top: 1.125rem;
}

.rail-enter-active {
  transition:
    opacity var(--duration-fast) var(--ease-standard),
    transform var(--duration-fast) var(--ease-standard);
  transition-delay: var(--duration-slow);
}

.rail-leave-active {
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.rail-enter-from {
  opacity: 0;
  transform: translateY(-4px);
}

.rail-leave-to {
  opacity: 0;
}

.history__rail-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-ink-4);
  cursor: pointer;
}

.history__rail-btn:hover {
  color: var(--color-ink);
}

.history__rail-btn:disabled {
  color: var(--color-line-strong);
  cursor: not-allowed;
}

.history__rail-btn:disabled:hover {
  color: var(--color-line-strong);
}

.history__rail-btn svg {
  width: 13px;
  height: 13px;
}

.history__panel {
  display: flex;
  flex-direction: column;
  width: 320px;
  height: 100%;
}

.history__head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 1.125rem 1.25rem 0.875rem;
  border-bottom: 1px solid var(--color-line);
}

.history__new {
  flex: 1;
}

.history__collapse {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--color-line-strong);
  background: transparent;
  padding: 0;
  color: var(--color-ink-4);
  cursor: pointer;
}

.history__collapse:hover {
  color: var(--color-ink);
  border-color: var(--color-ink);
}

.history__collapse svg {
  width: 12px;
  height: 12px;
}

.history__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-block: 1.125rem;
}

.history__eyebrow {
  margin: 0 0 0.5rem;
  padding-inline: 1.25rem;
}

.history__status {
  margin: 0;
  padding-inline: 1.25rem;
}

.history__row {
  position: relative;
  padding: 0.4375rem 1.25rem 0.5rem;
}

.history__title {
  display: block;
  width: 100%;
  font-size: var(--font-size-md);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history__title--active {
  color: var(--color-ink);
  font-weight: 500;
}

/* Der Titel bekommt die volle Breite. Erst beim Hover schiebt sich rechts
   ein Verlauf darüber, der nach links ausblendet — die linken ~70% des
   Titels bleiben dabei unverdeckt lesbar, rechts tragen die letzten 30%
   Datum und Löschen. */
.history__row-fade {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  padding-inline: 1.25rem;
  background: linear-gradient(to left, var(--color-canvas) 0%, var(--color-canvas) 30%, transparent 100%);
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.history__row:hover .history__row-fade,
.history__row:focus-within .history__row-fade {
  opacity: 1;
  pointer-events: auto;
}

.history__date {
  font-size: var(--font-size-2xs);
  white-space: nowrap;
  color: var(--color-ink-5);
}

.history__delete {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-ink-4);
  cursor: pointer;
}

.history__delete svg {
  width: 13px;
  height: 13px;
}

.history__delete:hover {
  color: var(--color-error);
}
</style>
