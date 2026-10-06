import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import AuditLog from "./AuditLog";

describe("AuditLog", () => {
  it("lists events newest first", async () => {
    const old = { ...fixtures.audit[0], at: "2026-10-06T09:00:00Z", action: "doc.upload" };
    mockApi({ "GET /api/audit": [old, ...fixtures.audit] });
    render(<AuditLog workspace={fixtures.workspace} onGone={() => {}} />);
    expect(await screen.findByRole("cell", { name: "run.done" })).toBeInTheDocument();
    const cells = screen.getAllByRole("cell").map((c) => c.textContent);
    expect(cells.indexOf("run.done")).toBeLessThan(cells.indexOf("doc.upload"));
  });

  it("filters by action, and / focuses the filter", async () => {
    mockApi({ "GET /api/audit": [{ ...fixtures.audit[0], action: "doc.upload" }, ...fixtures.audit] });
    render(<AuditLog workspace={fixtures.workspace} onGone={() => {}} />);
    await screen.findByRole("cell", { name: "run.done" });
    await userEvent.keyboard("/");
    expect(screen.getByLabelText("search")).toHaveFocus();
    await userEvent.keyboard("doc");
    expect(screen.queryByRole("cell", { name: "run.done" })).not.toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "doc.upload" })).toBeInTheDocument();
  });
});
