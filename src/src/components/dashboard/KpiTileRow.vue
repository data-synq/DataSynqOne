<script setup lang="ts">
import { computed } from "vue";
import type { DashboardKpis } from "../../api/client";
import { STATUS_COLORS } from "../../theme/statusColors";
import { useDashboardStore } from "../../stores/dashboard";

const props = defineProps<{ kpis: DashboardKpis }>();
const store = useDashboardStore();

interface Tile {
  label: string;
  value: number;
  /** Der Status, auf den ein Klick die Vorgangsliste einschränkt. Null: die Kachel filtert nicht. */
  status: string | null;
  note: string;
  /** Nur wo die Zahl selbst ein Signal ist. Sonst bleibt sie in Tinte. */
  color?: string;
  noteColor?: string;
}

const tiles = computed<Tile[]>(() => {
  const k = props.kpis;
  return [
    {
      label: "Offen",
      value: k.open,
      status: "open",
      note: k.open_new_7d ? `+${k.open_new_7d} diese Woche` : "keine neuen diese Woche",
    },
    {
      label: "Dringend",
      value: k.urgent,
      status: "urgent",
      color: STATUS_COLORS.urgent,
      note: k.urgent_new_today
        ? `${k.urgent_new_today} heute hinzugekommen`
        : "nichts heute hinzugekommen",
    },
    {
      label: "Überfällig",
      value: k.overdue,
      status: "overdue",
      color: STATUS_COLORS.overdue,
      note: k.overdue_oldest_days ? `älteste ${k.overdue_oldest_days} Tage` : "keine offene Frist",
      noteColor: k.overdue ? STATUS_COLORS.overdue : undefined,
    },
    { label: "Ohne Tag", value: k.untagged, status: null, note: "zu klassifizieren" },
    {
      label: "Neu (7 Tage)",
      value: k.recent_7d,
      status: null,
      note: `${k.recent_7d_tagged} verschlagwortet`,
    },
  ];
});

// "Ohne Tag" und "Neu" sind keine Zustände der Vorgangsliste, sie können sie
// also nicht einschränken — ein Klick hebt dort nur den Statusfokus auf. Die
// Objektwahl bleibt: sie stammt aus einer anderen Zeile und wurde nicht
// angefasst.
function activate(tile: Tile) {
  store.focusStatus(tile.status);
}

// Ist ein Status im Fokus, treten die übrigen Kacheln zurück statt zu
// verschwinden — die Zahlen bleiben ablesbar, nur nicht mehr im Vordergrund.
function opacity(tile: Tile): number {
  if (store.focusedStatus === null) return 1;
  return tile.status === store.focusedStatus ? 1 : 0.35;
}
</script>

<template>
  <section class="kpis">
    <button
      v-for="tile in tiles"
      :key="tile.label"
      type="button"
      class="kpi"
      :style="{ opacity: opacity(tile) }"
      :aria-pressed="tile.status ? store.focusedStatus === tile.status : undefined"
      @click="activate(tile)"
    >
      <span class="kpi__label">{{ tile.label }}</span>
      <span class="kpi__value" :style="tile.color ? { color: tile.color } : {}">{{ tile.value }}</span>
      <span class="kpi__note mono" :style="tile.noteColor ? { color: tile.noteColor } : {}">
        {{ tile.note }}
      </span>
    </button>
  </section>
</template>

<style scoped>
.kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  border-bottom: 1px solid var(--color-line);
}

/* Getrennt wird durch Haarlinien, nicht durch Abstand oder Kästen. Erste und
   letzte Kachel verzichten außen auf Polsterung, damit die Zahlen bündig mit
   dem Raster darunter stehen. */
.kpi {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
  padding: 1.625rem 1.5rem 1.5rem;
  border: 0;
  border-left: 1px solid var(--color-line);
  background: transparent;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: opacity var(--duration-fast) ease;
}

.kpi__label {
  font-size: var(--font-size-xs);
  font-weight: 500;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--color-ink-4);
}

.kpi__value {
  font-size: var(--font-size-display);
  font-weight: 300;
  line-height: var(--line-height-tight);
  letter-spacing: -0.02em;
  color: var(--color-ink);
  font-variant-numeric: tabular-nums;
}

.kpi__note {
  margin-top: 0.125rem;
}

/* Die Randregeln hängen an der Spaltenzahl: "erste in der Zeile" ist bei drei
   Spalten eine andere Kachel als bei fünf. Die Bereiche überschneiden sich
   deshalb nicht — genau ein Block gilt, und keiner muss den vorigen
   zurücknehmen. */
@media (min-width: 1101px) {
  .kpi:nth-child(5n + 1) {
    padding-left: 0;
    border-left: 0;
  }

  .kpi:nth-child(5n) {
    padding-right: 0;
  }
}

@media (min-width: 641px) and (max-width: 1100px) {
  .kpis {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .kpi:nth-child(3n + 1) {
    padding-left: 0;
    border-left: 0;
  }

  .kpi:nth-child(3n) {
    padding-right: 0;
  }

  .kpi:nth-child(-n + 3) {
    border-bottom: 1px solid var(--color-line);
  }
}

@media (max-width: 640px) {
  .kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .kpi {
    padding: 1.25rem 1rem;
  }

  .kpi:nth-child(2n + 1) {
    padding-left: 0;
    border-left: 0;
  }

  .kpi:nth-child(2n) {
    padding-right: 0;
  }

  .kpi:nth-child(-n + 4) {
    border-bottom: 1px solid var(--color-line);
  }
}
</style>
