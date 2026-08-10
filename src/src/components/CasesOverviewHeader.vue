<script setup lang="ts">
import { computed } from "vue";
import type { CaseSummary } from "../api/client";
import { STALE_CASE_DAYS, daysSince, isSameDay } from "../utils/dates";

export type CasesQuickFilter = "today" | "stale" | null;

const props = defineProps<{ cases: CaseSummary[]; activeFilter: CasesQuickFilter }>();
const emit = defineEmits<{ select: [key: CasesQuickFilter] }>();

// Wie DashboardHeadline.vue: kleine Zahlen als Wort, das liest sich als Satz
// statt als Tabellenzelle.
const WORDS = [
  "keine",
  "eine",
  "zwei",
  "drei",
  "vier",
  "fünf",
  "sechs",
  "sieben",
  "acht",
  "neun",
  "zehn",
  "elf",
  "zwölf",
];

function spell(n: number): string {
  return WORDS[n] ?? String(n);
}

const openCases = computed(() => props.cases.filter((c) => c.status === "open"));

const newToday = computed(() => props.cases.filter((c) => isSameDay(c.created_at)).length);

// Die Antwort auf "wo soll ich starten": nicht die schiere Zahl offener
// Anliegen, sondern was am längsten unbearbeitet liegt.
const staleOpen = computed(
  () => openCases.value.filter((c) => daysSince(c.created_at) > STALE_CASE_DAYS).length,
);

const closedThisWeek = computed(
  () => props.cases.filter((c) => c.closed_at !== null && daysSince(c.closed_at) <= 7).length,
);

const headline = computed(() => {
  const todayPart =
    newToday.value === 0
      ? "Heute ist noch kein neues Anliegen eingegangen"
      : newToday.value === 1
        ? "Heute ist ein neues Anliegen eingegangen"
        : `Heute sind ${spell(newToday.value)} neue Anliegen eingegangen`;

  const stalePart =
    staleOpen.value === 0
      ? "keines ist länger als eine Woche offen"
      : staleOpen.value === 1
        ? "eines ist schon länger als eine Woche offen"
        : `${spell(staleOpen.value)} sind schon länger als eine Woche offen`;

  const sentence = `${todayPart}, ${stalePart}.`;
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
});

function toggle(key: "today" | "stale") {
  emit("select", props.activeFilter === key ? null : key);
}
</script>

<template>
  <section class="cases-overview">
    <p class="cases-overview__headline">{{ headline }}</p>
    <div class="cases-overview__tiles">
      <button
        type="button"
        class="cases-overview__tile"
        :class="{ 'is-active': activeFilter === 'today' }"
        @click="toggle('today')"
      >
        <span class="mono cases-overview__tile-value">{{ newToday }}</span>
        <span class="cases-overview__tile-label">Neu heute</span>
      </button>
      <button
        type="button"
        class="cases-overview__tile"
        :class="{ 'is-active': activeFilter === 'stale' }"
        @click="toggle('stale')"
      >
        <span class="mono cases-overview__tile-value">{{ staleOpen }}</span>
        <span class="cases-overview__tile-label">Offen seit über 7 Tagen</span>
      </button>
      <div class="cases-overview__tile cases-overview__tile--static">
        <span class="mono cases-overview__tile-value">{{ closedThisWeek }}</span>
        <span class="cases-overview__tile-label">Diese Woche geschlossen</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.cases-overview {
  margin-bottom: var(--space-3);
}

.cases-overview__headline {
  margin: 0 0 var(--space-2);
  color: var(--color-ink-3);
}

.cases-overview__tiles {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.cases-overview__tile {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-line-strong);
  background: var(--color-white);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background-color var(--duration-fast) var(--ease-standard),
    border-color var(--duration-fast) var(--ease-standard);
}

.cases-overview__tile--static {
  cursor: default;
}

.cases-overview__tile.is-active {
  background: var(--color-ink);
  border-color: var(--color-ink);
}

.cases-overview__tile.is-active .cases-overview__tile-value,
.cases-overview__tile.is-active .cases-overview__tile-label {
  color: var(--color-white);
}

.cases-overview__tile-value {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text);
}

.cases-overview__tile-label {
  font-size: var(--font-size-xs);
  color: var(--color-ink-4);
}
</style>
