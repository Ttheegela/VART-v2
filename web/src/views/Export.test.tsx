import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import ExportView from "./Export";

describe("Export", () => {
  it("counts approved and draft answers and links the file", async () => {
    mockApi({ "GET /api/runs/r1/answers": { run: fixtures.run, rows: fixtures.rows } });
    render(<ExportView workspace={fixtures.workspace} onGone={() => {}} runId="r1" />);
    expect(await screen.findByText("0 approved · 2 draft · 1 unanswered")).toBeInTheDocument();
    expect(screen.getByText(/exported marked "Draft, not approved"/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export" })).toHaveAttribute("href", "/api/runs/r1/export");
  });

  it("shows a load error", async () => {
    mockApi({ "GET /api/runs/r1/answers": new Response(JSON.stringify({ detail: "boom" }), { status: 500 }) });
    render(<ExportView workspace={fixtures.workspace} onGone={() => {}} runId="r1" />);
    expect(await screen.findByText(/boom/)).toBeInTheDocument();
  });
});
