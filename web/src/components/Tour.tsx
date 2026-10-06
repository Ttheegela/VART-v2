import { useEffect, useRef, type KeyboardEvent } from "react";
import { go, href, useRoute } from "../lib/route";
import { STEPS, moveTour, narrow, stopTour, useTour } from "../lib/tour";
import { Button } from "./ui";

/** The guided tour's card (Plan 4 Task 3b). Not modal: the page under it keeps working, and its keys (→ ← Esc)
 * work only while focus is inside the card, so Enter on any other button or link stays that control's (adversary-1
 * I4); Enter on Next is Next's own click. It outlines the step's `data-tour` element, moves focus to Next on every
 * step, gives focus back when it closes, and closes itself when another run opens or, under 900 px, when a drawer
 * (a full-screen aria-modal dialog) opens. It sits under the key sheet (z-20) and over the narrow drawer (z-10). */
export default function Tour() {
  const { open, step, ctx } = useTour();
  const route = useRoute();
  const box = useRef<HTMLDivElement>(null);
  const s = STEPS[step];

  useEffect(() => {
    if (!open || !ctx) return;
    const r = s.route(ctx);
    if (r && href(r) !== window.location.search) go(r, { replace: true }); // browser Back skips the tour's moves
  }, [open, step, ctx, s]);

  const seen = useRef(route.view);
  useEffect(() => { // the visitor navigated away from the step's view (adversary-2 M8); a step's own move matches it
    const moved = seen.current !== route.view;
    seen.current = route.view;
    const want = ctx && s.route(ctx)?.view;
    if (open && moved && want && want !== route.view) stopTour();
  }, [open, ctx, s, route.view]);

  useEffect(() => {
    if (!open || !ctx) return;
    if ((route.run && route.run !== ctx.runId) || (route.item && narrow())) stopTour(); // never on a live run
  }, [open, ctx, route.run, route.item]);

  useEffect(() => {
    if (!open || (s.target === "drawer" && narrow())) return; // under 900 px step 5 opens no drawer: nothing to outline
    let el: Element | null = null;
    const find = () => {
      el = document.querySelector(`[data-tour="${s.target}"]`);
      if (!el) return; // the view may still be loading
      watch.disconnect();
      el.setAttribute("data-tour-on", "");
      el.scrollIntoView?.({ block: "nearest" });
    };
    const watch = new MutationObserver(find);
    watch.observe(document.body, { childList: true, subtree: true });
    find();
    return () => {
      watch.disconnect();
      el?.removeAttribute("data-tour-on");
    };
  }, [open, s, route.view, route.item]);

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement; // before the effect below moves focus to Next
    return () => {
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, [open]);

  useEffect(() => {
    if (open) box.current?.querySelector<HTMLElement>('[aria-keyshortcuts="ArrowRight"]')?.focus();
  }, [open, step]);

  if (!open || !ctx) return null;
  const onKey = (e: KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Escape") stopTour();
    else if (e.key === "ArrowRight") moveTour(1);
    else if (e.key === "ArrowLeft") moveTour(-1);
    else return;
    e.preventDefault();
    e.stopPropagation(); // a drawer's Esc under the card is not closed by the same key
  };
  const last = step === STEPS.length - 1;
  return (
    <div
      ref={box}
      role="dialog"
      aria-label="guided tour"
      aria-describedby="tour-body"
      onKeyDown={onKey}
      className="fixed inset-x-0 bottom-7 z-[15] border-t border-ink bg-paper p-4 text-sm min-[900px]:inset-x-auto min-[900px]:right-4 min-[900px]:bottom-9 min-[900px]:w-[22rem] min-[900px]:border"
    >
      <p className="text-xs text-ink-3">step {step + 1} of {STEPS.length}</p>
      <h2 className="mt-1 text-base font-medium">{s.title}</h2>
      <p id="tour-body" className="mt-1 text-ink-2">{s.body}</p>
      <p role="status" className="sr-only">{`Step ${step + 1} of ${STEPS.length}: ${s.title}. ${s.body}`}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button k="←" shortcut="ArrowLeft" label="Back" onClick={() => moveTour(-1)} disabled={step === 0} />
        <Button k="→" shortcut="ArrowRight" label={last ? "Done" : "Next"} primary onClick={() => moveTour(1)} />
        <Button k="esc" shortcut="Escape" label="Skip" onClick={stopTour} />
      </div>
    </div>
  );
}
