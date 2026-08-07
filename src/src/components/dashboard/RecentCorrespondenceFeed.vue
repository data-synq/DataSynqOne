<script setup lang="ts">
import type { DocSummary } from "../../api/client";
import { categoryLabel, STATUS_COLORS, STATUS_LABELS } from "../../theme/statusColors";
import { useChatStore } from "../../stores/chat";
import { formatDate } from "../../utils/dates";

defineProps<{ recent: DocSummary[]; total: number }>();
const chat = useChatStore();
</script>

<template>
  <!-- Eine Tabelle statt Kacheln: acht Dokumente vergleicht man spaltenweise
       ("wer, wann, welches Objekt"), und dafür müssen die Werte untereinander
       stehen. Als Kacheln steht jedes Feld an einer anderen Stelle. -->
  <section class="feed">
    <div class="section-head">
      <h2>Aktuelle Korrespondenz</h2>
      <span class="mono">{{ total.toLocaleString("de-DE") }} Dokumente insgesamt</span>
    </div>

    <div class="feed__scroll">
      <table class="feed__table">
        <thead>
          <tr>
            <th scope="col">Datum</th>
            <th scope="col">Titel</th>
            <th scope="col">Korrespondent</th>
            <th scope="col">Objekt</th>
            <th scope="col">Kategorie</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!recent.length">
            <td colspan="6" class="feed__empty mono">Keine Dokumente.</td>
          </tr>
          <tr
            v-for="doc in recent"
            :key="doc.id"
            class="row-link"
            @click="chat.openDocument(doc.id)"
            @keydown.enter="chat.openDocument(doc.id)"
            tabindex="0"
          >
            <td class="feed__date mono">{{ formatDate(doc.created) }}</td>
            <td class="feed__title">{{ doc.title }}</td>
            <td class="feed__truncate">{{ doc.correspondent_name ?? "—" }}</td>
            <td class="feed__truncate feed__muted">{{ doc.object_name ?? "—" }}</td>
            <td class="feed__muted">{{ categoryLabel(doc.category) }}</td>
            <td>
              <span class="feed__status" :style="{ color: STATUS_COLORS[doc.status] ?? 'var(--color-ink-3)' }">
                <span class="feed__status-mark" :style="{ background: 'currentColor' }" />
                {{ STATUS_LABELS[doc.status] ?? doc.status }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.feed {
  border-top: 1px solid var(--color-line);
  padding-top: 1.625rem;
}

/* Sechs Spalten unterschreiten irgendwann die lesbare Breite. Dann scrollt
   die Tabelle in sich — die Seite selbst darf nie waagerecht scrollen. */
.feed__scroll {
  overflow-x: auto;
  margin-top: 0.875rem;
}

.feed__table {
  width: 100%;
  min-width: 900px;
  border-collapse: collapse;
  table-layout: fixed;
}

.feed__table th {
  padding: 0 0.75rem 0.4375rem 0;
  border-bottom: 1px solid var(--color-ink);
  font-size: var(--font-size-2xs);
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-ink-4);
  text-align: left;
}

.feed__table td {
  padding: 0.5625rem 0.75rem 0.625rem 0;
  vertical-align: baseline;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feed__table th:first-child,
.feed__table td:first-child {
  width: 92px;
}

.feed__table th:nth-child(3),
.feed__table td:nth-child(3) {
  width: 190px;
}

.feed__table th:nth-child(4),
.feed__table td:nth-child(4),
.feed__table th:nth-child(5),
.feed__table td:nth-child(5) {
  width: 130px;
}

.feed__table th:last-child,
.feed__table td:last-child {
  width: 110px;
}

.feed__date {
  color: var(--color-ink-4);
  white-space: nowrap;
}

.feed__title {
  color: var(--color-text);
}

.feed__truncate {
  color: var(--color-ink-3);
}

.feed__muted {
  font-size: var(--font-size-md);
  color: var(--color-ink-4);
}

.feed__empty {
  padding: 1.5rem 0;
}

.feed__status {
  display: inline-flex;
  align-items: baseline;
  gap: 0.4375rem;
  font-size: var(--font-size-md);
}

.feed__status-mark {
  width: 7px;
  height: 7px;
  position: relative;
  top: -1px;
  flex: none;
}
</style>
