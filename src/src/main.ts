import { createApp } from "vue";
import { createPinia } from "pinia";

// IBM Plex aus node_modules statt von fonts.googleapis.com. Die Design-
// Komponenten laden die Schriften vom Google-CDN; in der Anwendung wäre
// das bei jedem Aufruf eine Übertragung der Nutzer-IP an Google, was in
// einem Produkt mit Mieterdaten niemand erklären möchte. Vor style.css
// importiert, damit die @font-face-Regeln vor den Tokens stehen.
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";

import "./style.css";
import App from "./App.vue";
import { router } from "./router";
import { registerAuthInterceptor } from "./stores/auth";

const app = createApp(App);
app.use(createPinia());
// Vor app.use(router), weil der erste Navigations-Guard sofort läuft und ein 401
// aus /auth/me schon im Store landen können muss.
registerAuthInterceptor();
app.use(router);
app.mount("#app");
