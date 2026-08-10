<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useChatStore } from "../stores/chat";
import { api, ApiError, type CaseLinkEdge, type CaseSummary } from "../api/client";
import { formatDateTime } from "../utils/dates";
import { useCaseGraphLayout, type CaseGraphEdge } from "../composables/useCaseGraphLayout";

const route = useRoute();
const router = useRouter();
const chat = useChatStore();

const cases = ref<CaseSummary[]>([]);
const edges = ref<CaseLinkEdge[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

// --- Laden -------------------------------------------------------------

async function load() {
  loading.value = true;
  try {
    [cases.value, edges.value] = await Promise.all([api.listCases(), api.listAllCaseLinks()]);
    error.value = null;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Der Graph konnte nicht geladen werden.";
  } finally {
    loading.value = false;
  }
}

const validEdges = computed(() => {
  const ids = new Set(cases.value.map((c) => c.tracking_id));
  return edges.value.filter((e) => ids.has(e.dependent_tracking_id) && ids.has(e.prerequisite_tracking_id));
});

// --- Filter: eine zweite, ergänzende Art, den Graphen einzugrenzen -----------
// Getrennt vom Fokus (unten): der Fokus beantwortet "wovon hängt dieses eine
// Anliegen ab" vollständig und darf dabei nicht durch einen Zeitraum/Status/
// Objekt-Schnitt beschnitten werden — deshalb sind die Filter hier deaktiviert,
// solange ein Fokus aktiv ist, statt sich mit ihm zu vermischen.

type TimeRange = "7" | "30" | "90" | "all";
type StatusRange = "all" | "open" | "closed";

const TIME_PRESETS: { value: TimeRange; label: string }[] = [
  { value: "7", label: "7 Tage" },
  { value: "30", label: "30 Tage" },
  { value: "90", label: "90 Tage" },
  { value: "all", label: "Alle" },
];
const STATUS_PRESETS: { value: StatusRange; label: string }[] = [
  { value: "all", label: "Alle" },
  { value: "open", label: "Offen" },
  { value: "closed", label: "Geschlossen" },
];

// 90 Tage als Start: deutlich weniger Knoten als "alle" ohne dass man erst
// etwas einstellen muss.
const timeRange = ref<TimeRange>("90");
const statusFilter = ref<StatusRange>("all");
const objectFilter = ref<string>(""); // "" = alle Objekte

const distinctObjects = computed(() => {
  const set = new Set<string>();
  for (const c of cases.value) if (c.object_code) set.add(c.object_code);
  return Array.from(set).sort();
});

const filteredBaseCases = computed(() => {
  let result = cases.value;
  if (timeRange.value !== "all") {
    const cutoff = Date.now() - Number(timeRange.value) * 86_400_000;
    result = result.filter((c) => new Date(c.created_at).getTime() >= cutoff);
  }
  if (statusFilter.value !== "all") {
    result = result.filter((c) => c.status === statusFilter.value);
  }
  if (objectFilter.value) {
    result = result.filter((c) => c.object_code === objectFilter.value);
  }
  return result;
});

// --- Fokus-Filter: ein Anliegen und sein gesamter Abhängigkeits-Zusammenhang --

const focusedId = ref<string | null>(null);
const searchQuery = ref("");
const searchOpen = ref(false);

function neighborhoodOf(trackingId: string): Set<string> {
  const adjacency = new Map<string, string[]>();
  for (const e of validEdges.value) {
    (adjacency.get(e.dependent_tracking_id) ?? adjacency.set(e.dependent_tracking_id, []).get(e.dependent_tracking_id)!).push(
      e.prerequisite_tracking_id,
    );
    (adjacency.get(e.prerequisite_tracking_id) ?? adjacency.set(e.prerequisite_tracking_id, []).get(e.prerequisite_tracking_id)!).push(
      e.dependent_tracking_id,
    );
  }
  const seen = new Set<string>([trackingId]);
  const queue = [trackingId];
  while (queue.length) {
    const current = queue.shift()!;
    for (const neighbor of adjacency.get(current) ?? []) {
      if (!seen.has(neighbor)) {
        seen.add(neighbor);
        queue.push(neighbor);
      }
    }
  }
  return seen;
}

const filtersActive = computed(() => focusedId.value === null);

const visibleCases = computed(() => {
  if (focusedId.value) {
    const ids = neighborhoodOf(focusedId.value);
    return cases.value.filter((c) => ids.has(c.tracking_id));
  }
  return filteredBaseCases.value;
});

// Immer aus visibleCases abgeleitet, egal ob die über den Fokus oder über die
// Filter entstanden sind — beide Wege liefern am Ende einfach eine Knotenmenge.
const visibleEdges = computed(() => {
  const ids = new Set(visibleCases.value.map((c) => c.tracking_id));
  return validEdges.value.filter((e) => ids.has(e.dependent_tracking_id) && ids.has(e.prerequisite_tracking_id));
});

const searchResults = computed(() => {
  const term = searchQuery.value.trim().toLowerCase();
  if (term.length < 1) return [];
  return cases.value
    .filter((c) => c.tracking_id.toLowerCase().includes(term) || c.title.toLowerCase().includes(term))
    .slice(0, 8);
});

function focusOn(trackingId: string) {
  focusedId.value = trackingId;
  searchQuery.value = "";
  searchOpen.value = false;
  router.replace({ query: { ...route.query, focus: trackingId } });
}

function clearFocus() {
  focusedId.value = null;
  const query = { ...route.query };
  delete query.focus;
  router.replace({ query });
}

watch(
  () => route.query.focus,
  (value) => {
    focusedId.value = typeof value === "string" ? value : null;
  },
  { immediate: true },
);

// --- Layout: git-graph-artige Spuren, Position = tatsächliche Zeit -----------
// Die eigentliche Algorithmik lebt in useCaseGraphLayout — geteilt mit dem
// eingebetteten Mini-Graphen auf der Anliegen-Detailseite.

const { NODE_W, NODE_H, layout, graphWidth, graphHeight, monthMarks, edgeGeometries } = useCaseGraphLayout(
  visibleCases,
  visibleEdges,
  {
    // Deutlich größer als vorher ("deutlich größer") — mehr Platz pro Knoten,
    // damit Beschriftung und Datum lesbar bleiben, auch wenn viele Kanten
    // daneben verlaufen.
    nodeWidth: 260,
    nodeHeight: 76,
    laneGap: 64,
    padding: 56,
    // Zeit ist die eigentliche Achse: jeder Tag bekommt denselben Pixel-Abstand,
    // unabhängig davon, wie viele Anliegen an dem Tag entstanden sind. Ein Tag
    // mit vielen Anliegen weicht dem nur lokal aus (Kollisionsauflösung).
    pxPerDay: 22,
  },
);

// --- Hervorhebung beim Überfahren: der eigentliche Ausweg aus "man kann die
// einzelnen Verbindungen nicht zuordnen" — selbst ein sauberes Layout hat bei
// 100 Knoten noch Kreuzungen, das Nachverfolgen per Fokus löst den Rest. -----

const hoveredId = ref<string | null>(null);

const connectedIds = computed(() => {
  if (!hoveredId.value) return null;
  const ids = new Set<string>([hoveredId.value]);
  for (const edge of edgeGeometries.value) {
    if (edge.dependent === hoveredId.value) ids.add(edge.prerequisite);
    if (edge.prerequisite === hoveredId.value) ids.add(edge.dependent);
  }
  return ids;
});

function isDimmed(id: string): boolean {
  return connectedIds.value !== null && !connectedIds.value.has(id);
}

const hoveredNode = computed(() => layout.value.nodes.find((n) => n.trackingId === hoveredId.value) ?? null);

function isEdgeDimmed(edge: CaseGraphEdge): boolean {
  return connectedIds.value !== null && !(connectedIds.value.has(edge.dependent) && connectedIds.value.has(edge.prerequisite));
}

// --- Pan & Zoom -----------------------------------------------------------

const viewport = ref<HTMLDivElement | null>(null);
const sidebarCollapsed = ref(false);
const scale = ref(1);
const translate = ref({ x: 0, y: 0 });
const dragging = ref(false);
let dragMoved = false;
let dragStart = { x: 0, y: 0 };
let translateStart = { x: 0, y: 0 };
let capturedPointerId: number | null = null;
let captureEl: HTMLElement | null = null;

function clampScale(value: number): number {
  return Math.min(2.5, Math.max(0.15, value));
}

// Feste Raststufen für den Zoom-Schieberegler unten rechts — ein "Einrast-
// slider" ist hier einfach ein <input type="range"> über den Index dieser
// Liste statt über den Zoomwert selbst, dann springt er nur zwischen diesen
// Werten statt stufenlos zu laufen.
const ZOOM_LEVELS = [0.25, 0.5, 0.75, 1, 1.5, 2, 2.5];

function zoomAroundCenter(newScale: number) {
  const el = viewport.value;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const cx = rect.width / 2;
  const cy = rect.height / 2;
  const clamped = clampScale(newScale);
  const worldX = (cx - translate.value.x) / scale.value;
  const worldY = (cy - translate.value.y) / scale.value;
  translate.value = { x: cx - worldX * clamped, y: cy - worldY * clamped };
  scale.value = clamped;
}

const zoomLevelIndex = computed<number>({
  get: () => {
    let closest = 0;
    let bestDiff = Infinity;
    ZOOM_LEVELS.forEach((level, i) => {
      const diff = Math.abs(level - scale.value);
      if (diff < bestDiff) {
        bestDiff = diff;
        closest = i;
      }
    });
    return closest;
  },
  set: (index: number) => zoomAroundCenter(ZOOM_LEVELS[index]),
});

// Wie stark ein Knoten beim Überfahren wächst, hängt vom aktuellen Zoom ab:
// weit rausgezoomt sind Knoten winzig, da darf der Hover-Effekt kräftig
// ausfallen; nah rangezoomt ist der Knoten schon groß genug, dort würde
// derselbe Sprung nur unruhig wirken.
const HOVER_SCALE_MAX = 1.5; // bei starkem Rauszoomen (scale <= HOVER_SCALE_LOW)
const HOVER_SCALE_MIN = 1.08; // bei starkem Reinzoomen (scale >= HOVER_SCALE_HIGH)
const HOVER_SCALE_LOW = 0.4;
const HOVER_SCALE_HIGH = 1.5;

const hoverScale = computed(() => {
  const t = Math.min(1, Math.max(0, (scale.value - HOVER_SCALE_LOW) / (HOVER_SCALE_HIGH - HOVER_SCALE_LOW)));
  return HOVER_SCALE_MAX - t * (HOVER_SCALE_MAX - HOVER_SCALE_MIN);
});

// Höhe des fest angedockten Datums-Streifens unten (siehe Template) — beim
// Einpassen von der nutzbaren Höhe abgezogen, damit die letzte Spur nicht
// dahinter verschwindet.
const AXIS_HEIGHT = 28;

function fitToView() {
  const el = viewport.value;
  if (!el || !layout.value.nodes.length) return;
  const rect = el.getBoundingClientRect();
  const usableHeight = Math.max(1, rect.height - AXIS_HEIGHT);
  const s = clampScale(Math.min(rect.width / graphWidth.value, usableHeight / graphHeight.value, 1));
  scale.value = s;
  // Links angepinnt statt zentriert: die Zeitachse läuft jetzt waagerecht,
  // "lesen" beginnt links (früheste Anliegen) statt oben.
  translate.value = {
    x: 16,
    y: (usableHeight - graphHeight.value * s) / 2,
  };
}

// Bildschirm-Position der Monatsmarken für den fest angedockten Streifen unten
// — dieselben Weltkoordinaten wie die Gitterlinien im Graphen, aber mit dem
// aktuellen Verschieben/Zoomen multipliziert, damit die Beschriftung beim
// Verschieben "mitläuft", statt (wie die Gitterlinien selbst) mit dem Inhalt
// aus dem sichtbaren Bereich zu wandern. "ich will da unten immer das Datum
// sehen, also das soll so fix als Timeline immer mitlaufen."
const axisMarks = computed(() =>
  monthMarks.value.map((mark) => ({
    x: translate.value.x + mark.x * scale.value,
    label: mark.label,
  })),
);

// Die Monatsmarken sagen nur, in welchem Monat ein Knoten liegt — beim Hovern
// zeigt derselbe angedockte Streifen zusätzlich das exakte Datum, an genau der
// Stelle, an der der Knoten gerade steht (dieselbe Umrechnung wie oben).
const hoveredAxisMark = computed(() => {
  if (!hoveredNode.value) return null;
  return {
    x: translate.value.x + (hoveredNode.value.x + NODE_W / 2) * scale.value,
    label: formatDateTime(hoveredNode.value.createdAt),
  };
});

// Reines Mausrad scrollt/verschiebt wie eine normale Fläche — das entspricht
// dem Reflex beim Scrollen über eine große Karte. Zoomen ist ein bewusster
// Zusatzgriff (Strg/Cmd+Rad), genau wie bei Figma/Miro/Google Maps — ein
// Trackpad-Pinch feuert dasselbe Rad-Ereignis mit ctrlKey=true, profitiert
// also automatisch mit.
function onWheel(event: WheelEvent) {
  event.preventDefault();
  const el = viewport.value;
  if (!el) return;

  if (event.ctrlKey || event.metaKey) {
    const rect = el.getBoundingClientRect();
    const cx = event.clientX - rect.left;
    const cy = event.clientY - rect.top;
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
    const newScale = clampScale(scale.value * factor);
    const worldX = (cx - translate.value.x) / scale.value;
    const worldY = (cy - translate.value.y) / scale.value;
    translate.value = { x: cx - worldX * newScale, y: cy - worldY * newScale };
    scale.value = newScale;
    return;
  }

  translate.value = { x: translate.value.x - event.deltaX, y: translate.value.y - event.deltaY };
}

// Pointer-Capture greift jetzt erst NACH der Bewegungsschwelle, nicht schon
// bei pointerdown: sobald ein Element den Zeiger einmal capturet, werden
// Klicks in Browsern typischerweise mit auf das capturende Element umgeleitet
// — ein einfacher Klick auf einen Knoten wäre damit nie beim Knoten
// angekommen. Ohne vorzeitiges Capture feuert ein echter Klick (keine
// nennenswerte Bewegung) ganz normal auf dem Element darunter; erst ein
// wirkliches Ziehen löst Capture + Verschieben aus.
function onPointerDown(event: PointerEvent) {
  // Das Zoom-Panel (Slider/Knöpfe) schwebt über der Zeichenfläche und liegt
  // damit innerhalb des Viewports — ohne diese Ausnahme würde ein Ziehen am
  // Schieberegler gleichzeitig als Verschieben des Graphen gewertet, das
  // Capture dem Panel wegnehmen und die Slider-Bedienung mittendrin abbrechen.
  if ((event.target as HTMLElement).closest(".zoom-panel")) return;
  dragMoved = false;
  dragStart = { x: event.clientX, y: event.clientY };
  translateStart = { ...translate.value };
  captureEl = event.currentTarget as HTMLElement;
  capturedPointerId = event.pointerId;
}

function onPointerMove(event: PointerEvent) {
  if (capturedPointerId === null || capturedPointerId !== event.pointerId) return;
  const dx = event.clientX - dragStart.x;
  const dy = event.clientY - dragStart.y;
  if (!dragMoved && Math.hypot(dx, dy) > 4) {
    dragMoved = true;
    dragging.value = true;
    captureEl?.setPointerCapture(event.pointerId);
  }
  if (dragMoved) {
    translate.value = { x: translateStart.x + dx, y: translateStart.y + dy };
  }
}

function onPointerUp(event: PointerEvent) {
  if (dragging.value && captureEl?.hasPointerCapture(event.pointerId)) {
    captureEl.releasePointerCapture(event.pointerId);
  }
  dragging.value = false;
  capturedPointerId = null;
}

function zoomBy(factor: number) {
  zoomAroundCenter(scale.value * factor);
}

function openCase(trackingId: string) {
  if (dragMoved) return; // ein echtes Ziehen, das über einem Knoten endet, ist kein Klick
  chat.openCasePopup(trackingId);
}

async function confirmEdge(edge: CaseGraphEdge) {
  error.value = null;
  try {
    await api.confirmCaseLink(edge.dependent, edge.prerequisite);
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Verknüpfung konnte nicht bestätigt werden.";
  }
}

async function rejectEdge(edge: CaseGraphEdge) {
  error.value = null;
  try {
    await api.removeCaseLink(edge.dependent, edge.prerequisite);
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Verknüpfung konnte nicht entfernt werden.";
  }
}

watch(
  () => [focusedId.value, layout.value.nodes.length, timeRange.value, statusFilter.value, objectFilter.value] as const,
  () => nextTick(fitToView),
);

// Die Seitenleiste blendet mit einer Breiten-Transition ein/aus (wie
// DocumentDetailView.vue) — sofort neu einpassen würde noch die alte Breite
// sehen; nach der Transitionsdauer (--duration-slow, 600ms) passt es.
watch(sidebarCollapsed, () => setTimeout(fitToView, 650));

// --- Tastaturkürzel --------------------------------------------------------
// Esc schließt jeweils die "oberste" Ebene: erst die Such-Vorschläge, dann den
// aktiven Fokus. Das Popup (falls offen) schließt sich selbst über sein
// eigenes Esc — diese Seite muss davon nichts wissen.
const searchInput = ref<HTMLInputElement | null>(null);

function isTypingContext(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    if (searchOpen.value) {
      searchOpen.value = false;
    } else if (focusedId.value) {
      clearFocus();
    }
    return;
  }
  if (isTypingContext(event.target)) return;
  if (event.key === "/") {
    event.preventDefault();
    searchInput.value?.focus();
  } else if (event.key === "+" || event.key === "=") {
    zoomBy(1.3);
  } else if (event.key === "-") {
    zoomBy(1 / 1.3);
  } else if (event.key === "0") {
    fitToView();
  } else if (event.key.startsWith("Arrow")) {
    event.preventDefault();
    const step = 70;
    const dx = event.key === "ArrowLeft" ? step : event.key === "ArrowRight" ? -step : 0;
    const dy = event.key === "ArrowUp" ? step : event.key === "ArrowDown" ? -step : 0;
    translate.value = { x: translate.value.x + dx, y: translate.value.y + dy };
  }
}

onMounted(async () => {
  window.addEventListener("keydown", onKeydown);
  await load();
  await nextTick(fitToView);
});

onUnmounted(() => {
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div class="graph-page">
    <div class="graph-header">
      <h2 class="graph-header__title">Abhängigkeitsgraph</h2>

      <div class="focus-search" @keydown.esc="searchOpen = false">
        <input
          ref="searchInput"
          v-model="searchQuery"
          type="search"
          class="focus-search__input"
          placeholder="Anliegen fokussieren … ( / )"
          autocomplete="off"
          @focus="searchOpen = true"
        />
        <div v-if="searchOpen && searchResults.length" class="focus-search__results">
          <button
            v-for="c in searchResults"
            :key="c.tracking_id"
            type="button"
            class="focus-search__result row-link"
            @click="focusOn(c.tracking_id)"
          >
            <span class="mono">{{ c.tracking_id }}</span>
            <span class="focus-search__result-title">{{ c.title }}</span>
          </button>
        </div>
      </div>

      <span v-if="focusedId" class="focus-pill">
        Fokus: <span class="mono">{{ focusedId }}</span>
        <button type="button" title="Filter aufheben" @click="clearFocus">✕</button>
      </span>

      <span
        class="mono graph-header__kbd"
        title="Tastenkürzel: Pfeiltasten verschieben, Esc schließt, +/− zoomt, 0 passt ein, / springt zur Suche. Strg/Cmd+Mausrad zoomt, einfaches Rad verschiebt."
      >
        <kbd>↑↓←→</kbd><kbd>Esc</kbd><kbd>+/−</kbd><kbd>0</kbd><kbd>/</kbd>
      </span>

      <RouterLink to="/anliegen" class="link-action graph-header__back">Zur Liste</RouterLink>
    </div>

    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>

    <div class="graph-body">
      <aside class="graph-sidebar" :class="{ 'graph-sidebar--collapsed': sidebarCollapsed }">
        <button
          type="button"
          class="graph-sidebar__toggle"
          :aria-label="sidebarCollapsed ? 'Filter einblenden' : 'Filter ausblenden'"
          :title="sidebarCollapsed ? 'Filter einblenden' : 'Filter ausblenden'"
          @click="sidebarCollapsed = !sidebarCollapsed"
        >
          <svg viewBox="0 0 16 16" aria-hidden="true" :class="{ 'graph-sidebar__toggle-icon--flipped': sidebarCollapsed }">
            <path d="M10 3 5 8 10 13" fill="none" stroke="currentColor" stroke-width="1.5" />
          </svg>
        </button>

        <div v-if="!sidebarCollapsed" class="filters" :class="{ 'is-disabled': !filtersActive }">
          <div class="filters__group">
            <span class="filters__label mono">Zeitraum</span>
            <div class="filters__stack">
              <button
                v-for="preset in TIME_PRESETS"
                :key="preset.value"
                type="button"
                class="filters__chip"
                :class="{ 'is-active': timeRange === preset.value }"
                :disabled="!filtersActive"
                @click="timeRange = preset.value"
              >
                {{ preset.label }}
              </button>
            </div>
          </div>

          <div class="filters__group">
            <span class="filters__label mono">Status</span>
            <div class="filters__stack">
              <button
                v-for="preset in STATUS_PRESETS"
                :key="preset.value"
                type="button"
                class="filters__chip"
                :class="{ 'is-active': statusFilter === preset.value }"
                :disabled="!filtersActive"
                @click="statusFilter = preset.value"
              >
                {{ preset.label }}
              </button>
            </div>
          </div>

          <div class="filters__group">
            <label class="filters__label mono" for="graph-object-filter">Objekt</label>
            <select id="graph-object-filter" v-model="objectFilter" :disabled="!filtersActive">
              <option value="">Alle Objekte</option>
              <option v-for="code in distinctObjects" :key="code" :value="code">{{ code }}</option>
            </select>
          </div>
        </div>
      </aside>

      <div class="graph-canvas">
        <p v-if="loading" class="mono graph-page__state">Wird geladen …</p>
        <p v-else-if="!cases.length" class="mono graph-page__state">Noch keine Anliegen.</p>

        <div
          v-else
          ref="viewport"
          class="graph-page__viewport"
          :class="{ 'is-dragging': dragging }"
          @wheel="onWheel"
          @pointerdown="onPointerDown"
          @pointermove="onPointerMove"
          @pointerup="onPointerUp"
          @pointercancel="onPointerUp"
        >
          <svg width="100%" height="100%">
            <g :transform="`translate(${translate.x}, ${translate.y}) scale(${scale})`">
              <g v-for="mark in monthMarks" :key="mark.label">
                <line :x1="mark.x" :y1="0" :x2="mark.x" :y2="graphHeight" class="graph__gridline" />
              </g>

              <path
                v-for="edge in edgeGeometries"
                :key="edge.key"
                :d="edge.path"
                class="graph__edge"
                :class="{ 'graph__edge--proposed': edge.status === 'proposed', 'graph__edge--dim': isEdgeDimmed(edge) }"
              />

              <foreignObject
                v-for="edge in edgeGeometries.filter((e) => e.status === 'proposed')"
                :key="`actions-${edge.key}`"
                :x="edge.midX - 44"
                :y="edge.midY - 12"
                width="88"
                height="24"
              >
                <div class="graph__edge-actions">
                  <button type="button" title="Bestätigen" @click="confirmEdge(edge)">✓</button>
                  <button type="button" title="Verwerfen" @click="rejectEdge(edge)">✗</button>
                </div>
              </foreignObject>

              <g
                v-for="node in layout.nodes"
                :key="node.trackingId"
                class="graph__node"
                :class="{ 'graph__node--closed': node.status === 'closed', 'graph__node--dim': isDimmed(node.trackingId) }"
                :style="{
                  // transform-origin bleibt immer gesetzt (nie an/aus) — sonst
                  // springt der Anker beim Verlassen für einen Frame auf den
                  // SVG-Standardursprung, bevor die Transition greift, und der
                  // Knoten 'zuckt' sichtbar Richtung unten rechts, während er
                  // wieder auf scale(1) zurückgeht. Nur der Skalierungswert
                  // selbst ändert sich, der Anker bleibt konstant der Mittelpunkt
                  // dieses Knotens.
                  transform: hoveredId === node.trackingId ? `scale(${hoverScale})` : 'scale(1)',
                  transformOrigin: `${node.x + NODE_W / 2}px ${node.y + NODE_H / 2}px`,
                }"
                @click="openCase(node.trackingId)"
                @mouseenter="hoveredId = node.trackingId"
                @mouseleave="hoveredId = null"
              >
                <rect :x="node.x" :y="node.y" :width="NODE_W" :height="NODE_H" class="graph__node-box" />
                <rect :x="node.x" :y="node.y" width="4" :height="NODE_H" class="graph__node-accent" />
                <!-- HTML statt SVG <text>: nur so lässt sich mit echtem
                     text-overflow:ellipsis pixelgenau an der Knotenbreite
                     abschneiden, statt nach einer festen Zeichenzahl zu raten
                     (die bei einer langen E-Mail-Adresse trotzdem übersteht
                     und bei einem kurzen Titel zu früh kappt). -->
                <foreignObject :x="node.x + 14" :y="node.y" :width="NODE_W - 22" :height="NODE_H">
                  <div class="graph__node-content" :class="{ 'graph__node-content--closed': node.status === 'closed' }">
                    <span class="mono graph__node-id">{{ node.trackingId }}</span>
                    <span class="graph__node-title">{{ node.title }}</span>
                    <span class="mono graph__node-date">
                      {{ formatDateTime(node.createdAt) }}<template v-if="node.senderEmail"> · {{ node.senderEmail }}</template>
                    </span>
                  </div>
                </foreignObject>

                <!-- Eindeutiger, unmissverständlicher Klickpunkt zusätzlich
                     zum ganzen Knoten — taucht erst beim Hover auf, damit die
                     Karte in Ruhe bleibt, wenn niemand danach greift. -->
                <foreignObject
                  v-if="hoveredId === node.trackingId"
                  :x="node.x"
                  :y="node.y + NODE_H + 6"
                  :width="NODE_W"
                  height="24"
                >
                  <button type="button" class="graph__node-action" @click.stop="chat.openCasePopup(node.trackingId)">
                    Anzeigen
                  </button>
                </foreignObject>
              </g>
            </g>
          </svg>

          <!-- Fest angedockt, außerhalb der verschieb-/zoombaren <g> — läuft beim
               Verschieben des Graphen immer mit, statt (wie die Gitterlinien
               selbst) aus dem sichtbaren Bereich zu wandern. -->
          <div class="graph-axis">
            <span
              v-for="mark in axisMarks"
              :key="mark.label"
              class="mono graph-axis__label"
              :style="{ left: `${mark.x}px` }"
            >
              {{ mark.label }}
            </span>
            <span
              v-if="hoveredAxisMark"
              class="mono graph-axis__label graph-axis__label--exact"
              :style="{ left: `${hoveredAxisMark.x}px` }"
            >
              {{ hoveredAxisMark.label }}
            </span>
          </div>

          <div class="zoom-panel">
            <button type="button" title="Verkleinern" @click="zoomBy(1 / 1.3)">−</button>
            <input
              v-model.number="zoomLevelIndex"
              type="range"
              class="zoom-panel__slider"
              min="0"
              :max="ZOOM_LEVELS.length - 1"
              step="1"
              title="Zoomstufe"
            />
            <button type="button" title="Vergrößern" @click="zoomBy(1.3)">+</button>
            <span class="mono zoom-panel__value">{{ Math.round(scale * 100) }}%</span>
            <button type="button" title="Ansicht einpassen" @click="fitToView">⤢</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Bewusst ohne .container: der Graph bekommt die volle Breite und den
   größten Teil der Höhe statt in die schmale Textspalte gezwängt zu werden. */
.graph-page {
  display: flex;
  flex-direction: column;
  height: calc(100dvh - 58px);
  padding-inline: var(--page-padding);
}

/* Ein schmaler Balken statt vier gestapelter Zeilen ("weniger hoher Header,
   mehr Graph sichtbar") — Titel, Suche, Fokus, Zoom, Tasten-Kurzlegende und
   der Rücklink stehen alle in einer Zeile. */
.graph-header {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: 52px;
  border-bottom: 1px solid var(--color-line);
}

.graph-header__title {
  flex: none;
  margin: 0;
  font-size: var(--font-size-md);
  font-weight: 600;
  white-space: nowrap;
}

.graph-header__kbd {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin-left: auto;
  color: var(--color-ink-5);
  cursor: help;
}

.graph-header__kbd kbd {
  padding: 0.05rem 0.3rem;
  border: 1px solid var(--color-line-strong);
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
}

.graph-header__back {
  flex: none;
  white-space: nowrap;
}

.graph-page__state {
  padding: var(--space-3);
  color: var(--color-ink-4);
}

/* Zweispaltig unterhalb des Headers: eine einklappbare Filter-Spur neben der
   Zeichenfläche, genau das Muster aus DocumentDetailView.vue (.detail__meta). */
.graph-body {
  flex: 1;
  min-height: 0;
  display: flex;
}

.graph-sidebar {
  position: relative;
  flex: none;
  display: flex;
  flex-direction: column;
  width: 208px;
  padding: var(--space-3) var(--space-3) var(--space-3) 0;
  overflow-y: auto;
  transition: width var(--duration-slow) var(--ease-emphasized);
}

.graph-sidebar--collapsed {
  width: 36px;
  padding-inline: 0;
  align-items: center;
  overflow: hidden;
}

.graph-sidebar__toggle {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-bottom: var(--space-2);
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-ink-4);
  cursor: pointer;
}

.graph-sidebar__toggle:hover {
  color: var(--color-ink);
}

.graph-sidebar__toggle svg {
  width: 13px;
  height: 13px;
  transition: transform var(--duration-fast) var(--ease-standard);
}

.graph-sidebar__toggle-icon--flipped {
  transform: rotate(180deg);
}

.filters {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.filters.is-disabled {
  opacity: 0.4;
}

.filters__group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
}

.filters__label {
  font-size: var(--font-size-2xs);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-ink-5);
}

.filters__stack {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.filters__chip {
  padding: 0.3rem 0.6rem;
  border: 1px solid var(--color-line-strong);
  background: var(--color-white);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.filters__chip.is-active {
  background: var(--color-ink);
  border-color: var(--color-ink);
  color: var(--color-white);
}

.filters__chip:disabled {
  cursor: not-allowed;
}

.filters__group select {
  width: 100%;
  height: 28px;
  font-size: var(--font-size-sm);
}

.graph-canvas {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: var(--space-3) 0 var(--space-3) var(--space-3);
  border-left: 1px solid var(--color-line);
}

.focus-search {
  position: relative;
  width: clamp(200px, 26vw, 340px);
}

.focus-search__input {
  width: 100%;
  height: 30px;
  font-size: var(--font-size-md);
}

.focus-search__results {
  position: absolute;
  z-index: 30;
  top: calc(100% + 0.375rem);
  left: 0;
  right: 0;
  max-height: 50vh;
  overflow-y: auto;
  background: var(--color-white);
  border: 1px solid var(--color-line-strong);
}

.focus-search__result {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 0.75rem;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 0;
  background: transparent;
  font: inherit;
  text-align: left;
}

.focus-search__result-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text);
}

.focus-pill {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.6rem;
  border: 1px solid var(--color-line-strong);
  font-size: var(--font-size-sm);
  white-space: nowrap;
}

.focus-pill button {
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--color-ink-4);
  cursor: pointer;
  font-size: var(--font-size-sm);
  line-height: 1;
}

.focus-pill button:hover {
  color: var(--color-error);
}

/* Schwebt unten rechts über der Zeichenfläche statt oben im Header zu stehen
   — "Zoom mit Einrastslider unten rechts in Graph View". Der Schieberegler
   selbst rastet ein, weil er nicht den Zoomwert direkt steuert, sondern den
   Index in ZOOM_LEVELS (step="1" über eine kurze Liste fester Stufen). */
.zoom-panel {
  position: absolute;
  right: var(--space-3);
  /* Über dem fest angedockten Datumsstreifen (28px), nicht darauf. */
  bottom: calc(28px + var(--space-2));
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.6rem;
  background: var(--color-white);
  border: 1px solid var(--color-line-strong);
}

.zoom-panel button {
  flex: none;
  width: 26px;
  height: 26px;
  border: 1px solid var(--color-line-strong);
  background: var(--color-white);
  font-size: var(--font-size-md);
  line-height: 1;
  cursor: pointer;
}

.zoom-panel button:hover {
  background: var(--color-surface-muted);
}

.zoom-panel__slider {
  width: 100px;
}

.zoom-panel__value {
  flex: none;
  width: 3.2em;
  color: var(--color-ink-4);
  text-align: right;
}

.graph-page__viewport {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  /* Eigener, sichtbar von der Seite abgesetzter Grund statt der geerbten
     Canvas-Farbe — sonst verschwimmen weiße Knoten fast unsichtbar mit dem
     fast-weißen Hintergrund darunter. */
  background: var(--color-surface-muted);
  border: 1px solid var(--color-line);
  cursor: grab;
  touch-action: none;
}

.graph-page__viewport.is-dragging {
  cursor: grabbing;
}

.graph__gridline {
  stroke: var(--color-line-soft);
  stroke-width: 1;
}

/* Fest angedockter Datumsstreifen unten — bewusst außerhalb der verschieb-/
   zoombaren <g>, damit die Beschriftung beim Verschieben sichtbar "mitläuft"
   statt mit dem Inhalt aus dem Bild zu wandern. */
.graph-axis {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 28px;
  overflow: hidden;
  background: var(--color-white);
  border-top: 1px solid var(--color-line);
  z-index: 15;
}

.graph-axis__label {
  position: absolute;
  bottom: 0;
  padding: 0.4rem 0 0.4rem 0.4rem;
  font-size: 11px;
  color: var(--color-ink-5);
  white-space: nowrap;
  transform: translateX(1px);
  border-left: 1px solid var(--color-line-soft);
}

/* Das exakte Datum des gerade gehovten Knotens — deutlich abgehoben von den
   Monatsmarken, damit klar ist: das ist eine Praezisionsangabe, keine
   weitere Gitterlinie. */
.graph-axis__label--exact {
  bottom: 4px;
  padding: 0.15rem 0.45rem;
  border-left: 0;
  border-radius: 2px;
  background: var(--color-accent-strong);
  color: var(--color-white);
  font-weight: 500;
  transform: translateX(-50%);
  z-index: 1;
  pointer-events: none;
}

.graph__edge {
  fill: none;
  stroke: var(--color-line-strong);
  stroke-width: 1.5;
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.graph__edge--proposed {
  stroke: var(--color-ink-4);
  stroke-dasharray: 4 3;
}

.graph__edge--dim {
  opacity: 0.12;
}

.graph__edge-actions {
  display: flex;
  gap: 4px;
  justify-content: center;
}

.graph__edge-actions button {
  width: 22px;
  height: 22px;
  border: 1px solid var(--color-line-strong);
  background: var(--color-white);
  font-size: var(--font-size-2xs);
  line-height: 1;
  cursor: pointer;
}

.graph__edge-actions button:hover {
  background: var(--color-surface-muted);
}

.graph__node {
  cursor: pointer;
  transition:
    opacity var(--duration-fast) var(--ease-standard),
    transform var(--duration-fast) var(--ease-standard);
}

/* Erscheint erst beim Hover, direkt unter dem (dann vergrößerten) Knoten —
   ein eindeutiger, unmissverständlicher Klickpunkt statt allein auf den
   Klick irgendwo auf der Karte zu setzen. */
.graph__node-action {
  display: block;
  margin: 0 auto;
  padding: 0.2rem 0.75rem;
  border: 1px solid var(--color-accent);
  background: var(--color-white);
  color: var(--color-accent);
  font-size: var(--font-size-2xs);
  font-weight: 500;
  cursor: pointer;
}

.graph__node-action:hover {
  background: var(--color-accent);
  color: var(--color-white);
}

.graph__node--dim {
  opacity: 0.25;
}

/* Weiß auf dem gemuteten Viewport-Grund liest jetzt klar als eigene Fläche.
   Die Kontur trägt Farbe statt eines einheitlichen Hellgrau — offen/
   geschlossen ist damit schon an der Kontur erkennbar, ohne zu hovern. Beim
   Hover bleibt die Füllung Weiß (sonst verschwände der Knoten beim Hover
   genau in den gemuteten Viewport-Grund) — nur die Kontur reagiert. */
.graph__node-box {
  fill: var(--color-white);
  stroke: var(--color-accent);
  stroke-width: 1.5;
  transition:
    stroke var(--duration-fast) var(--ease-standard),
    stroke-width var(--duration-fast) var(--ease-standard);
}

.graph__node-accent {
  fill: var(--color-accent);
}

.graph__node:hover .graph__node-box {
  stroke: var(--color-accent-strong);
  stroke-width: 2;
}

.graph__node--closed .graph__node-box {
  stroke: var(--color-line-strong);
}

.graph__node--closed .graph__node-accent {
  fill: var(--color-line-strong);
}

.graph__node--closed:hover .graph__node-box {
  stroke: var(--color-ink-3);
}

/* HTML statt SVG-<text>: text-overflow braucht ein Blockelement mit fester
   Breite, das kann natives SVG-Text nicht. pointer-events:none reicht die
   Maus an das darunterliegende <rect>/<g> durch — Klick/Hover verhalten sich
   unveraendert. */
.graph__node-content {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  height: 100%;
  font-family: var(--font-sans);
  pointer-events: none;
}

.graph__node-id,
.graph__node-title,
.graph__node-date {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.graph__node-id {
  font-size: 11px;
  color: var(--color-ink-4);
}

.graph__node-title {
  font-size: 13px;
  color: var(--color-text);
}

.graph__node-date {
  font-size: 10px;
  color: var(--color-ink-5);
}

.graph__node-content--closed .graph__node-id,
.graph__node-content--closed .graph__node-title {
  color: var(--color-ink-4);
}

.notice {
  margin-bottom: var(--space-2);
  padding: 0.625rem 0.75rem;
  border-left: 2px solid var(--color-error);
  background: var(--color-surface-muted);
  font-size: var(--font-size-md);
  color: var(--color-error);
}
</style>
