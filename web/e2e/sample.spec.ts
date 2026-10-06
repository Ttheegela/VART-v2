import { expect, test, type Page } from "@playwright/test";
import { sampleRun, xlsxCells } from "./helpers.ts";

// One sample run feeds all four tests: each run spends ~120 model calls, and the network cap is 400 an hour
// (Ruling 20). Serial, in this order: the export approves the verified answers, and the interview changes an item.
test.describe.configure({ mode: "serial" });

let page: Page;
let run: string;

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  run = await sampleRun(page);
});

test.afterAll(async () => {
  await page.close();
});

/** Reload the finished run, so a test starts with no filter, drawer or focus left by the one before. */
async function openRun(): Promise<void> {
  await page.goto(`/?view=run&run=${run}`);
  await expect(page.getByText(/64 of 64 answered · done/)).toBeVisible();
}

test("the sample flow fills the questionnaire and opens the evidence", async () => {
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

test("at 375px the page never scrolls sideways and the drawer is a modal", async () => {
  await page.setViewportSize({ width: 375, height: 812 });
  await openRun();
  // a string, not a function: the e2e tsconfig has no DOM lib
  expect(await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")).toBe(true);
  await page.getByRole("row", { name: /^VSQ-01 / }).click();
  await expect(page.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  await page.setViewportSize({ width: 1280, height: 720 });
});

test("the export is the original workbook, filled, cell by cell", async () => {
  await openRun();
  await page.keyboard.press("Shift+A");
  await expect(page.getByRole("button", { name: /Approve all verified \(0\)/ })).toBeDisabled();
  const download = page.waitForEvent("download");
  await page.keyboard.press("e");
  const saved = await download;
  expect(saved.suggestedFilename()).toMatch(/\.xlsx$/);
  const file = test.info().outputPath(saved.suggestedFilename()); // openpyxl needs the extension; path() has none
  await saved.saveAs(file);
  const cells = xlsxCells(file, "Questionnaire", ["A5", "C5", "F5", "G5", "H5", "A7", "C7", "D7", "F7", "G7"]);
  expect(cells).toMatchObject({ A5: "#", C5: "Control Question", F5: "Status", G5: "Sources", H5: "Notes", A7: "VSQ-01" });
  expect(cells.F7).toMatch(/^(Verified · Approved|(Partial|Conflict|Unknown) · Draft, not approved)$/);
  expect(["Yes", "No", "N/A", null]).toContain(cells.D7);
});

test("an answer in Questions for you fills its item", async () => {
  await openRun();
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
