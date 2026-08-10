<script setup lang="ts">
import { computed } from "vue";
import type { DashboardKpis, Deadline } from "../../api/client";

const props = defineProps<{
  kpis: DashboardKpis;
  deadlines: Deadline[];
  objectCount: number;
  generatedAt: string | null;
}>();

const today = computed(() =>
  new Date().toLocaleDateString("de-DE", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }),
);

// Der Lagesatz nennt kleine Zahlen aus: "Zwei Fristen" liest sich als Satz,
// "2 Fristen" als Tabellenzelle. Ab dreizehn kippt das, dort sind Ziffern
// schneller zu erfassen.
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

const dueThisWeek = computed(
  () => props.deadlines.filter((d) => d.days_until >= 0 && d.days_until <= 7).length,
);

const headline = computed(() => {
  const overdue = props.kpis.overdue;
  const soon = dueThisWeek.value;

  const overduePart =
    overdue === 0
      ? "Keine Frist ist überschritten"
      : overdue === 1
        ? "Eine Frist ist überschritten"
        : `${spell(overdue)} Fristen sind überschritten`;

  const soonPart =
    soon === 0
      ? "diese Woche wird nichts fällig"
      : soon === 1
        ? "ein Vorgang wird diese Woche fällig"
        : `${spell(soon)} Vorgänge werden diese Woche fällig`;

  // Erster Buchstabe groß, weil der zweite Teil im Satz kleingeschrieben
  // beginnt und je nach Lage vorne stehen kann.
  const sentence = `${overduePart}, ${soonPart}.`;
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
});

const syncedAt = computed(() => {
  if (!props.generatedAt) return null;
  const at = new Date(props.generatedAt);
  if (Number.isNaN(at.getTime())) return null;
  return at.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
});
</script>

<template>
  <section class="headline">
    <div>
      <p class="eyebrow headline__date">{{ today }}</p>
      <h1 class="headline__text">{{ headline }}</h1>
    </div>
    <div class="headline__right">
      <p class="mono headline__meta">
        {{ props.kpis.total.toLocaleString("de-DE") }} Dokumente<template v-if="objectCount">
          · {{ objectCount }} {{ objectCount === 1 ? "Objekt" : "Objekte" }}</template
        ><br />
        <template v-if="syncedAt">zuletzt synchronisiert {{ syncedAt }} Uhr</template>
      </p>
    </div>
  </section>
</template>

<style scoped>
.headline {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 2.25rem 0 1.5rem;
}

.headline__date {
  margin: 0;
}

.headline__text {
  margin: 0.625rem 0 0;
  max-width: 36ch;
  text-wrap: pretty;
}

.headline__right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.5rem;
}

.headline__meta {
  margin: 0;
  white-space: nowrap;
  text-align: right;
}

@media (max-width: 800px) {
  .headline {
    flex-direction: column;
    align-items: flex-start;
  }

  .headline__right {
    align-items: flex-start;
  }

  .headline__meta {
    text-align: left;
  }
}
</style>
