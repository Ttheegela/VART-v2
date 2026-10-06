import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const remote = process.env.PLAYWRIGHT_BASE_URL;

export default defineConfig({
  testDir: "e2e",
  timeout: process.env.LLM_MODE === "record" ? 1_320_000 : 180_000, // live calls while recording are slow
  // No retries even in CI: a retry re-runs the shared sample run, and its model calls can pass the 400/h per-network cap.
  retries: 0,
  use: { baseURL: remote ?? "http://127.0.0.1:8000", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // One server: FastAPI serves the built UI (public/) and the API. Build first so it mounts.
  webServer: remote
    ? undefined
    : {
        command: "npm run build && cd .. && uvicorn app.main:app --port 8000",
        url: "http://127.0.0.1:8000/api/health",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        env: {
          LLM_MODE: process.env.LLM_MODE ?? "replay",
          LLM_RECORDING: process.env.LLM_RECORDING ?? fileURLToPath(new URL("./e2e/recorded.jsonl", import.meta.url)),
        },
      },
});
