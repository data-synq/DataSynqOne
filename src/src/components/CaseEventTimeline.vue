<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import type { CaseEvent } from "../api/client";
import { formatDateTime, formatShortDate } from "../utils/dates";
import { EVENT_LABELS, LINK_LABELS } from "../utils/caseEvents";

const props = defineProps<{ events: CaseEvent[] }>();
const emit = defineEmits<{ open: [event: CaseEvent] }>();

const PADDING = 100;
// Groesster vorkommender Label-Text ("Verknüpfung entfernt", "Im Chat
// besprochen") bei der verwendeten Schriftgroesse gemessen, mit Puffer — eine
// grobe, aber fuer den ueblichen Fall ausreichende Kollisionsvermeidung, ohne
// echte Textbreiten messen zu muessen.
const MIN_GAP = 130;
const DOT_R = 6;
const LABEL_Y = 12;
const LINE_Y = 32;
const DATE_Y = 54;
const TIME_Y = 68;
const ACTOR_Y = 82;
const DETAIL_Y = 96;
const HEIGHT = 112;
const BOUNDARY_LABEL_Y = HEIGHT - 4;
const DETAIL_MAX_CHARS = 22;

// Neuestes Ereignis zuerst — links ist "jetzt", rechts geht es in die
// Vergangenheit. Der Server liefert chronologisch aufsteigend (aeltestes
// zuerst), hier wird nur die Anzeigereihenfolge gedreht.
const orderedEvents = computed(() => [...props.events].reverse());

const viewMode = ref<"graphic" | "log">("graphic");

function toggleView() {
  viewMode.value = viewMode.value === "graphic" ? "log" : "graphic";
  hoveredEvent.value = null;
}

const containerEl = ref<HTMLElement | null>(null);
const containerWidth = ref(0);
let resizeObserver: ResizeObserver | null = null;

onMounted(async () => {
  await nextTick();
  if (!containerEl.value) return;
  resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) containerWidth.value = entry.contentRect.width;
  });
  resizeObserver.observe(containerEl.value);
});

onUnmounted(() => {
  resizeObserver?.disconnect();
});

// Volle verfuegbare Breite ausnutzen, solange der Mindestabstand pro Knoten
// gewahrt bleibt — reicht der Platz nicht, wird die Spur (per overflow-x auf
// dem Scrollbereich) statt weiter gestaucht horizontal scrollbar.
const dotGap = computed(() => {
  if (props.events.length <= 1) return MIN_GAP;
  const available = Math.max(0, containerWidth.value - PADDING * 2);
  return Math.max(MIN_GAP, available / (props.events.length - 1));
});

const width = computed(() => {
  if (props.events.length <= 1) return Math.max(containerWidth.value, PADDING * 2);
  return PADDING * 2 + (props.events.length - 1) * dotGap.value;
});

function xFor(index: number): number {
  if (props.events.length === 1) return width.value / 2;
  return PADDING + index * dotGap.value;
}

function sameDay(aIso: string, bIso: string): boolean {
  return new Date(aIso).toDateString() === new Date(bIso).toDateString();
}

// Markiert jeden Tageswechsel entlang der Reihe mit einer gestrichelten Linie
// und dem Datum, in das man beim Weiterlesen (nach rechts, also rueckwaerts
// in der Zeit) eintritt.
const dayBoundaries = computed(() => {
  const list = orderedEvents.value;
  const marks: { x: number; label: string }[] = [];
  for (let i = 1; i < list.length; i++) {
    if (!sameDay(list[i - 1].created_at, list[i].created_at)) {
      marks.push({ x: (xFor(i - 1) + xFor(i)) / 2, label: formatShortDate(list[i].created_at) });
    }
  }
  return marks;
});

function hasLink(event: CaseEvent): boolean {
  return Boolean(event.link_kind && event.link_id);
}

function linkLabel(event: CaseEvent): string {
  return event.link_kind ? (LINK_LABELS[event.link_kind] ?? "Öffnen") : "Öffnen";
}

// Drei grobe Bedeutungsgruppen statt einer Farbe pro Ereignisart — bleibt auf
// einen Blick lesbar, zehn verschiedene Farben waeren nur Rauschen.
function bucketClass(kind: string): string {
  if (kind === "closed" || kind === "reopened") return "event-timeline__dot--status";
  if (kind === "linked" || kind === "unlinked") return "event-timeline__dot--link";
  return "event-timeline__dot--activity";
}

function actorLabel(event: CaseEvent): string {
  return event.actor_name ?? event.actor_label ?? "—";
}

function datePart(event: CaseEvent): string {
  return formatDateTime(event.created_at).split(", ")[0] ?? "";
}

function timePart(event: CaseEvent): string {
  return formatDateTime(event.created_at).split(", ")[1] ?? "";
}

function shortDetail(event: CaseEvent): string {
  if (!event.detail) return "";
  return event.detail.length > DETAIL_MAX_CHARS
    ? `${event.detail.slice(0, DETAIL_MAX_CHARS - 1)}…`
    : event.detail;
}

// Kein Popup, wenn es nichts zu ergaenzen gibt — Art/Datum/Zeit/Akteur stehen
// bereits immer am Knoten selbst.
function isPopupWorthy(event: CaseEvent): boolean {
  return Boolean(event.detail) || hasLink(event);
}

const hoveredEvent = ref<CaseEvent | null>(null);
const popupPos = ref({ left: 0, top: 0 });

function onDotEnter(event: CaseEvent, domEvent: MouseEvent) {
  if (!isPopupWorthy(event)) return;
  const target = domEvent.currentTarget as Element;
  const rect = target.getBoundingClientRect();
  popupPos.value = { left: rect.left + rect.width / 2, top: rect.bottom + 8 };
  hoveredEvent.value = event;
}

function onDotLeave() {
  hoveredEvent.value = null;
}

function onPopupAction(event: CaseEvent) {
  emit("open", event);
  hoveredEvent.value = null;
}
</script>

<template>
  <div ref="containerEl" class="event-timeline">
    <div class="event-timeline__toolbar">
      <div class="event-timeline__legend">
        <span class="event-timeline__legend-badge">Neueste</span>
        <span class="event-timeline__legend-arrow" aria-hidden="true">→</span>
        <span class="mono event-timeline__legend-text">Älter</span>
      </div>
      <button v-if="events.length" type="button" class="link-action" @click="toggleView">
        {{ viewMode === "graphic" ? "Listenansicht" : "Grafische Ansicht" }}
      </button>
    </div>

    <p v-if="!events.length" class="mono event-timeline__empty">Noch keine Einträge.</p>

    <div v-else class="event-timeline__content" :style="{ height: `${HEIGHT}px` }">
      <div v-if="viewMode === 'graphic'" class="event-timeline__scroll-x">
        <svg
          class="event-timeline__svg"
          :viewBox="`0 0 ${width} ${HEIGHT}`"
          :width="width"
          :height="HEIGHT"
          preserveAspectRatio="xMinYMin meet"
        >
          <line
            v-if="orderedEvents.length > 1"
            :x1="xFor(0)"
            :y1="LINE_Y"
            :x2="xFor(orderedEvents.length - 1)"
            :y2="LINE_Y"
            class="event-timeline__line"
          />

          <g v-for="mark in dayBoundaries" :key="mark.label + mark.x">
            <line :x1="mark.x" :y1="0" :x2="mark.x" :y2="HEIGHT" class="event-timeline__boundary-line" />
            <text :x="mark.x" :y="BOUNDARY_LABEL_Y" class="mono event-timeline__boundary-label">
              {{ mark.label }}
            </text>
          </g>

          <g
            v-for="(event, index) in orderedEvents"
            :key="event.id"
            class="event-timeline__dot-group"
            :class="{ 'event-timeline__dot-group--clickable': hasLink(event) }"
            @mouseenter="onDotEnter(event, $event)"
            @mouseleave="onDotLeave"
            @click="hasLink(event) && emit('open', event)"
          >
            <text :x="xFor(index)" :y="LABEL_Y" class="event-timeline__label">
              {{ EVENT_LABELS[event.kind] ?? event.kind }}
            </text>
            <circle
              v-if="index === 0"
              :cx="xFor(index)"
              :cy="LINE_Y"
              :r="DOT_R + 4"
              class="event-timeline__dot-halo"
            />
            <circle
              :cx="xFor(index)"
              :cy="LINE_Y"
              :r="DOT_R"
              :class="['event-timeline__dot', bucketClass(event.kind)]"
            />
            <text :x="xFor(index)" :y="DATE_Y" class="mono event-timeline__date">{{ datePart(event) }}</text>
            <text :x="xFor(index)" :y="TIME_Y" class="mono event-timeline__time">{{ timePart(event) }}</text>
            <text :x="xFor(index)" :y="ACTOR_Y" class="mono event-timeline__actor">{{ actorLabel(event) }}</text>
            <text v-if="event.detail" :x="xFor(index)" :y="DETAIL_Y" class="event-timeline__detail">
              {{ shortDetail(event) }}
            </text>
          </g>
        </svg>
      </div>

      <ol v-else class="event-timeline__log">
        <li
          v-for="(event, index) in orderedEvents"
          :key="event.id"
          class="event-timeline__log-item"
          :class="{ 'event-timeline__log-item--latest': index === 0 }"
        >
          <span class="mono event-timeline__log-date">{{ formatDateTime(event.created_at) }}</span>
          <span class="event-timeline__log-kind">{{ EVENT_LABELS[event.kind] ?? event.kind }}</span>
          <span class="mono event-timeline__log-actor">{{ actorLabel(event) }}</span>
          <span v-if="event.detail" class="event-timeline__log-detail">{{ event.detail }}</span>
          <button
            v-if="hasLink(event)"
            type="button"
            class="link-action event-timeline__log-link"
            @click="emit('open', event)"
          >
            {{ linkLabel(event) }}
          </button>
        </li>
      </ol>
    </div>

    <Teleport to="body">
      <div
        v-if="hoveredEvent"
        class="event-timeline__popup"
        :style="{ left: `${popupPos.left}px`, top: `${popupPos.top}px` }"
      >
        <p v-if="hoveredEvent.detail" class="event-timeline__popup-detail">{{ hoveredEvent.detail }}</p>
        <button
          v-if="hasLink(hoveredEvent)"
          type="button"
          class="link-action"
          @click="onPopupAction(hoveredEvent)"
        >
          {{ linkLabel(hoveredEvent) }}
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* Wie die eingebettete Abhängigkeits-Grafik (CaseDependencyGraph.vue): ein
   eigener, klar umrandeter Kasten statt frei schwebender Linien. */
.event-timeline {
  border: 1px solid var(--color-line);
  background: var(--color-surface-muted);
}

.event-timeline__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: 0.4rem 0.75rem;
  border-bottom: 1px solid var(--color-line);
}

.event-timeline__legend {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.event-timeline__legend-badge {
  padding: 0.05rem 0.4rem;
  background: var(--color-accent-strong);
  color: var(--color-white);
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.event-timeline__legend-arrow {
  color: var(--color-ink-4);
}

.event-timeline__legend-text {
  color: var(--color-ink-4);
  font-size: var(--font-size-2xs);
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.event-timeline__empty {
  margin: 0;
  padding: var(--space-3);
  color: var(--color-ink-4);
}

.event-timeline__content {
  min-height: 0;
}

/* Nur horizontal scrollbar — die Hoehe steht fest (:style oben), damit ein
   Umschalten zwischen Grafik und Liste den Abschnitt nicht springen laesst. */
.event-timeline__scroll-x {
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
}

.event-timeline__svg {
  display: block;
}

.event-timeline__line {
  stroke: var(--color-line-strong);
  stroke-width: 1.5;
}

.event-timeline__boundary-line {
  stroke: var(--color-line-soft);
  stroke-width: 1;
  stroke-dasharray: 3 3;
}

.event-timeline__boundary-label {
  font-size: 9px;
  fill: var(--color-ink-5);
  text-anchor: middle;
}

.event-timeline__dot {
  stroke: var(--color-white);
  stroke-width: 1.5;
  transition: r var(--duration-fast) var(--ease-standard);
}

.event-timeline__dot-halo {
  fill: none;
  stroke: var(--color-accent-strong);
  stroke-width: 1.5;
}

.event-timeline__dot-group--clickable {
  cursor: pointer;
}

.event-timeline__dot-group--clickable:hover .event-timeline__dot {
  r: 8;
}

.event-timeline__dot--status {
  fill: var(--color-accent-strong);
}

.event-timeline__dot--link {
  fill: var(--color-ink-4);
}

.event-timeline__dot--activity {
  fill: var(--color-line-strong);
}

.event-timeline__label,
.event-timeline__date,
.event-timeline__time,
.event-timeline__actor,
.event-timeline__detail {
  text-anchor: middle;
}

.event-timeline__label {
  font-size: 10px;
  font-weight: 500;
  fill: var(--color-text);
}

.event-timeline__date,
.event-timeline__time {
  font-size: 10px;
}

.event-timeline__date {
  fill: var(--color-text);
}

.event-timeline__time,
.event-timeline__actor {
  fill: var(--color-ink-4);
}

.event-timeline__actor {
  font-size: 10px;
}

.event-timeline__detail {
  font-size: 10px;
  fill: var(--color-ink-3);
}

.event-timeline__log {
  height: 100%;
  margin: 0;
  padding: 0.5rem 0.75rem;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  overflow-y: auto;
}

.event-timeline__log-item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.5rem;
  padding-left: 0.5rem;
  border-left: 2px solid transparent;
  font-size: var(--font-size-sm);
}

.event-timeline__log-item--latest {
  border-left-color: var(--color-accent-strong);
}

.event-timeline__log-date {
  color: var(--color-ink-4);
  min-width: 8.5rem;
}

.event-timeline__log-kind {
  font-weight: 500;
}

.event-timeline__log-actor {
  color: var(--color-ink-4);
}

.event-timeline__log-detail {
  flex-basis: 100%;
  color: var(--color-ink-3);
}

.event-timeline__log-link {
  margin-left: auto;
}

.event-timeline__popup {
  position: fixed;
  z-index: 80;
  transform: translateX(-50%);
  width: max-content;
  max-width: 320px;
  padding: 0.6rem 0.75rem;
  background: var(--color-white);
  border: 1px solid var(--color-line-strong);
  box-shadow: 0 2px 6px rgba(22, 24, 20, 0.12);
}

.event-timeline__popup-detail {
  margin: 0 0 0.4rem;
  font-size: var(--font-size-sm);
  color: var(--color-text);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.event-timeline__popup .link-action {
  display: block;
}
</style>
