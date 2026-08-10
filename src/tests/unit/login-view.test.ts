import { mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { describe, expect, it } from "vitest";

import LoginView from "../../src/views/LoginView.vue";

describe("LoginView", () => {
  it("renders an accessible sign-in form", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", component: LoginView }],
    });
    await router.push("/");
    await router.isReady();

    const wrapper = mount(LoginView, {
      global: { plugins: [createPinia(), router] },
    });

    expect(wrapper.get("h1").text()).toBe("Anmeldung");
    expect(wrapper.get("input[type='email']").attributes("autocomplete")).toBe("username");
    expect(wrapper.get("input[type='password']").attributes("autocomplete")).toBe(
      "current-password",
    );
    expect(wrapper.get("button[type='submit']").text()).toBe("Anmelden");
  });
});
