<script setup lang="ts">
import { computed } from "vue";
import type { ChartBucket } from "../../api/client";
import { categoryLabel } from "../../theme/statusColors";

const props = defineProps<{ perWeek: ChartBucket; categories: ChartBucket }>();

// Beide Diagramme sind hier aus CSS gebaut, nicht aus Chart.js. Acht Balken
// und fünf Zeilen brauchen keine Canvas-Bibliothek, und aufs Canvas gezeichnet
// erben sie weder die Schrift noch die Linienfarben des Rasters daneben.
// Chart.js bleibt für die Diagramme, die der Assistent erzeugt.

const weeks = computed(() => {
  const max = Math.max(...props.perWeek.data, 1);
  return props.perWeek.labels.map((label, i) => {
    const value = props.perWeek.data[i] ?? 0;
    return {
      label,
      value,
      // Nullwerte bekommen eine Restlinie, sonst verschwindet die Woche
      // zwischen ihren Nachbarn und die Achse hat ein Loch.
      height: value === 0 ? "1px" : `${Math.round((value / max) * 100)}%`,
      peak: value === max && value > 0,
    };
  });
});

const average = computed(() => {
  if (!props.perWeek.data.length) return 0;
  const sum = props.perWeek.data.reduce((a, b) => a + b, 0);
  return Math.round(sum / props.perWeek.data.length);
});

const categories = computed(() => {
  const total = props.categories.data.reduce((a, b) => a + b, 0);
  return props.categories.labels.map((slug, i) => {
    const value = props.categories.data[i] ?? 0;
    return {
      slug,
      label: categoryLabel(slug),
      value,
      width: total ? `${Math.round((value / total) * 100)}%` : "0%",
    };
  });
});
</script>

<template>
  <section class="trends">
    <div class="trends__weeks">
      <div class="section-head">
        <h2>Eingang je Kalenderwoche</h2>
        <span class="mono">Ø {{ average }} Dokumente / Woche</span>
      </div>

      <div class="bars" :style="{ '--columns': weeks.length }">
        <div v-for="week in weeks" :key="week.label" class="bars__col">
          <span class="bars__value mono">{{ week.value }}</span>
          <div
            class="bars__bar"
            :style="{ height: week.height, background: week.peak ? 'var(--color-accent)' : 'var(--color-line-strong)' }"
          />
        </div>
      </div>
      <div class="bars__axis" :style="{ '--columns': weeks.length }">
        <span v-for="week in weeks" :key="week.label" class="mono">{{ week.label }}</span>
      </div>
    </div>

    <div class="trends__categories">
      <div class="section-head">
        <h2>Kategorien</h2>
        <span class="mono">letzte 60 Tage</span>
      </div>

      <p v-if="!categories.length" class="trends__empty mono">Keine Dokumente im Zeitraum.</p>
      <div v-for="category in categories" :key="category.slug" class="category">
        <div class="category__main">
          <span class="category__label">{{ category.label }}</span>
          <div class="category__track">
            <div class="category__fill" :style="{ width: category.width }" />
          </div>
        </div>
        <span class="category__value mono">{{ category.value }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.trends {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  border-top: 1px solid var(--color-line);
}

.trends__weeks {
  padding: 1.625rem 2.25rem 2rem 0;
  border-right: 1px solid var(--color-line);
}

.trends__categories {
  padding: 1.625rem 0 2rem 2rem;
}

.bars {
  display: grid;
  grid-template-columns: repeat(var(--columns), minmax(0, 1fr));
  align-items: end;
  gap: 0.875rem;
  height: 148px;
  margin-top: 1.375rem;
}

.bars__col {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 0.375rem;
  height: 100%;
}

.bars__value {
  color: var(--color-ink-4);
}

.bars__axis {
  display: grid;
  grid-template-columns: repeat(var(--columns), minmax(0, 1fr));
  gap: 0.875rem;
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--color-line);
}

.trends__empty {
  padding: 1.5rem 0;
}

.category {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 34px;
  align-items: center;
  gap: 0.75rem;
  padding: 0.4375rem 0;
}

.category__label {
  font-size: var(--font-size-md);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.category__track {
  margin-top: 0.3125rem;
  height: 3px;
  background: var(--color-line-soft);
}

.category__fill {
  height: 3px;
  background: var(--color-accent);
}

.category__value {
  text-align: right;
  color: var(--color-ink-4);
}

@media (max-width: 1000px) {
  .trends {
    grid-template-columns: minmax(0, 1fr);
  }

  .trends__weeks {
    padding-right: 0;
    border-right: 0;
    border-bottom: 1px solid var(--color-line);
  }

  .trends__categories {
    padding-left: 0;
  }
}
</style>
