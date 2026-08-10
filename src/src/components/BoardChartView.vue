<script setup lang="ts">
import { computed } from "vue";
import { Chart, registerables } from "chart.js";
import { Bar, Line, Pie, Doughnut } from "vue-chartjs";
import type { ChartSpec } from "../api/client";
import { PALETTE } from "../theme/chartPalette";

Chart.register(...registerables);

const props = defineProps<{ spec: ChartSpec }>();

const isRound = computed(() => props.spec.chart_type === "pie" || props.spec.chart_type === "doughnut");

const chartComponent = computed(
  () => ({ bar: Bar, line: Line, pie: Pie, doughnut: Doughnut })[props.spec.chart_type],
);

const chartData = computed(() => ({
  labels: props.spec.labels,
  datasets: props.spec.datasets.map((ds, i) => ({
    label: ds.label,
    data: ds.data,
    backgroundColor: PALETTE[i % PALETTE.length],
    borderColor: PALETTE[i % PALETTE.length],
  })),
}));

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  scales: isRound.value
    ? undefined
    : {
        x: { title: { display: !!props.spec.x_label, text: props.spec.x_label } },
        y: { title: { display: !!props.spec.y_label, text: props.spec.y_label } },
      },
}));
</script>

<template>
  <div :class="['chart-wrap', { 'chart-wrap--round': isRound }]">
    <component :is="chartComponent" :data="chartData" :options="chartOptions" />
  </div>
</template>

<style scoped>
.chart-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  padding: 1.25rem;
  box-sizing: border-box;
}

.chart-wrap--round {
  max-width: 480px;
  margin-inline: auto;
}
</style>
