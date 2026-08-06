<script setup lang="ts">
import type { DocSummary } from "../../api/client";
import { useChatStore } from "../../stores/chat";
import IconChat from "../icons/IconChat.vue";

const props = defineProps<{ doc: DocSummary }>();
const store = useChatStore();

function open() {
  store.openDocument(props.doc.id);
}

function ask(event: MouseEvent) {
  event.stopPropagation();
  store.askAboutDocument(props.doc.id, props.doc.title);
}
</script>

<template>
  <article class="doc-card" @click="open">
    <div class="doc-card__head">
      <h4 class="doc-card__title" :title="doc.title">{{ doc.title }}</h4>
      <button type="button" class="doc-card__ask" title="Im Chat nachfragen" @click="ask"><IconChat /></button>
    </div>
    <p class="doc-card__meta">
      <span v-if="doc.correspondent_name">{{ doc.correspondent_name }}</span>
      <span v-if="doc.correspondent_name"> · </span>
      <span>{{ doc.created?.slice(0, 10) }}</span>
    </p>
    <div class="doc-card__tags">
      <span v-for="tag in doc.tags" :key="tag.id" class="tag-pill" :style="{ '--tag-color': tag.color }">
        {{ tag.name }}
      </span>
    </div>
  </article>
</template>

<style scoped>
.doc-card {
  background: var(--surface-glass);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  padding: var(--space-1) var(--space-2);
  cursor: pointer;
  min-width: 0;
  transition: box-shadow var(--duration-fast) var(--ease-standard);
}

.doc-card:hover {
  box-shadow: var(--shadow-md);
}

.doc-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-1);
  min-width: 0;
}

.doc-card__title {
  margin: 0;
  min-width: 0;
  flex: 1;
  font-size: var(--font-size-sm);
  font-family: var(--font-display);
  color: var(--color-heading-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-card__ask {
  border: none;
  background: none;
  cursor: pointer;
  font-size: var(--font-size-sm);
  line-height: 1;
  padding: 0.2rem;
  flex: none;
}

.doc-card__meta {
  margin: 0.15rem 0 0.35rem;
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.tag-pill {
  border-radius: var(--radius-pill);
  padding: 0.1rem 0.6rem;
  font-size: var(--font-size-xs);
  font-family: var(--font-display);
  font-weight: 600;
  background: var(--color-white);
  color: var(--tag-color, var(--color-text-muted));
  border: 1px solid var(--tag-color, var(--color-border));
}
</style>
