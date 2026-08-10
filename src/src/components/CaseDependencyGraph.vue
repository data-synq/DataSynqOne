<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api, ApiError, type CaseLink, type CaseLinkEdge, type CaseSummary } from "../api/client";
import { useCaseGraphLayout } from "../composables/useCaseGraphLayout";

const props = defineProps<{ trackingId: string; links: CaseLink[] }>();

const router = useRouter();

const allCases = ref<CaseSummary[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

async function load() {
  loading.value = true;
  try {
    allCases.value = await api.listCases();
    error.value = null;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Der Graph konnte nicht geladen werden.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => props.trackingId, load);

// Nur der direkte Zusammenhang (1 Sprung) — für einen eingebetteten
// Schnellüberblick ist das genau richtig; die volle Kette gibt es im großen
// Graphen (Link darunter).
const neighborhoodCases = computed<CaseSummary[]>(() => {
  const ids = new Set<string>([props.trackingId]);
  for (const link of props.links) {
    ids.add(link.dependent_tracking_id);
    ids.add(link.prerequisite_tracking_id);
  }
  return allCases.value.filter((c) => ids.has(c.tracking_id));
});

const neighborhoodEdges = computed<CaseLinkEdge[]>(() =>
  props.links.map((l) => ({
    dependent_tracking_id: l.dependent_tracking_id,
    prerequisite_tracking_id: l.prerequisite_tracking_id,
    status: l.status,
    proposed_by: l.proposed_by,
    created_at: l.created_at,
  })),
);

const { NODE_W, NODE_H, layout, graphWidth, graphHeight, monthMarks, edgeGeometries } = useCaseGraphLayout(
  neighborhoodCases,
  neighborhoodEdges,
  {
    // Deutlich kleiner als der große Graph: hier geht es um einen schnellen
    // Überblick auf der Detailseite, nicht um Navigation — die Fläche skaliert
    // per SVG-viewBox in einen festen Rahmen, egal wie weit die Zeitspanne
    // zwischen den Anliegen auseinanderliegt.
    nodeWidth: 172,
    nodeHeight: 52,
    laneGap: 36,
    padding: 20,
    pxPerDay: 10,
  },
);

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

// Direkter Wechsel statt Popup — hier auf der Anliegen-Seite selbst darf ein
// Klick sofort umschalten, ohne den Umweg über die Schnellansicht.
function switchTo(trackingId: string) {
  if (trackingId === props.trackingId) return;
  router.push(`/anliegen/${trackingId}`);
}
</script>

<template>
  <div class="mini-graph">
    <p v-if="loading" class="mono mini-graph__status">Lade …</p>
    <p v-else-if="error" class="mini-graph__status mini-graph__status--error">{{ error }}</p>

    <svg
      v-else
      class="mini-graph__svg"
      :viewBox="`0 0 ${graphWidth} ${graphHeight}`"
      preserveAspectRatio="xMidYMid meet"
    >
      <!-- Statisch (kein Verschieben/Zoomen hier), deshalb reicht die
           Beschriftung direkt in derselben, per viewBox skalierten Fläche —
           anders als beim großen Graphen gibt es nichts, wovor sie "weglaufen"
           könnte. -->
      <g v-for="mark in monthMarks" :key="mark.label">
        <line :x1="mark.x" y1="0" :x2="mark.x" :y2="graphHeight" class="mini-graph__gridline" />
        <text :x="mark.x + 3" :y="graphHeight - 4" class="mini-graph__gridline-label">{{ mark.label }}</text>
      </g>

      <path
        v-for="edge in edgeGeometries"
        :key="edge.key"
        :d="edge.path"
        class="mini-graph__edge"
        :class="{ 'mini-graph__edge--proposed': edge.status === 'proposed' }"
      />

      <g
        v-for="node in layout.nodes"
        :key="node.trackingId"
        class="mini-graph__node"
        :class="{
          'mini-graph__node--self': node.trackingId === trackingId,
          'mini-graph__node--closed': node.status === 'closed',
          'mini-graph__node--dim': isDimmed(node.trackingId),
        }"
        @click="switchTo(node.trackingId)"
        @mouseenter="hoveredId = node.trackingId"
        @mouseleave="hoveredId = null"
      >
        <rect :x="node.x" :y="node.y" :width="NODE_W" :height="NODE_H" />
        <foreignObject :x="node.x + 8" :y="node.y" :width="NODE_W - 14" :height="NODE_H">
          <div class="mini-graph__node-content">
            <span class="mono mini-graph__node-id">{{ node.trackingId }}</span>
            <span class="mini-graph__node-title">{{ node.title }}</span>
          </div>
        </foreignObject>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.mini-graph {
  border: 1px solid var(--color-line);
  background: var(--color-surface-muted);
}

.mini-graph__status {
  margin: 0;
  padding: var(--space-3);
  color: var(--color-ink-4);
}

.mini-graph__status--error {
  color: var(--color-error);
}

.mini-graph__svg {
  display: block;
  width: 100%;
  height: 220px;
}

.mini-graph__gridline {
  stroke: var(--color-line-soft);
  stroke-width: 1;
}

.mini-graph__gridline-label {
  font-size: 9px;
  fill: var(--color-ink-5);
}

.mini-graph__edge {
  fill: none;
  stroke: var(--color-line-strong);
  stroke-width: 1.5;
}

.mini-graph__edge--proposed {
  stroke: var(--color-ink-4);
  stroke-dasharray: 4 3;
}

.mini-graph__node {
  cursor: pointer;
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.mini-graph__node--dim {
  opacity: 0.3;
}

.mini-graph__node rect {
  fill: var(--color-white);
  stroke: var(--color-accent);
  stroke-width: 1.5;
}

.mini-graph__node:hover rect {
  stroke: var(--color-accent-strong);
  stroke-width: 2;
}

.mini-graph__node--closed rect {
  stroke: var(--color-line-strong);
}

.mini-graph__node--closed .mini-graph__node-id,
.mini-graph__node--closed .mini-graph__node-title {
  color: var(--color-ink-4);
}

/* Das Anliegen dieser Seite hebt sich als gefüllte Fläche von seinen
   Nachbarn ab, statt nur eine weitere Box unter mehreren zu sein. */
.mini-graph__node--self {
  /* Ein Klick tut hier nichts (switchTo() bricht ab) — soll man ihr ansehen. */
  cursor: default;
}

.mini-graph__node--self rect {
  fill: var(--color-accent);
  stroke: var(--color-accent);
}

.mini-graph__node--self .mini-graph__node-id,
.mini-graph__node--self .mini-graph__node-title {
  color: var(--color-white);
}

/* HTML statt SVG-<text>: nur so lässt sich der Titel mit echtem
   text-overflow:ellipsis pixelgenau abschneiden. pointer-events:none reicht
   Klick/Hover an das darunterliegende <rect>/<g> durch. */
.mini-graph__node-content {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 1px;
  height: 100%;
  font-family: var(--font-sans);
  pointer-events: none;
}

.mini-graph__node-id,
.mini-graph__node-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini-graph__node-id {
  font-size: 10px;
  color: var(--color-ink-4);
}

.mini-graph__node-title {
  font-size: 11px;
  color: var(--color-text);
}
</style>
