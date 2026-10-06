import { expect, test } from "@playwright/test";
import { sampleRun } from "./helpers.ts";

test("the sample flow fills the questionnaire and opens the evidence", async ({ page }) => {
  await sampleRun(page);
  const rows = page.getByRole("row", { name: /^VSQ-\d\d / });
  await expect(rows).toHaveCount(64);
  await page.keyboard.press("v"); // the verified filter (the command line also has "Approve all verified")
  await rows.first().click();
  const drawer = page.getByRole("complementary");
  await expect(drawer.getByText(/^sources \(\d+\)$/)).toBeVisible();
  await expect(drawer.locator("mark").first()).toBeVisible();
  await expect(drawer.getByText("Draft, not approved")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
});

test("at 375px the page never scrolls sideways and the drawer is a modal", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await sampleRun(page);
  // a string, not a function: the e2e tsconfig has no DOM lib
  expect(await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")).toBe(true);
  await page.getByRole("row", { name: /^VSQ-01 / }).click();
  await expect(page.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
});
