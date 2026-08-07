<script setup lang="ts">
import AppTopBar from "./components/dashboard/AppTopBar.vue";
import DocumentOverviewPanel from "./components/DocumentOverviewPanel.vue";
import ChartModal from "./components/ChartModal.vue";
import ChatDrawer from "./components/ChatDrawer.vue";
</script>

<template>
  <div class="app-shell">
    <AppTopBar />

    <main>
      <RouterView />
    </main>

    <DocumentOverviewPanel />
    <ChartModal />
    <ChatDrawer />
  </div>
</template>

<style scoped>
/* Kein innerer Scrollcontainer mehr: die Seite selbst scrollt. Der Assistent
   steht daneben fest verankert, und ein eigener Scrollbereich darunter hätte
   zwei Bildlaufleisten nebeneinander ergeben. */
.app-shell {
  min-height: 100dvh;
}
</style>
