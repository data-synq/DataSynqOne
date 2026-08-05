<script setup lang="ts">
import { useChatStore } from "../stores/chat";
import IconChat from "./icons/IconChat.vue";

const store = useChatStore();
</script>

<template>
  <button
    v-if="!store.chatOpen"
    type="button"
    class="chat-fab"
    aria-label="Chat öffnen"
    @click="store.openChat()"
  >
    <IconChat />
  </button>
</template>

<style scoped>
.chat-fab {
  position: fixed;
  right: var(--space-3);
  bottom: var(--space-3);
  width: 56px;
  height: 56px;
  border-radius: var(--radius-pill);
  border: none;
  background: var(--color-brand-gold-dark);
  color: var(--color-white);
  font-size: 1.4rem;
  box-shadow: var(--shadow-md);
  cursor: pointer;
  z-index: 20;
  transition: transform var(--duration-fast) var(--ease-standard);
}

.chat-fab:hover {
  transform: scale(1.05);
}
</style>
