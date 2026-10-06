import { expect, test } from "@playwright/test";
import { RUN_WAIT, xlsxCells } from "./helpers.ts";

// One core gap check (at most 73 stance calls, no draft call) in its own workspace, plus at most 7 re-checks of
// Govern parts after the Ask-me answer. With the other specs (about 150 calls) it stays under the 400-an-hour
// per-network model-call cap.
test("the gap check runs over the sample documents, takes an Ask-me answer and exports the report", async ({ page }) => {
  await page.goto("/?view=workspace");
  await expect(page.getByRole("button", { name: "Load sample documents" })).toBeEnabled();
  await page.keyboard.press("l");
  await expect(page.getByText("security-improvement-plan.md")).toBeVisible();
  await page.keyboard.press("6");
  await page.waitForURL(/view=gap/);
  // the body's coverage line (the status bar repeats it)
  await expect(page.getByRole("main").getByText("checked 31 · ask me 5 · not checked 70 · of 106")).toBeVisible();
  await page.keyboard.press("r");
  await expect(page.getByText(/31 of 31 checked · done/)).toBeVisible({ timeout: RUN_WAIT }); // Ask me is not checked
  await expect(page.getByRole("row", { name: /^[A-Z]{2}\.[A-Z]{2}-\d\d / })).toHaveCount(106);
  // the planted improvement plan: at least one stated non-compliance shows
  const filters = page.getByRole("group", { name: "filter by label" });
  await expect(filters.getByRole("button", { name: /^not met [1-9]\d*$/ })).toBeVisible();

  // A Checked outcome: NIST's text and link, and its four parts
  await page.getByRole("row", { name: /^PR\.DS-11 / }).click();
  const drawer = page.getByRole("complementary");
  await expect(drawer.getByText("parts (4)")).toBeVisible();
  await expect(drawer.getByRole("link", { name: "NIST CSF 2.0 reference tool" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();

  // An Ask-me outcome, answered in the inspector (re-checked against Govern parts; fills stay suggestions)
  await page.getByRole("row", { name: /^GV\.RM-02 / }).click();
  await drawer
    .getByLabel("your answer to GV.RM-02")
    .fill("Yes. The board approved a cybersecurity risk appetite statement, and the security team shares it with every new hire.");
  await drawer.getByRole("button", { name: "Send" }).click();
  await expect(drawer.getByText("answered by you").first()).toBeVisible({ timeout: RUN_WAIT });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("row", { name: /^GV\.RM-02 / })).toContainText("answered by you");

  // The gap report
  const download = page.waitForEvent("download");
  await page.keyboard.press("e");
  const saved = await download;
  expect(saved.suggestedFilename()).toBe("csf-2.0-core-gap-report.xlsx");
  const file = test.info().outputPath(saved.suggestedFilename()); // openpyxl needs the extension
  await saved.saveAs(file);
  const cells = xlsxCells(file, "Gap report", ["A1", "B1", "A2", "D2", "A3", "G3", "A110"]);
  expect(cells).toMatchObject({
    A1: "Possible gap — review it",
    B1: "Scope: core",
    A2: "ID",
    D2: "Label",
    A3: "GV.OC-01",
    A110: "Not legal advice. CSF 2.0 text © NIST, public domain.",
  });
  expect(cells.G3).toBe("The organizational mission is understood and informs cybersecurity risk management"); // verbatim
});
