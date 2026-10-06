import { expect, test } from "@playwright/test";
import { sampleRun } from "./helpers.ts";

test("an answer in Questions for you fills its item", async ({ page }) => {
  const run = await sampleRun(page);
  await page.keyboard.press("3");
  await page.waitForURL(new RegExp(`view=questions&run=${run}`));
  const box = page.getByLabel(/^your answer to /).first();
  const code = (await box.getAttribute("aria-label"))!.replace("your answer to ", "");
  await box.fill("Yes. Customers can bring their own encryption keys, and keys are rotated every 90 days.");
  await page.getByRole("button", { name: "Send" }).first().click();
  const outcome = page.getByText(/also needs|^confirmed by you$/).first();
  await expect(outcome).toBeVisible();
  if ((await outcome.textContent())?.includes("also needs")) {
    await box.fill("The security team owns it and reviews it quarterly.");
    await page.getByRole("button", { name: "Send" }).first().click();
  }
  await expect(page.getByText("confirmed by you").first()).toBeVisible();
  await page.keyboard.press("2");
  await expect(page.getByRole("row", { name: new RegExp(`^${code} `) })).toContainText("confirmed by you");
});
