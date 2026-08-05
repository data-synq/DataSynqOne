<script setup lang="ts">
import { computed } from "vue";
import { Chart, registerables } from "chart.js";
import { Line, Doughnut } from "vue-chartjs";
import type { ChartBucket } from "../../api/client";
import { PALETTE } from "../../theme/chartPalette";

Chart.register(...registerables);

const props = defineProps<{
  title: string;
  type: "line" | "doughnut";
  bucket: ChartBucket;
  colors?: string[];
}>();

const chartComponent = computed(() => (props.type === "line" ? Line : Doughnut));

const chartData = computed(() => {
  const colors = props.colors ?? props.bucket.labels.map((_, i) => PALETTE[i % PALETTE.length]);
  return {
    labels: props.bucket.labels,
    datasets: [
      {
        label: props.title,
        data: props.bucket.data,
        backgroundColor: props.type === "line" ? colors[0] : colors,
        borderColor: colors[0],
        fill: props.type === "line",
      },
    ],
  };
});

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: props.type === "doughnut" } },
  scales: props.type === "line" ? { y: { beginAtZero: true, ticks: { precision: 0 } } } : undefined,
}));
</script>

<template>
  <div class="chart-card">
    <h3 class="chart-card__title">{{ title }}</h3>
    <div :class="['chart-card__wrap', { 'chart-card__wrap--round': type === 'doughnut' }]">
      <component :is="chartComponent" :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>

<style scoped>
.chart-card {
  background: var(--surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  padding: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.chart-card__title {
  margin: 0;
  font-family: var(--font-display);
  color: var(--color-heading-strong);
  font-size: var(--font-size-sm);
}

.chart-card__wrap {
  position: relative;
  height: 200px;
}

.chart-card__wrap--round {
  max-width: 200px;
  margin-inline: auto;
}
</style>
