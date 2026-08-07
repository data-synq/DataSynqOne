<script setup lang="ts">
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api, type PaperlessDocument } from "../../api/client";
import { useChatStore } from "../../stores/chat";
import { useDashboardStore } from "../../stores/dashboard";
import { useAuthStore } from "../../stores/auth";

const chat = useChatStore();
const dashboard = useDashboardStore();
const auth = useAuthStore();
const router = useRouter();

const accountOpen = ref(false);

async function signOut() {
  accountOpen.value = false;
  await auth.logout();
  await router.replace("/login");
}

const query = ref("");
const results = ref<PaperlessDocument[]>([]);
const searching = ref(false);
const searchError = ref<string | null>(null);
const open = ref(false);

const SEARCH_DEBOUNCE_MS = 250;
const MAX_RESULTS = 8;

let debounce: ReturnType<typeof setTimeout> | null = null;
// Tippt jemand schneller als die Antworten kommen, treffen sie in beliebiger
// Reihenfolge ein. Ohne diesen Zähler überschreibt eine langsame Antwort auf
// "Miet" die schnelle auf "Mietvertrag".
let latestRequest = 0;

watch(query, (value) => {
  if (debounce) clearTimeout(debounce);
  const term = value.trim();
  if (term.length < 2) {
    results.value = [];
    searchError.value = null;
    searching.value = false;
    open.value = false;
    return;
  }
  searching.value = true;
  open.value = true;
  debounce = setTimeout(async () => {
    const request = ++latestRequest;
    try {
      const page = await api.searchDocuments(term);
      if (request !== latestRequest) return;
      results.value = page.results.slice(0, MAX_RESULTS);
      searchError.value = null;
    } catch (e) {
      if (request !== latestRequest) return;
      results.value = [];
      searchError.value = e instanceof TypeError ? "Server nicht erreichbar." : "Suche fehlgeschlagen.";
    } finally {
      if (request === latestRequest) searching.value = false;
    }
  }, SEARCH_DEBOUNCE_MS);
});

function openResult(id: number) {
  chat.openDocument(id);
  query.value = "";
  open.value = false;
}

function reset() {
  query.value = "";
  open.value = false;
}
</script>

<template>
  <header class="topbar">
    <div class="topbar__brand">
      <span class="topbar__product">DataSynq One</span>
      <span class="topbar__divider" />
      <span class="topbar__context">Dokumentenakte</span>
    </div>

    <div class="search" @keydown.esc="reset">
      <label class="search__label" for="topbar-search">Dokumentsuche</label>
      <input
        id="topbar-search"
        v-model="query"
        type="search"
        class="search__input"
        :placeholder="
          dashboard.overview
            ? `Suche in ${dashboard.overview.kpis.total.toLocaleString('de-DE')} Dokumenten`
            : 'Suche in Dokumenten'
        "
        autocomplete="off"
        @focus="open = results.length > 0 || searching"
      />

      <div v-if="open" class="search__results">
        <p v-if="searching" class="search__note">Suche läuft …</p>
        <p v-else-if="searchError" class="search__note search__note--error">{{ searchError }}</p>
        <p v-else-if="!results.length" class="search__note">Kein Treffer.</p>
        <button
          v-for="doc in results"
          :key="doc.id"
          type="button"
          class="search__result row-link"
          @click="openResult(doc.id)"
        >
          <span class="search__result-title">{{ doc.title }}</span>
          <span class="search__result-date mono">{{ doc.created?.slice(0, 10) }}</span>
        </button>
      </div>
    </div>

    <div class="topbar__actions">
      <button type="button" class="button--primary assistant-button" @click="chat.openChat()">
        <span class="assistant-button__dot" />
        Assistent
      </button>

      <div class="account" @keydown.esc="accountOpen = false">
        <button
          type="button"
          class="account__trigger"
          :aria-expanded="accountOpen"
          aria-haspopup="menu"
          @click="accountOpen = !accountOpen"
        >
          <span class="account__name">{{ auth.user?.display_name }}</span>
          <span class="account__role mono">{{ auth.user?.role_label }}</span>
        </button>

        <!-- Ein Klick daneben schließt das Menü. Der Overlay liegt unter dem Menü,
             aber über allem anderen, damit kein Klick ins Leere geht. -->
        <div v-if="accountOpen" class="account__backdrop" @click="accountOpen = false" />

        <div v-if="accountOpen" class="account__menu" role="menu">
          <RouterLink to="/profil" class="account__item" role="menuitem" @click="accountOpen = false">
            Passwort ändern
          </RouterLink>
          <RouterLink
            v-if="auth.can('users:manage')"
            to="/admin/benutzer"
            class="account__item"
            role="menuitem"
            @click="accountOpen = false"
          >
            Benutzer verwalten
          </RouterLink>
          <button type="button" class="account__item" role="menuitem" @click="signOut">
            Abmelden
          </button>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-3);
  height: 58px;
  padding-inline: var(--page-padding);
  background: var(--color-white);
  border-bottom: 1px solid var(--color-line);
}

.topbar__brand {
  display: flex;
  align-items: baseline;
  gap: 0.625rem;
}

.topbar__product {
  font-size: var(--font-size-md);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-ink);
  white-space: nowrap;
}

.topbar__divider {
  width: 1px;
  height: 12px;
  background: var(--color-line-strong);
}

.topbar__context {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  letter-spacing: 0.04em;
  color: var(--color-ink-4);
  white-space: nowrap;
}

/* Die Suche sitzt in der mittleren Spalte und darf sie nicht sprengen —
   deshalb clamp statt einer festen Breite. */
.search {
  position: relative;
  justify-self: end;
  width: clamp(140px, 26vw, 320px);
}

.search__label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.search__input {
  height: 26px;
  font-size: var(--font-size-md);
}

.search__results {
  position: absolute;
  z-index: 30;
  top: calc(100% + 0.5rem);
  right: 0;
  left: 0;
  max-height: 60vh;
  overflow-y: auto;
  background: var(--color-white);
  border: 1px solid var(--color-line-strong);
}

.search__note {
  margin: 0;
  padding: 0.625rem 0.75rem;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-ink-5);
}

.search__note--error {
  color: var(--color-error);
}

.search__result {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 0.75rem;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border-inline: 0;
  border-top: 0;
  background: transparent;
  font: inherit;
  text-align: left;
}

.search__result:last-child {
  border-bottom: 0;
}

.search__result-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text);
}

.search__result-date {
  white-space: nowrap;
}

.assistant-button__dot {
  width: 6px;
  height: 6px;
  background: #7fbfa2;
}

.topbar__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.account {
  position: relative;
}

.account__trigger {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.1rem;
  padding: 0;
  border: 0;
  background: transparent;
  font: inherit;
  line-height: 1.2;
  text-align: right;
  cursor: pointer;
}

.account__name {
  font-size: var(--font-size-md);
  font-weight: 500;
  color: var(--color-text);
  white-space: nowrap;
}

.account__role {
  font-size: var(--font-size-2xs);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

/* Fängt den Klick neben dem Menü ab. Unsichtbar, aber über der Seite. */
.account__backdrop {
  position: fixed;
  inset: 0;
  z-index: 30;
}

.account__menu {
  position: absolute;
  z-index: 31;
  top: calc(100% + 0.75rem);
  right: 0;
  display: grid;
  min-width: 12rem;
  background: var(--color-white);
  border: 1px solid var(--color-line-strong);
}

.account__item {
  padding: 0.5rem 0.75rem;
  border: 0;
  border-bottom: 1px solid var(--color-line-soft);
  background: transparent;
  color: var(--color-text);
  font: inherit;
  font-size: var(--font-size-md);
  text-align: left;
  text-decoration: none;
  cursor: pointer;
  transition: background-color var(--duration-fast) var(--ease-standard);
}

.account__item:last-child {
  border-bottom: 0;
}

.account__item:hover {
  background: var(--color-surface-muted);
}
</style>
