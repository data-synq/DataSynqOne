<script setup lang="ts">
import { computed } from "vue";
import { Chart, registerables } from "chart.js";
import { Bar, Line, Pie, Doughnut } from "vue-chartjs";
import { useChatStore } from "../stores/chat";
import { PALETTE } from "../theme/chartPalette";

Chart.register(...registerables);

const store = useChatStore();

const isRound = computed(
  () => store.activeChart?.chart_type === "pie" || store.activeChart?.chart_type === "doughnut",
);

const chartComponent = computed(() => {
  if (!store.activeChart) return null;
  return { bar: Bar, line: Line, pie: Pie, doughnut: Doughnut }[store.activeChart.chart_type];
});

const chartData = computed(() => {
  if (!store.activeChart) return null;
  const chart = store.activeChart;
  return {
    labels: chart.labels,
    datasets: chart.datasets.map((ds, i) => ({
      label: ds.label,
      data: ds.data,
      backgroundColor: PALETTE[i % PALETTE.length],
      borderColor: PALETTE[i % PALETTE.length],
    })),
  };
});

const chartOptions = computed(() => {
  if (!store.activeChart) return {};
  const chart = store.activeChart;
  return {
    responsive: true,
    maintainAspectRatio: false,
    scales: isRound.value
      ? undefined
      : {
          x: { title: { display: !!chart.x_label, text: chart.x_label } },
          y: { title: { display: !!chart.y_label, text: chart.y_label } },
        },
  };
});
</script>

<template>
  <div v-if="store.activeChart && chartComponent" class="chart-backdrop" @click.self="store.closeChart()">
    <div class="chart-dialog" role="dialog" aria-modal="true">
      <div class="chart-dialog__head">
        <h2>{{ store.activeChart.title }}</h2>
        <button type="button" class="link-action" @click="store.closeChart()">Schließen</button>
      </div>
      <div :class="['chart-wrap', { 'chart-wrap--round': isRound }]">
        <component :is="chartComponent" :data="chartData!" :options="chartOptions" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.chart-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(22, 24, 20, 0.32);
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  box-sizing: border-box;
}

.chart-dialog {
  width: min(640px, 92vw);
  max-height: 80vh;
  background: var(--color-white);
  border: 1px solid var(--color-line-strong);
  padding: var(--space-3);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.chart-dialog__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--color-ink);
}

.chart-dialog__head h2 {
  margin: 0;
}

.chart-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  max-height: 65vh;
}

.chart-wrap--round {
  aspect-ratio: 1;
  max-width: 420px;
  margin-inline: auto;
}
</style>
