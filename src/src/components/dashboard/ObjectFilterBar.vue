<script setup lang="ts">
import { useDashboardStore } from "../../stores/dashboard";

defineProps<{ objects: string[] }>();
const store = useDashboardStore();
</script>

<template>
  <!-- Ohne gepflegte `obj:`-Tags in Paperless gibt es nichts zu filtern. Dann
       ist die leere Zeile ehrlicher als ein einzelner Chip "Alle Objekte",
       der nach einer Wahl aussieht, die es nicht gibt. -->
  <div v-if="objects.length" class="objects">
    <span class="objects__label">Objekt</span>
    <button
      type="button"
      class="objects__chip"
      :class="{ 'objects__chip--active': store.selectedObject === null }"
      @click="store.selectObject(null)"
    >
      Alle Objekte
    </button>
    <button
      v-for="name in objects"
      :key="name"
      type="button"
      class="objects__chip"
      :class="{ 'objects__chip--active': store.selectedObject === name }"
      @click="store.selectObject(name)"
    >
      {{ name }}
    </button>
  </div>
</template>

<style scoped>
.objects {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.25rem;
  border-top: 1px solid var(--color-line);
  border-bottom: 1px solid var(--color-line);
}

.objects__label {
  padding: 0.625rem 0.875rem 0.625rem 0;
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-ink-5);
}

/* Die Auswahl trägt eine Unterstreichung, keine Fläche: ein gefüllter Chip
   wöge hier so viel wie eine Kennzahl darunter. */
.objects__chip {
  border: 0;
  background: transparent;
  padding: 0.625rem 0.75rem;
  font: inherit;
  font-size: var(--font-size-md);
  white-space: nowrap;
  color: var(--color-ink-4);
  cursor: pointer;
  box-shadow: none;
  transition: color var(--duration-fast) var(--ease-standard);
}

.objects__chip:hover {
  color: var(--color-ink);
}

.objects__chip--active {
  color: var(--color-ink);
  box-shadow: inset 0 -2px 0 var(--color-ink);
}
</style>
