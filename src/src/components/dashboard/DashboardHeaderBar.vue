<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";

const props = defineProps<{ generatedAt: string | null }>();

const tick = ref(0);
let timer: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  timer = setInterval(() => tick.value++, 1000);
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
});

const relativeLabel = ref("");

function computeLabel() {
  if (!props.generatedAt) {
    relativeLabel.value = "";
    return;
  }
  const seconds = Math.max(0, Math.round((Date.now() - new Date(props.generatedAt).getTime()) / 1000));
  if (seconds < 5) relativeLabel.value = "gerade eben aktualisiert";
  else if (seconds < 60) relativeLabel.value = `aktualisiert vor ${seconds}s`;
  else relativeLabel.value = `aktualisiert vor ${Math.round(seconds / 60)} Min.`;
}

watch([tick, () => props.generatedAt], computeLabel, { immediate: true });
</script>

<template>
  <div class="header-bar">
    <div>
      <h1 class="header-bar__title">Dashboard</h1>
      <p class="header-bar__meta">{{ relativeLabel }}</p>
    </div>
    <span class="live-indicator">
      <span class="live-indicator__dot" />
      Live
    </span>
  </div>
</template>

<style scoped>
.header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.header-bar__title {
  margin: 0;
  font-family: var(--font-display);
  color: var(--color-heading-strong);
}

.header-bar__meta {
  margin: 0.2rem 0 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.live-indicator {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.8rem;
  border-radius: var(--radius-pill);
  background: var(--color-white);
  border: 1px solid var(--color-border);
  color: var(--color-success);
  font-size: var(--font-size-xs);
  font-family: var(--font-display);
  font-weight: 600;
}

.live-indicator__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-success);
  animation: pulse 1.8s var(--ease-standard) infinite;
}

@keyframes pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(82, 118, 97, 0.45);
  }
  50% {
    box-shadow: 0 0 0 5px rgba(82, 118, 97, 0);
  }
}
</style>
