import { expect, test } from "@playwright/test";
import { sampleRun, xlsxCells } from "./helpers.ts";

test("the export is the original workbook, filled, cell by cell", async ({ page }) => {
  await sampleRun(page);
  await page.keyboard.press("Shift+A");
  await expect(page.getByRole("button", { name: /Approve all verified \(0\)/ })).toBeDisabled();
  const download = page.waitForEvent("download");
  await page.keyboard.press("e");
  const file = await (await download).path();
  const cells = xlsxCells(file, "Questionnaire", ["A5", "C5", "F5", "G5", "H5", "A7", "C7", "D7", "F7", "G7"]);
  expect(cells).toMatchObject({ A5: "#", C5: "Control Question", F5: "Status", G5: "Sources", H5: "Notes", A7: "VSQ-01" });
  expect(cells.F7).toMatch(/^(Verified · Approved|(Partial|Conflict|Unknown) · Draft, not approved)$/);
  expect(["Yes", "No", "N/A", null]).toContain(cells.D7);
});
