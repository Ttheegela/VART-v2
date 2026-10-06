import { useSyncExternalStore } from "react";

export type View = "home" | "workspace" | "run" | "questions" | "export" | "audit" | "gap";
export type Route = { view: View; run?: string; item?: string; questionnaire?: string; scope?: string };

const VIEWS: readonly View[] = ["home", "workspace", "run", "questions", "export", "audit", "gap"];
const KEYS = ["run", "item", "questionnaire", "scope"] as const;

/** Only `/` and `/api/*` exist in production, so every view lives in the query string. */
export function readRoute(search: string = window.location.search): Route {
  const q = new URLSearchParams(search);
  const view = q.get("view") as View | null;
  const route: Route = { view: view && VIEWS.includes(view) ? view : "home" };
  if (route.view === "home") return route;
  for (const k of KEYS) {
    const v = q.get(k);
    if (v) route[k] = v;
  }
  return route;
}

export function href(r: Route): string {
  const q = new URLSearchParams({ view: r.view });
  for (const k of KEYS) if (r[k]) q.set(k, r[k] as string);
  return `?${q.toString()}`;
}

/** `replace`: no new history entry (the guided tour's moves, so browser Back does not walk the tour). */
export function go(r: Route, { replace = false }: { replace?: boolean } = {}): void {
  window.history[replace ? "replaceState" : "pushState"](null, "", href(r));
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function subscribe(cb: () => void) {
  window.addEventListener("popstate", cb);
  return () => window.removeEventListener("popstate", cb);
}

export function useRoute(): Route {
  const search = useSyncExternalStore(subscribe, () => window.location.search);
  return readRoute(search);
}
