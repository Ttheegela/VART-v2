import { expect, test } from "@playwright/test";

test("home page loads and reports a healthy system", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "VART" })).toBeVisible();
  const status = page.getByRole("region", { name: "System status" });
  await expect(status).toBeVisible();
  await expect(status.locator('dt:text-is("Overall") + dd')).toHaveText("OK");
  await expect(status.locator('dt:text-is("Database") + dd')).toHaveText("OK");
  // The workspace request runs alongside the status check, so its cookie may land after the panel shows.
  await expect
    .poll(async () =>
      (await page.context().cookies()).some((c) => c.name === "vart_ws" && c.httpOnly && c.value !== ""),
    )
    .toBe(true);
});
