import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useKeys } from "./keys";

function Probe({ onA, onEsc }: { onA: () => void; onEsc: () => void }) {
  useKeys({ a: onA, Escape: onEsc });
  return <input aria-label="search" />;
}

describe("useKeys", () => {
  it("fires a single key on the page", () => {
    const onA = vi.fn();
    render(<Probe onA={onA} onEsc={() => {}} />);
    fireEvent.keyDown(document.body, { key: "a" });
    expect(onA).toHaveBeenCalledTimes(1);
  });

  it("ignores single keys while a text field has focus, but Esc always works", () => {
    const onA = vi.fn();
    const onEsc = vi.fn();
    const { getByLabelText } = render(<Probe onA={onA} onEsc={onEsc} />);
    const input = getByLabelText("search");
    input.focus();
    fireEvent.keyDown(input, { key: "a" });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onA).not.toHaveBeenCalled();
    expect(onEsc).toHaveBeenCalledTimes(1);
  });

  it("is case sensitive and ignores modified keys", () => {
    const onA = vi.fn();
    render(<Probe onA={onA} onEsc={() => {}} />);
    fireEvent.keyDown(document.body, { key: "A" });
    fireEvent.keyDown(document.body, { key: "a", metaKey: true });
    expect(onA).not.toHaveBeenCalled();
  });
});
