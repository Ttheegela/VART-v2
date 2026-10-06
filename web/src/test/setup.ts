import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { resetTourForTests } from "../lib/tour";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetTourForTests();
  window.history.replaceState(null, "", "/"); // a test never inherits the route the one before left
});
