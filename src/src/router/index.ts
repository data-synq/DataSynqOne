import { createRouter, createWebHistory } from "vue-router";
import DashboardView from "../views/DashboardView.vue";
import LoginView from "../views/LoginView.vue";
import { useAuthStore } from "../stores/auth";
import type { PermissionName } from "../api/client";

declare module "vue-router" {
  interface RouteMeta {
    /** Ohne dieses Recht ist die Route nicht erreichbar. */
    permission?: PermissionName;
    /** Nur diese Route ist ohne Anmeldung erreichbar. */
    public?: boolean;
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginView, meta: { public: true } },
    {
      path: "/mfa",
      name: "mfa",
      component: () => import("../views/MfaView.vue"),
    },
    {
      path: "/einladung/:token",
      name: "invitation",
      component: () => import("../views/InvitationView.vue"),
      meta: { public: true },
    },
    { path: "/", name: "dashboard", component: DashboardView },
    {
      path: "/profil",
      name: "profile",
      component: () => import("../views/ProfileView.vue"),
    },
    {
      path: "/admin/benutzer",
      name: "users",
      component: () => import("../views/AdminUsersView.vue"),
      meta: { permission: "users:manage" },
    },
    {
      path: "/admin/mail-freigaben",
      name: "mail-approval",
      component: () => import("../views/MailApprovalView.vue"),
      meta: { permission: "mail:manage" },
    },
    {
      path: "/anliegen",
      name: "cases",
      component: () => import("../views/CasesView.vue"),
      meta: { permission: "documents:read" },
    },
    {
      path: "/anliegen/graph",
      name: "cases-graph",
      component: () => import("../views/CaseGraphView.vue"),
      meta: { permission: "documents:read" },
    },
    {
      path: "/anliegen/:trackingId",
      name: "case-detail",
      component: () => import("../views/CaseDetailView.vue"),
      meta: { permission: "documents:read" },
    },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  // Beim ersten Aufruf steht noch nicht fest, ob ein Cookie gilt — erst fragen,
  // dann entscheiden, sonst blitzt für einen Moment die Anmeldeseite auf.
  await auth.resolve();

  if (to.meta.public && to.name !== "login") return true;

  if (!auth.hasSession) {
    return to.meta.public ? true : { name: "login", query: { weiter: to.fullPath } };
  }

  // Nur die Anmeldeseite ist für Angemeldete sinnlos. Ein Einladungs- oder
  // Reset-Link muss auch dann funktionieren, wenn noch eine Sitzung läuft — genau
  // dann klickt jemand ihn, der sein Passwort vergessen hat und irgendwo noch
  // angemeldet ist.
  if (auth.authStage === "password_change" && to.name !== "profile") {
    return { name: "profile", query: { erstanmeldung: "1" } };
  }

  if (
    (auth.authStage === "mfa_setup" || auth.authStage === "mfa_challenge") &&
    to.name !== "mfa"
  ) {
    return { name: "mfa", query: { weiter: to.fullPath } };
  }

  if (to.name === "login" || (to.name === "mfa" && auth.isAuthenticated)) {
    return { name: "dashboard" };
  }

  if (to.meta.permission && !auth.can(to.meta.permission)) {
    return { name: "dashboard" };
  }

  return true;
});
