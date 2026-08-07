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
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  // Beim ersten Aufruf steht noch nicht fest, ob ein Cookie gilt — erst fragen,
  // dann entscheiden, sonst blitzt für einen Moment die Anmeldeseite auf.
  await auth.resolve();

  if (!auth.isAuthenticated) {
    return to.meta.public ? true : { name: "login", query: { weiter: to.fullPath } };
  }

  if (to.meta.public) return { name: "dashboard" };

  // Ein erzwungener Passwortwechsel geht allem anderen vor: das Startpasswort
  // stammt von einem Administrator und kennt damit mindestens eine zweite Person.
  if (auth.mustChangePassword && to.name !== "profile") {
    return { name: "profile", query: { erstanmeldung: "1" } };
  }

  if (to.meta.permission && !auth.can(to.meta.permission)) {
    return { name: "dashboard" };
  }

  return true;
});
