<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";
import { useDashboardStore } from "../stores/dashboard";
import DashboardHeadline from "../components/dashboard/DashboardHeadline.vue";
import ObjectFilterBar from "../components/dashboard/ObjectFilterBar.vue";
import KpiTileRow from "../components/dashboard/KpiTileRow.vue";
import ChatTeaserBar from "../components/dashboard/ChatTeaserBar.vue";
import NextUpQueue from "../components/dashboard/NextUpQueue.vue";
import DeadlinesPanel from "../components/dashboard/DeadlinesPanel.vue";
import TrendsSection from "../components/dashboard/TrendsSection.vue";
import RecentCorrespondenceFeed from "../components/dashboard/RecentCorrespondenceFeed.vue";

const store = useDashboardStore();

onMounted(() => {
  store.load();
  store.startPolling();
});
onUnmounted(() => store.stopPolling());

const overview = computed(() => store.overview);

// Der Nenner in "N von M Vorgängen": alles Offene, ungefiltert.
const totalOpen = computed(() => {
  const k = overview.value?.kpis;
  return k ? k.open + k.urgent + k.overdue : 0;
});

const emptyBucket = { labels: [], data: [] };
</script>

<template>
  <div class="dashboard">
    <p v-if="store.error" class="dashboard__error">{{ store.error }}</p>
    <p v-else-if="!overview && store.loading" class="dashboard__status mono">Lade Dashboard …</p>

    <template v-if="overview">
      <!-- Ungefiltert: der Lagesatz beschreibt den Tag, nicht die gerade
           eingestellte Ansicht. Die Kennzahlen daneben sind ebenfalls
           Gesamtzahlen — beide Hälften des Satzes müssen sich auf dasselbe
           beziehen. -->
      <DashboardHeadline
        :kpis="overview.kpis"
        :deadlines="overview.deadlines"
        :object-count="overview.objects.length"
        :generated-at="overview.generated_at"
      />

      <ObjectFilterBar :objects="overview.objects" />

      <KpiTileRow :kpis="overview.kpis" />

      <ChatTeaserBar />

      <div class="dashboard__split">
        <NextUpQueue :queue="store.filteredQueue" :total-open="totalOpen" />
        <DeadlinesPanel :deadlines="store.filteredDeadlines" />
      </div>

      <TrendsSection
        :per-week="overview.charts.documents_per_week ?? emptyBucket"
        :categories="overview.charts.category_distribution ?? emptyBucket"
      />

      <RecentCorrespondenceFeed :recent="store.filteredRecent" :total="overview.kpis.total" />
    </template>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: var(--content-width);
  margin-inline: auto;
  padding: 0 var(--page-padding) 4.5rem;
}

/* Die Trennlinie zwischen Vorgängen und Fristen ist dieselbe Linie, die
   darunter die Trends teilt — beide Raster stehen auf derselben Achse. */
.dashboard__split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
}

.dashboard__split > :first-child {
  padding: 1.625rem 2.25rem 2rem 0;
  border-right: 1px solid var(--color-line);
}

.dashboard__split > :last-child {
  padding: 1.625rem 0 2rem 2rem;
}

.dashboard__error {
  padding: var(--space-3) 0;
  color: var(--color-error);
}

.dashboard__status {
  padding: var(--space-3) 0;
}

@media (max-width: 1000px) {
  .dashboard__split {
    grid-template-columns: minmax(0, 1fr);
  }

  .dashboard__split > :first-child {
    padding-right: 0;
    border-right: 0;
    border-bottom: 1px solid var(--color-line);
  }

  .dashboard__split > :last-child {
    padding-left: 0;
  }
}
</style>
