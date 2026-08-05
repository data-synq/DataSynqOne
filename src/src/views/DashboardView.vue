<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";
import { useDashboardStore } from "../stores/dashboard";
import DashboardHeaderBar from "../components/dashboard/DashboardHeaderBar.vue";
import KpiTileRow from "../components/dashboard/KpiTileRow.vue";
import DeadlinesPanel from "../components/dashboard/DeadlinesPanel.vue";
import StatusQueueBoard from "../components/dashboard/StatusQueueBoard.vue";
import ChartsRow from "../components/dashboard/ChartsRow.vue";
import RecentCorrespondenceFeed from "../components/dashboard/RecentCorrespondenceFeed.vue";

const store = useDashboardStore();

onMounted(() => {
  store.load();
  store.startPolling();
});
onUnmounted(() => store.stopPolling());

const overview = computed(() => store.overview);
</script>

<template>
  <div class="dashboard">
    <DashboardHeaderBar :generated-at="overview?.generated_at ?? null" />

    <p v-if="store.error" class="dashboard__error">{{ store.error }}</p>
    <p v-else-if="!overview && store.loading" class="dashboard__status">Lade Dashboard...</p>

    <template v-if="overview">
      <KpiTileRow :kpis="overview.kpis" @focus="store.focusStatus" />

      <div class="dashboard__main">
        <StatusQueueBoard
          :by-status="overview.by_status"
          :kpis="overview.kpis"
          :focused-status="store.focusedStatus"
        />
        <DeadlinesPanel :deadlines="overview.deadlines" />
      </div>

      <ChartsRow
        :documents-over-time="overview.charts.documents_over_time"
        :status-distribution="overview.charts.status_distribution"
      />

      <RecentCorrespondenceFeed :recent="overview.recent" />
    </template>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 1680px;
  margin-inline: auto;
  padding: var(--space-3) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  overflow-y: auto;
  height: 100%;
  box-sizing: border-box;
}

.dashboard__main {
  display: grid;
  grid-template-columns: minmax(0, 2.4fr) minmax(240px, 1fr);
  gap: var(--space-2);
  align-items: start;
}

.dashboard__error {
  color: var(--color-error);
}

.dashboard__status {
  color: var(--color-text-muted);
}

@media (max-width: 900px) {
  .dashboard__main {
    grid-template-columns: 1fr;
  }
}
</style>
