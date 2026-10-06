import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const MESSY = fileURLToPath(new URL("../../data/mapper/v05.xlsx", import.meta.url));
const POLICY = fileURLToPath(new URL("./fixtures/backup-policy.md", import.meta.url));

test("a messy xlsx is mapped, confirmed and answered from an uploaded document", async ({ page }) => {
  await page.goto("/?view=workspace");
  await page.getByLabel("upload a questionnaire").setInputFiles(MESSY);
  await expect(page.getByRole("cell", { name: /information security program/ }).first()).toBeVisible();
  await page.getByRole("button", { name: "Confirm mapping" }).click();
  await expect(page.getByText("20 questions")).toBeVisible();
  await page.getByLabel("upload documents").setInputFiles(POLICY);
  await expect(page.getByRole("row", { name: /backup-policy\.md/ })).toContainText("policy");
  await page.keyboard.press("r");
  await page.waitForURL(/view=run&run=/);
  await expect(page.getByText(/20 of 20 answered · done/)).toBeVisible({ timeout: 120_000 });
});
