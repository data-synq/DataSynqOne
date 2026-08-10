<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../../stores/auth";

const auth = useAuthStore();
const router = useRouter();

const accountOpen = ref(false);

async function signOut() {
  accountOpen.value = false;
  await auth.logout();
  await router.replace("/login");
}

// Nur eingreifen (und die Weitergabe stoppen), wenn das Menü tatsächlich
// offen ist — sonst würde ein Esc-Druck bei fokussiertem Konto-Button auch
// dann den Fokusmodus dahinter blockieren, wenn das Menü gar nicht offen ist.
function onEsc(event: KeyboardEvent) {
  if (!accountOpen.value) return;
  accountOpen.value = false;
  event.stopPropagation();
}
</script>

<template>
  <div class="account" @keydown.esc="onEsc">
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
        to="/anliegen"
        class="account__item"
        role="menuitem"
        @click="accountOpen = false"
      >
        Anliegen
      </RouterLink>
      <RouterLink
        v-if="auth.can('mail:manage')"
        to="/admin/mail-freigaben"
        class="account__item"
        role="menuitem"
        @click="accountOpen = false"
      >
        Absender-Freigaben
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
</template>

<style scoped>
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
