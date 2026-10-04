import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ErrorBoundary from "./ErrorBoundary";

function Broken(): never {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  it("passes a working screen through", () => {
    render(
      <ErrorBoundary>
        <p>Screen content</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Screen content")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("replaces a crashed screen with a way to reload", () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Broken />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong on this screen.");
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    expect(logged).toHaveBeenCalledWith("Screen render failed", expect.any(Error));
  });
});
