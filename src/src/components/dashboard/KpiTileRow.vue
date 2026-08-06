<script setup lang="ts">
import { STATUS_COLORS } from "../../theme/statusColors";

const props = defineProps<{ kpis: Record<string, number> }>();
const emit = defineEmits<{ focus: [status: string | null] }>();

const tiles = [
  { key: "open", label: "Offen", status: "open" },
  { key: "urgent", label: "Dringend", status: "urgent" },
  { key: "overdue", label: "Überfällig", status: "overdue" },
  { key: "untagged", label: "Ohne Tag", status: null },
  { key: "recent_7d", label: "Neu (7 Tage)", status: null },
];
</script>

<template>
  <div class="kpi-row">
    <button
      v-for="tile in tiles"
      :key="tile.key"
      type="button"
      class="kpi-tile"
      :style="tile.status ? { '--accent': STATUS_COLORS[tile.status] } : {}"
      @click="emit('focus', tile.status)"
    >
      <span class="kpi-tile__label">{{ tile.label }}</span>
      <span class="kpi-tile__value">{{ props.kpis[tile.key] ?? 0 }}</span>
    </button>
  </div>
</template>

<style scoped>
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-2);
}

.kpi-tile {
  text-align: left;
  cursor: pointer;
  background: var(--surface-glass);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--accent, var(--color-border));
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  padding: var(--space-1) var(--space-2);
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  transition: box-shadow var(--duration-fast) var(--ease-standard);
  font: inherit;
}

.kpi-tile:hover {
  box-shadow: var(--shadow-md);
}

.kpi-tile__label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.kpi-tile__value {
  font-size: var(--font-size-2xl);
  font-family: var(--font-display);
  font-weight: 700;
  color: var(--color-heading-strong);
}
</style>
