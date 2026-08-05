<script setup lang="ts">
import { computed, ref } from "vue";
import type { DocSummary } from "../../api/client";
import DocumentCard from "./DocumentCard.vue";

const props = defineProps<{ recent: DocSummary[] }>();
const filter = ref<string | null>(null);

const correspondents = computed(() => {
  const names = new Set<string>();
  for (const d of props.recent) if (d.correspondent_name) names.add(d.correspondent_name);
  return Array.from(names).sort();
});

const filtered = computed(() =>
  filter.value ? props.recent.filter((d) => d.correspondent_name === filter.value) : props.recent,
);
</script>

<template>
  <section class="feed">
    <div class="feed__head">
      <h3 class="feed__title">Aktuelle Korrespondenz</h3>
      <select v-model="filter" class="feed__filter">
        <option :value="null">Alle Korrespondenten</option>
        <option v-for="name in correspondents" :key="name" :value="name">{{ name }}</option>
      </select>
    </div>
    <div class="feed__list">
      <DocumentCard v-for="doc in filtered" :key="doc.id" :doc="doc" />
    </div>
  </section>
</template>

<style scoped>
.feed {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.feed__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.feed__title {
  margin: 0;
  font-family: var(--font-display);
  color: var(--color-heading-strong);
}

.feed__filter {
  border-radius: var(--radius-pill);
  border: 1px solid var(--color-border);
  padding: 0.3rem 0.8rem;
  font-size: var(--font-size-xs);
  background: var(--color-white);
}

.feed__list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-2);
}
</style>
