<script setup lang="ts">
import { reactive, ref, watch } from "vue";

const props = defineProps<{
  toolCalls: { id: string; name: string; arguments: Record<string, unknown>; result?: unknown }[];
  streaming: boolean;
}>();

// Während der Antwort offen, danach zu: solange gearbeitet wird, ist der
// Ablauf die einzige Rückmeldung; steht die Antwort da, ist er Beiwerk.
const open = ref(props.streaming);

watch(
  () => props.streaming,
  (streaming) => {
    if (!streaming) open.value = false;
  },
);

function call(name: string, args: Record<string, unknown>): string {
  const inner = Object.entries(args)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  return `${name}(${inner})`;
}

// Das rohe Ergebnis je Aufruf bleibt erreichbar. Es ist im Design nicht
// vorgesehen, aber es ist das Einzige, woran sich nachvollziehen lässt,
// worauf eine Antwort sich stützt — dafür ist die Ablaufanzeige da.
const expanded = reactive<Record<string, boolean>>({});
</script>

<template>
  <div v-if="toolCalls.length" class="trace">
    <button type="button" class="trace__toggle" :aria-expanded="open" @click="open = !open">
      {{ toolCalls.length }} Tool-Aufruf{{ toolCalls.length === 1 ? "" : "e" }} {{ open ? "▾" : "▸" }}
    </button>

    <div v-if="open" class="trace__list">
      <div v-for="c in toolCalls" :key="c.id" class="trace__entry">
        <div class="trace__row">
          <span class="trace__call">{{ call(c.name, c.arguments) }}</span>
          <button
            v-if="c.result !== undefined"
            type="button"
            class="trace__state trace__state--done"
            :aria-expanded="!!expanded[c.id]"
            @click="expanded[c.id] = !expanded[c.id]"
          >
            fertig {{ expanded[c.id] ? "▾" : "▸" }}
          </button>
          <span v-else class="trace__state">läuft</span>
        </div>
        <pre v-if="expanded[c.id]" class="trace__result">{{ JSON.stringify(c.result, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trace {
  margin-bottom: 0.75rem;
  padding: 0.5rem 0.625rem;
  background: var(--color-surface-muted);
}

.trace__toggle {
  display: block;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 0;
  font: inherit;
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  color: var(--color-ink-4);
  text-align: left;
  cursor: pointer;
}

.trace__toggle:hover {
  color: var(--color-ink);
}

.trace__list {
  display: flex;
  flex-direction: column;
  gap: 0.3125rem;
  margin-top: 0.5rem;
}

.trace__entry {
  padding-top: 0.3125rem;
  border-top: 1px solid #e2e2da;
}

.trace__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 0.625rem;
}

.trace__call {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace__state {
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  color: var(--color-ink-5);
  white-space: nowrap;
}

button.trace__state {
  border: 0;
  background: transparent;
  padding: 0;
  font: inherit;
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  cursor: pointer;
}

.trace__state--done {
  color: var(--color-accent);
}

.trace__result {
  margin: 0.3125rem 0 0;
  padding: 0.5rem 0.625rem;
  max-height: 220px;
  overflow: auto;
  background: var(--color-white);
  border: 1px solid var(--color-line-soft);
  font-family: var(--font-mono);
  font-size: var(--font-size-2xs);
  line-height: 1.5;
  color: var(--color-ink-3);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
