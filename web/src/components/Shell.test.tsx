import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import { ExpiredNotice, Shell, goneOn404 } from "./Shell";

describe("Shell", () => {
  it("numbers the views, marks the current one and names its key", () => {
    window.history.replaceState(null, "", "?view=run&run=r1");
    render(<Shell mode="RUN" cursor="AC-04 · 4/60" hints={[["j/k", "move"]]} runId="r1" expiresAt={null}>x</Shell>);
    const current = screen.getByRole("link", { current: "page" });
    expect(current).toHaveTextContent("run");
    expect(current).toHaveAttribute("aria-keyshortcuts", "2");
    expect(screen.getByText("AC-04 · 4/60")).toBeInTheDocument();
  });

  it("opens the key sheet on ? and closes it on Esc", async () => {
    render(<Shell mode="RUN" cursor="" hints={[]} runId="r1" expiresAt={null}>x</Shell>);
    await userEvent.keyboard("?");
    expect(screen.getByRole("dialog", { name: "keys" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "keys" })).not.toBeInTheDocument();
  });

  it("a 404 on a remembered id means the workspace is gone; other errors are words", () => {
    const onGone = vi.fn();
    expect(goneOn404(new ApiError(404, "Not found."), onGone)).toBeNull();
    expect(onGone).toHaveBeenCalledTimes(1);
    expect(goneOn404(new ApiError(500, "Request failed (500)"), onGone)).toBe("Request failed (500)");
  });

  it("the expired notice offers a fresh start", () => {
    render(<ExpiredNotice />);
    expect(screen.getByRole("alert")).toHaveTextContent("This workspace has expired");
    expect(screen.getByRole("button", { name: "Start again" })).toBeInTheDocument();
  });
});
