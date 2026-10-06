import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import { useKeys } from "../lib/keys";
import { ExpiredNotice, Shell, goneOn404 } from "./Shell";

function Drawer({ onClose }: { onClose: () => void }) {
  useKeys({ Escape: onClose });
  return <div role="region" aria-label="drawer" />;
}

/** A view that opens its drawer after Shell has mounted (the Run grid's main path). */
function ViewWithDrawer({ onA }: { onA: () => void }) {
  const [open, setOpen] = useState(false);
  useKeys({ Enter: () => setOpen(true), A: onA });
  return (
    <Shell mode="RUN" cursor="" hints={[]} runId="r1" expiresAt={null}>
      <button type="button">row</button>
      {open && <Drawer onClose={() => setOpen(false)} />}
    </Shell>
  );
}

describe("Shell", () => {
  it("numbers the views, marks the current one and names its key", () => {
    window.history.replaceState(null, "", "?view=run&run=r1");
    render(<Shell mode="RUN" cursor="AC-04 · 4/60" hints={[["j/k", "move"]]} runId="r1" expiresAt={null}>x</Shell>);
    const current = screen.getByRole("link", { current: "page" });
    expect(current).toHaveTextContent("run");
    expect(current).toHaveAttribute("aria-keyshortcuts", "2");
    expect(screen.getByText("AC-04 · 4/60")).toBeInTheDocument();
    expect(screen.getByText("j/k").closest("[aria-hidden]")).toBeNull(); // the status line's keys reach screen readers
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

  it("leaves Esc to a drawer opened after mount when the key sheet is closed", async () => {
    render(<ViewWithDrawer onA={() => {}} />);
    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("region", { name: "drawer" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "drawer" })).not.toBeInTheDocument();
  });

  it("Esc closes only the key sheet when it is on top of a drawer", async () => {
    render(<ViewWithDrawer onA={() => {}} />);
    await userEvent.keyboard("{Enter}");
    await userEvent.keyboard("?");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "keys" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "drawer" })).toBeInTheDocument();
  });

  it("view keys are inert while the key sheet is open", async () => {
    window.history.replaceState(null, "", "?view=run&run=r1");
    const onA = vi.fn();
    render(<ViewWithDrawer onA={onA} />);
    await userEvent.keyboard("?");
    await userEvent.keyboard("A");
    await userEvent.keyboard("1");
    // Enter presses the focused Close button (the sheet's own control); it must not reach the view.
    await userEvent.keyboard("{Enter}");
    expect(onA).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "drawer" })).not.toBeInTheDocument();
    expect(window.location.search).toBe("?view=run&run=r1");
  });

  it("the key sheet takes focus, traps Tab and gives focus back on close", async () => {
    render(<ViewWithDrawer onA={() => {}} />);
    const row = screen.getByRole("button", { name: "row" });
    row.focus();
    await userEvent.keyboard("?");
    const dialog = screen.getByRole("dialog", { name: "keys" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const close = screen.getByRole("button", { name: "Close" });
    expect(close).toHaveFocus();
    await userEvent.tab();
    expect(close).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(close).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(row).toHaveFocus();
  });
});
