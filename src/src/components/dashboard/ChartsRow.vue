<script setup lang="ts">
import type { ChartBucket } from "../../api/client";
import { STATUS_COLORS } from "../../theme/statusColors";
import DashboardChartCard from "./DashboardChartCard.vue";

const props = defineProps<{
  documentsOverTime: ChartBucket;
  statusDistribution: ChartBucket;
}>();

// Literal, keine CSS-Variable: der Wert geht an Chart.js aufs Canvas,
// und dort wird var(...) nicht aufgelöst.
const statusColors = props.statusDistribution.labels.map((l) => STATUS_COLORS[l] ?? "#8b8f84");
</script>

<template>
  <div class="charts-row">
    <DashboardChartCard title="Dokumente über Zeit" type="line" :bucket="documentsOverTime" />
    <DashboardChartCard
      title="Status-Verteilung"
      type="doughnut"
      :bucket="statusDistribution"
      :colors="statusColors"
    />
  </div>
</template>

<style scoped>
.charts-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: var(--space-2);
}
</style>
