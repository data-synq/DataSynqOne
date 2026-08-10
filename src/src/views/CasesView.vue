<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { api, ApiError, type CaseSummary } from "../api/client";
import { STALE_CASE_DAYS, daysSince, formatDateTime, isSameDay } from "../utils/dates";
import CasesOverviewHeader, { type CasesQuickFilter } from "../components/CasesOverviewHeader.vue";

const auth = useAuthStore();

const cases = ref<CaseSummary[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const tab = ref<"open" | "closed">("open");
const quickFilter = ref<CasesQuickFilter>(null);

const searchQuery = ref("");
const objectFilter = ref("");
type TimeRange = "7" | "30" | "90" | "all";
const timeRange = ref<TimeRange>("all");

const TIME_PRESETS: { value: TimeRange; label: string }[] = [
  { value: "7", label: "7 Tage" },
  { value: "30", label: "30 Tage" },
  { value: "90", label: "90 Tage" },
  { value: "all", label: "Alle" },
];

const distinctObjects = computed(() => {
  const set = new Set<string>();
  for (const c of cases.value) if (c.object_code) set.add(c.object_code);
  return Array.from(set).sort();
});

const visible = computed(() => {
  let result = cases.value.filter((c) => c.status === tab.value);

  const term = searchQuery.value.trim().toLowerCase();
  if (term) {
    result = result.filter(
      (c) =>
        c.tracking_id.toLowerCase().includes(term) ||
        c.title.toLowerCase().includes(term) ||
        (c.sender_email ?? "").toLowerCase().includes(term),
    );
  }
  if (objectFilter.value) {
    result = result.filter((c) => c.object_code === objectFilter.value);
  }
  if (timeRange.value !== "all") {
    const cutoff = Date.now() - Number(timeRange.value) * 86_400_000;
    result = result.filter((c) => new Date(c.created_at).getTime() >= cutoff);
  }
  if (quickFilter.value === "today") {
    result = result.filter((c) => isSameDay(c.created_at));
  } else if (quickFilter.value === "stale") {
    result = result.filter((c) => c.status === "open" && daysSince(c.created_at) > STALE_CASE_DAYS);
  }
  return result;
});

const openCount = computed(() => cases.value.filter((c) => c.status === "open").length);

function onQuickFilterSelect(key: CasesQuickFilter) {
  quickFilter.value = key;
}

async function load() {
  loading.value = true;
  try {
    cases.value = await api.listCases();
    error.value = null;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Die Anliegenliste konnte nicht geladen werden.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="container cases">
    <div class="section-head">
      <h2>Anliegen</h2>
      <div class="head-actions">
        <RouterLink to="/anliegen/graph" class="link-action">Abhängigkeitsgraph</RouterLink>
        <RouterLink v-if="auth.can('mail:manage')" to="/admin/mail-freigaben" class="link-action">
          Absender-Freigaben
        </RouterLink>
        <RouterLink to="/" class="link-action">Zurück zum Dashboard</RouterLink>
      </div>
    </div>

    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>

    <CasesOverviewHeader v-if="cases.length" :cases="cases" :active-filter="quickFilter" @select="onQuickFilterSelect" />

    <div class="filters">
      <input
        v-model="searchQuery"
        type="search"
        class="filters__search"
        placeholder="Suche (Tracking-ID, Titel, Absender) …"
        autocomplete="off"
      />

      <div class="filters__group">
        <span class="filters__label mono">Zeitraum</span>
        <button
          v-for="preset in TIME_PRESETS"
          :key="preset.value"
          type="button"
          class="filters__chip"
          :class="{ 'is-active': timeRange === preset.value }"
          @click="timeRange = preset.value"
        >
          {{ preset.label }}
        </button>
      </div>

      <div class="filters__group">
        <label class="filters__label mono" for="cases-object-filter">Objekt</label>
        <select id="cases-object-filter" v-model="objectFilter">
          <option value="">Alle Objekte</option>
          <option v-for="code in distinctObjects" :key="code" :value="code">{{ code }}</option>
        </select>
      </div>
    </div>

    <div class="tabs">
      <button
        type="button"
        class="tabs__item"
        :class="{ 'is-active': tab === 'open' }"
        @click="tab = 'open'"
      >
        Offen<span v-if="openCount" class="badge mono">{{ openCount }}</span>
      </button>
      <button
        type="button"
        class="tabs__item"
        :class="{ 'is-active': tab === 'closed' }"
        @click="tab = 'closed'"
      >
        Geschlossen
      </button>
    </div>

    <p v-if="loading" class="mono cases__state">Wird geladen …</p>

    <table v-else class="table">
      <thead>
        <tr>
          <th>Tracking-ID</th>
          <th>Titel</th>
          <th>Absender</th>
          <th>Objekt</th>
          <th>Angelegt</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!visible.length">
          <td colspan="5" class="mono cases__empty">Keine Anliegen.</td>
        </tr>
        <RouterLink
          v-for="item in visible"
          :key="item.id"
          :to="`/anliegen/${item.tracking_id}`"
          custom
          v-slot="{ navigate }"
        >
          <tr class="row-link" @click="navigate">
            <td class="mono">{{ item.tracking_id }}</td>
            <td>{{ item.title }}</td>
            <td class="mono">{{ item.sender_email ?? "—" }}</td>
            <td class="mono">{{ item.object_code ?? "—" }}</td>
            <td class="mono">{{ formatDateTime(item.created_at) }}</td>
          </tr>
        </RouterLink>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.cases {
  padding-block: var(--space-4) var(--space-5);
}

.cases__state,
.cases__empty {
  padding-block: var(--space-3);
  color: var(--color-ink-4);
}

.head-actions {
  display: flex;
  gap: var(--space-2);
}

.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.filters__search {
  height: 30px;
  width: clamp(220px, 30vw, 360px);
  font-size: var(--font-size-md);
}

.filters__group {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.filters__label {
  margin-right: 0.25rem;
  font-size: var(--font-size-2xs);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-ink-5);
}

.filters__chip {
  padding: 0.3rem 0.6rem;
  border: 1px solid var(--color-line-strong);
  background: var(--color-white);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.filters__chip.is-active {
  background: var(--color-ink);
  border-color: var(--color-ink);
  color: var(--color-white);
}

.filters__group select {
  height: 28px;
  font-size: var(--font-size-sm);
}

.tabs {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  border-bottom: 1px solid var(--color-line);
}

.tabs__item {
  padding: 0.5rem 0.125rem;
  border-bottom: 2px solid transparent;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  letter-spacing: 0.04em;
  color: var(--color-ink-4);
}

.tabs__item.is-active {
  border-bottom-color: var(--color-accent);
  color: var(--color-text);
}

.badge {
  margin-left: 0.4rem;
  padding: 0.05rem 0.3rem;
  border: 1px solid var(--color-line-strong);
  color: var(--color-ink-4);
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-md);
}

.table th {
  padding: 0.5rem 0.75rem 0.5rem 0;
  border-bottom: 1px solid var(--color-line-strong);
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  font-weight: 400;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-align: left;
  color: var(--color-ink-4);
}

.table td {
  padding: 0.5rem 0.75rem 0.5rem 0;
  border-bottom: 1px solid var(--color-line-soft);
  vertical-align: baseline;
}

.table tr.row-link {
  cursor: pointer;
}

.notice {
  margin-bottom: var(--space-2);
  padding: 0.625rem 0.75rem;
  border-left: 2px solid var(--color-error);
  background: var(--color-surface-muted);
  font-size: var(--font-size-md);
  color: var(--color-error);
}
</style>
