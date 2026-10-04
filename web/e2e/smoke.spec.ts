import { expect, test } from "@playwright/test";

test("home page loads and reports a healthy system", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "VART" })).toBeVisible();
  const status = page.getByRole("region", { name: "System status" });
  await expect(status).toBeVisible();
  await expect(status.locator('dt:text-is("Overall") + dd')).toHaveText("OK");
  await expect(status.locator('dt:text-is("Database") + dd')).toHaveText("OK");
  // The status no longer waits for the workspace, so wait for it before reading its cookie.
  await expect(page.getByText(/arrives in the next build/)).toBeVisible();
  const cookies = await page.context().cookies();
  expect(cookies.some((c) => c.name === "vart_ws" && c.httpOnly)).toBe(true);
});
