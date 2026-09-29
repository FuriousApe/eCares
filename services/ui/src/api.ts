import type {
  AuditEntry, Meta, Page, PatientDetail, PatientWithContext, Program,
  Resolution, SyncRun, Task, TaskFilters,
} from "./types";

declare global {
  interface Window {
    WORKLIST_API_BASE_URL?: string;
  }
}

export const API_BASE = window.WORKLIST_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public requestId?: string) {
    super(message);
  }
  /** Someone else changed the task first (stale `version`). */
  get isConflict() {
    return this.status === 409;
  }
  /** fetch() itself failed: server down, CORS, offline. */
  get isNetwork() {
    return this.status === 0;
  }
}

export interface Caller {
  role: string;
  userId: string;
}

type Query = Record<string, string | number | boolean | string[] | undefined>;

function qs(query?: Query): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function makeApi(caller: Caller) {
  async function req<T>(method: string, path: string, opts: { query?: Query; body?: unknown } = {}): Promise<T> {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}${path}${qs(opts.query)}`, {
        method,
        headers: {
          "X-User-Role": caller.role,
          "X-User-Id": caller.userId,
          ...(opts.body ? { "Content-Type": "application/json" } : {}),
        },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
    } catch {
      throw new ApiError(0, "network", `Cannot reach the server at ${API_BASE}.`);
    }
    if (!res.ok) {
      let code = "error";
      let message = `Request failed (${res.status})`;
      let requestId: string | undefined;
      try {
        const j = await res.json();
        code = j.code ?? code;
        message = j.message ?? (typeof j.detail === "string" ? j.detail : message);
        requestId = j.request_id;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(res.status, code, message, requestId);
    }
    return (await res.json()) as T;
  }

  const taskAction = (id: number, action: string, body: object) =>
    req<Task>("POST", `/tasks/${id}/${action}`, { body });

  return {
    meta: () => req<Meta>("GET", "/meta"),
    programs: () => req<{ items: Program[] }>("GET", "/programs"),

    tasks: (f: TaskFilters, cursor?: string, limit = 50) =>
      req<Page<Task>>("GET", "/tasks", { query: { ...f, limit, cursor } }),
    task: (id: number) => req<{ task: Task; history: AuditEntry[] }>("GET", `/tasks/${id}`),
    claim: (t: Task) => taskAction(t.task_id, "claim", { version: t.version }),
    complete: (t: Task, resolution: Resolution, note?: string) =>
      taskAction(t.task_id, "complete", { version: t.version, resolution, note: note || undefined }),
    decline: (t: Task, reason: string, snooze_days: number) =>
      taskAction(t.task_id, "decline", { version: t.version, reason, snooze_days }),
    snooze: (t: Task, until: string, reason: string) =>
      taskAction(t.task_id, "snooze", { version: t.version, until, reason }),

    patients: (q: string, cursor?: string, limit = 50) =>
      req<Page<PatientWithContext>>("GET", "/patients", { query: { q, limit, cursor } }),
    patient: (id: string) => req<PatientDetail>("GET", `/patients/${encodeURIComponent(id)}`),

    syncRuns: () => req<{ items: SyncRun[] }>("GET", "/admin/sync-runs", { query: { limit: 10 } }),
    runSync: () => req<{ run: SyncRun; changed_patient_ids: string[] }>("POST", "/admin/sync"),
    evaluate: (all: boolean) =>
      req<{ enqueued_count: number; scope: string; note: string | null }>("POST", "/admin/evaluate", { query: { all } }),
  };
}

export type Api = ReturnType<typeof makeApi>;
