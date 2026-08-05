<script setup lang="ts">
import { ref, watch } from "vue";
import IconTool from "./icons/IconTool.vue";

const props = defineProps<{
  toolCalls: { id: string; name: string; arguments: Record<string, unknown>; result?: unknown }[];
  streaming: boolean;
}>();

const open = ref(props.streaming);

watch(
  () => props.streaming,
  (streaming) => {
    if (!streaming) open.value = false;
  },
);

function formatArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
}
</script>

<template>
  <details v-if="toolCalls.length" class="tool-trace" :open="open" @toggle="open = ($event.target as HTMLDetailsElement).open">
    <summary class="tool-trace__summary">
      <IconTool /> {{ toolCalls.length }} Tool-Aufruf{{ toolCalls.length === 1 ? "" : "e" }}
      <span class="tool-trace__names">({{ toolCalls.map((c) => c.name).join(", ") }})</span>
    </summary>
    <ul class="tool-trace__list">
      <li v-for="call in toolCalls" :key="call.id" class="tool-trace__item">
        <div class="tool-trace__row">
          <span class="tool-trace__name">{{ call.name }}</span>
          <span class="tool-trace__args">({{ formatArgs(call.arguments) }})</span>
          <span v-if="call.result === undefined" class="tool-trace__status">läuft…</span>
          <span v-else class="tool-trace__status tool-trace__status--done">fertig</span>
        </div>
        <details v-if="call.result !== undefined" class="tool-trace__result">
          <summary>Ergebnis anzeigen</summary>
          <pre>{{ JSON.stringify(call.result, null, 2) }}</pre>
        </details>
      </li>
    </ul>
  </details>
</template>

<style scoped>
.tool-trace {
  margin-bottom: 0.4rem;
  padding: 0.6rem 0.8rem;
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted);
  box-shadow: var(--shadow-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.tool-trace__summary {
  cursor: pointer;
  color: var(--color-brand-blue-dark);
  font-weight: 500;
  list-style: none;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.tool-trace__summary::-webkit-details-marker {
  display: none;
}

.tool-trace__names {
  color: var(--color-text-muted);
  font-weight: 400;
}

.tool-trace__list {
  list-style: none;
  margin: 0.3rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.tool-trace__item {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.tool-trace__row {
  display: flex;
  align-items: baseline;
  gap: 0.35rem;
}

.tool-trace__name {
  color: var(--color-brand-blue-dark);
  font-weight: 500;
}

.tool-trace__status--done {
  color: var(--color-success);
}

.tool-trace__result {
  margin-left: 0.2rem;
}

.tool-trace__result summary {
  cursor: pointer;
  color: var(--color-text-muted);
  list-style: none;
}

.tool-trace__result summary::-webkit-details-marker {
  display: none;
}

.tool-trace__result pre {
  margin: 0.2rem 0 0;
  padding: 0.6rem;
  background: var(--color-white);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
