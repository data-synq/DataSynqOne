import { expect, test } from "@playwright/test";

test("an anonymous visitor reaches the sign-in page", async ({ page }) => {
  await page.route("**/auth/me", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Nicht angemeldet" }),
    }),
  );

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Anmeldung" })).toBeVisible();
  await expect(page.getByLabel("E-Mail-Adresse")).toHaveAttribute("autocomplete", "username");
  await expect(page.getByLabel("Passwort")).toHaveAttribute("autocomplete", "current-password");
});
