import { execFileSync } from "node:child_process";
import { expect, type Page } from "@playwright/test";

/** How long a run may take: live model calls while recording are far slower than replay. */
export const RUN_WAIT = process.env.LLM_MODE === "record" ? 1_200_000 : 150_000;

/** Start the sample company from Home and wait until the run is done; returns the run id. */
export async function sampleRun(page: Page): Promise<string> {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Try with a sample company" })).toBeEnabled();
  await page.keyboard.press("s");
  await page.waitForURL(/view=run&run=/);
  await expect(page.getByText(/64 of 64 answered · done/)).toBeVisible({ timeout: RUN_WAIT });
  return new URL(page.url()).searchParams.get("run") as string;
}

/** Read cells of a downloaded xlsx with openpyxl (the repo's Python is on PATH in CI and locally). */
export function xlsxCells(path: string, sheet: string, cells: string[]): Record<string, unknown> {
  const script =
    "import json, sys, openpyxl\n" +
    "ws = openpyxl.load_workbook(sys.argv[1])[sys.argv[2]]\n" +
    "print(json.dumps({c: ws[c].value for c in sys.argv[3:]}, default=str))";
  return JSON.parse(execFileSync("python", ["-c", script, path, sheet, ...cells], { encoding: "utf-8" }));
}
