import type { components } from "./api-types";

export type Health = components["schemas"]["HealthOut"];

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
  } catch {
    // not JSON
  }
  return `Request failed (${res.status})`;
}

export function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin", ...init });
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return (await res.json()) as T;
}

let workspace: Promise<void> | undefined;

/** Test-only: forget the memoized workspace. */
export function resetWorkspaceForTests() {
  workspace = undefined;
}

/** Creates (or loads) this browser's workspace. Must resolve before any workspace call. */
export function ensureWorkspace(): Promise<void> {
  workspace ??= request<{ created_at: string }>("/api/workspace").then(
    () => undefined,
    (e) => {
      workspace = undefined;
      throw e;
    },
  );
  return workspace;
}

/** Health answers 503 with a body when the database is down; both are readable states, not errors. */
export async function getHealth(): Promise<Health> {
  const res = await fetch("/api/health", { credentials: "same-origin" });
  if (res.status === 200 || res.status === 503) return (await res.json()) as Health;
  throw new ApiError(res.status, await errorMessage(res));
}
