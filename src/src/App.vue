<script setup lang="ts">
import AppTopBar from "./components/dashboard/AppTopBar.vue";
import DocumentOverviewPanel from "./components/DocumentOverviewPanel.vue";
import ChartModal from "./components/ChartModal.vue";
import ChatDrawer from "./components/ChatDrawer.vue";
import { useAuthStore } from "./stores/auth";

// Die Anmeldeseite steht für sich: ohne Kopfzeile, ohne Assistenten, ohne
// Dokumentpanel — nichts davon hat ohne angemeldeten Benutzer eine Bedeutung.
const auth = useAuthStore();
</script>

<template>
  <div class="app-shell">
    <AppTopBar v-if="auth.isAuthenticated" />

    <main>
      <RouterView />
    </main>

    <template v-if="auth.isAuthenticated">
      <DocumentOverviewPanel />
      <ChartModal />
      <ChatDrawer />
    </template>
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
