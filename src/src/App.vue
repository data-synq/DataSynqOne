<script setup lang="ts">
import DocumentOverviewPanel from "./components/DocumentOverviewPanel.vue";
import ChartModal from "./components/ChartModal.vue";
import ChatDrawer from "./components/ChatDrawer.vue";
import DashboardChatFab from "./components/DashboardChatFab.vue";
</script>

<template>
  <div class="app-shell">
    <header class="site-header">
      <span class="logo">
        <span class="logo__mark">◆</span>
        <span class="logo__text">Paperless Agent</span>
      </span>
    </header>

    <main class="app-main">
      <RouterView />
    </main>

    <DocumentOverviewPanel />
    <ChartModal />
    <ChatDrawer />
    <DashboardChatFab />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100dvh;
}

.site-header {
  flex: none;
  z-index: 10;
  display: flex;
  align-items: center;
  min-height: 56px;
  padding-inline: var(--page-padding);
  background: var(--surface-glass-strong);
  box-shadow: 0 1px 0 var(--color-border);
}

.logo {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--color-heading-strong);
  font-family: var(--font-display);
  font-weight: 700;
  letter-spacing: -0.01em;
  font-size: var(--font-size-base);
}

.logo__mark {
  color: var(--color-brand-gold-dark);
  font-size: 0.8em;
}

.app-main {
  flex: 1;
  min-height: 0;
}
</style>
