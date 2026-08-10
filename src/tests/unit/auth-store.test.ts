import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import type { CurrentUser } from "../../src/api/client";
import { useAuthStore } from "../../src/stores/auth";

function user(auth_stage: CurrentUser["auth_stage"]): CurrentUser {
  return {
    id: "user-1",
    email: "admin@example.org",
    display_name: "Admin",
    role: "admin",
    role_label: "Administrator",
    is_active: true,
    must_change_password: auth_stage === "password_change",
    mfa_enabled: auth_stage === "mfa_challenge" || auth_stage === "ready",
    object_access_mode: "all",
    object_codes: [],
    last_login_at: null,
    created_at: "2026-08-10T00:00:00Z",
    permissions: auth_stage === "ready" ? ["users:manage"] : [],
    auth_stage,
  };
}

describe("auth store stages", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it.each(["password_change", "mfa_setup", "mfa_challenge"] as const)(
    "keeps a %s session out of the application shell",
    (stage) => {
      const auth = useAuthStore();
      auth.user = user(stage);

      expect(auth.hasSession).toBe(true);
      expect(auth.isAuthenticated).toBe(false);
      expect(auth.can("users:manage")).toBe(false);
    },
  );

  it("exposes permissions only for a ready session", () => {
    const auth = useAuthStore();
    auth.user = user("ready");

    expect(auth.hasSession).toBe(true);
    expect(auth.isAuthenticated).toBe(true);
    expect(auth.can("users:manage")).toBe(true);
  });
});
