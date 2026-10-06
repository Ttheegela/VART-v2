import { Component, type ReactNode } from "react";

export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    console.error("Screen render failed", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="m-4 space-y-3 border border-rule-strong p-4">
        <p className="font-medium">Something went wrong on this screen.</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="h-7 bg-chrome px-2 text-sm font-medium text-on-chrome hover:bg-neutral-800"
        >
          Reload
        </button>
      </div>
    );
  }
}
