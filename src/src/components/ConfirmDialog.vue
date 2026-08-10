<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";

withDefaults(
  defineProps<{
    title?: string;
    message: string;
    confirmLabel?: string;
    cancelLabel?: string;
    danger?: boolean;
  }>(),
  {
    title: "Bestätigen",
    confirmLabel: "Bestätigen",
    cancelLabel: "Abbrechen",
    danger: false,
  },
);

const emit = defineEmits<{ confirm: []; cancel: [] }>();

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") emit("cancel");
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <div class="scrim" @click.self="emit('cancel')">
    <div class="confirm" role="alertdialog" aria-modal="true" :aria-label="title">
      <h3 class="confirm__title">{{ title }}</h3>
      <p class="confirm__message">{{ message }}</p>
      <div class="confirm__actions">
        <button type="button" class="link-action" @click="emit('cancel')">{{ cancelLabel }}</button>
        <button
          type="button"
          class="button--primary"
          :class="{ 'confirm__button--danger': danger }"
          @click="emit('confirm')"
        >
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scrim {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.75rem;
  background: rgba(22, 24, 20, 0.32);
}

.confirm {
  display: flex;
  flex-direction: column;
  width: min(380px, 100%);
  padding: 1.25rem 1.5rem;
  background: var(--color-white);
  border: 1px solid var(--color-line-strong);
}

.confirm__title {
  margin: 0 0 0.5rem;
  font-size: var(--font-size-md);
  font-weight: 500;
}

.confirm__message {
  margin: 0 0 1.125rem;
  color: var(--color-ink-3);
}

.confirm__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-3);
}

.confirm__button--danger {
  background: var(--color-error);
  border-color: var(--color-error);
}

.confirm__button--danger:hover:not(:disabled) {
  background: #8c3a32;
  border-color: #8c3a32;
}
</style>
