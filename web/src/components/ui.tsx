import type { ReactNode } from "react";
import type { Label } from "../lib/api";
import { CHIP, LABEL_WORD } from "../lib/labels";

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd aria-hidden="true">{children}</kbd>;
}

type ButtonProps = {
  k: string; // the key shown in the hint
  shortcut?: string; // aria-keyshortcuts when it differs from k ("Shift+A")
  label: string;
  onClick?: () => void;
  submit?: boolean; // a form's submit button: Enter in the form's fields presses it
  primary?: boolean;
  quiet?: boolean;
  disabled?: boolean;
  busy?: boolean;
  busyLabel?: string;
};

/** design.md: every action shows its key before the label; the accessible name is the label alone. */
export function Button({ k, shortcut, label, onClick, submit, primary, quiet, disabled, busy, busyLabel }: ButtonProps) {
  const look = quiet
    ? "text-on-chrome-2 hover:bg-chrome-2 hover:text-on-chrome"
    : primary
      ? "bg-chrome text-on-chrome hover:bg-neutral-800"
      : "border border-ink bg-paper text-ink hover:bg-sunken";
  return (
    <button
      type={submit ? "submit" : "button"}
      aria-keyshortcuts={shortcut ?? k}
      disabled={disabled || busy}
      onClick={onClick}
      className={`inline-flex h-7 items-center gap-2 whitespace-nowrap px-2 text-sm font-medium active:translate-y-px disabled:cursor-not-allowed disabled:border-rule-strong disabled:bg-paper disabled:text-ink-3 ${look}`}
    >
      <Kbd>{k}</Kbd>
      <span>{busy ? (busyLabel ?? label) : label}</span>
    </button>
  );
}

export function LabelChip({ label }: { label: Label }) {
  return (
    <span className={`inline-block min-w-[9ch] px-1 text-center text-xs font-medium leading-[18px] ${CHIP[label]}`}>
      {LABEL_WORD[label]}
    </span>
  );
}

export function ErrorLine({ message }: { message: string | null }) {
  if (!message) return null;
  return <p role="alert" className="text-xs font-medium text-ink">Error: {message}</p>;
}
