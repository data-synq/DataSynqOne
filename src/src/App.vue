<script setup lang="ts">
import AppTopBar from "./components/dashboard/AppTopBar.vue";
import DocumentOverviewPanel from "./components/DocumentOverviewPanel.vue";
import AgentFocusView from "./components/AgentFocusView.vue";
import CasePopup from "./components/CasePopup.vue";
import { useAuthStore } from "./stores/auth";
import { useChatStore } from "./stores/chat";

// Die Anmeldeseite steht für sich: ohne Kopfzeile, ohne Assistenten, ohne
// Dokumentpanel — nichts davon hat ohne angemeldeten Benutzer eine Bedeutung.
const auth = useAuthStore();
const chat = useChatStore();
</script>

<template>
  <div class="app-shell">
    <AppTopBar v-if="auth.isAuthenticated && !chat.focusMode" />

    <!-- v-show statt v-if: die Seite darunter bleibt im Fokusmodus unsichtbar
         (nicht nur vom opaken Overlay verdeckt), behält dabei aber ihren
         Zustand — Scrollposition, offene Filter etc. — bis man zurückkehrt. -->
    <main v-show="!chat.focusMode">
      <RouterView />
    </main>

    <template v-if="auth.isAuthenticated">
      <DocumentOverviewPanel />
      <AgentFocusView />
      <CasePopup />
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
