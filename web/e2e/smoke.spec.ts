import { expect, test } from "@playwright/test";

test("home page loads and reports a healthy system", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "VART" })).toBeVisible();
  const status = page.getByRole("region", { name: "System status" });
  await expect(status).toBeVisible();
  await expect(status.getByText("Database")).toBeVisible();
  const cookies = await page.context().cookies();
  expect(cookies.some((c) => c.name === "vart_ws" && c.httpOnly)).toBe(true);
});
