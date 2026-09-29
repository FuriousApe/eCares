import { useCallback, useEffect, useState } from "react";
import { Badge, Modal, Spinner, useToast } from "../components/ui";
import { fmtDateTime, STATUS_LABEL, titleCase } from "../format";
import { useSession } from "../session";
import type { SyncRun, TaskStatus } from "../types";

function summarize(json: string): string {
  try {
    const o = JSON.parse(json) as Record<string, unknown>;
    return Object.entries(o).map(([k, v]) => `${titleCase(k)}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ") || "—";
  } catch {
    return json || "—";
  }
}

export function Admin() {
  const { api, meta, refreshMeta } = useSession();
  const toast = useToast();
  const [runs, setRuns] = useState<SyncRun[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmAll, setConfirmAll] = useState(false);

  const load = useCallback(() => {
    api.syncRuns().then((r) => setRuns(r.items), () => setRuns([]));
    refreshMeta();
  }, [api, refreshMeta]);
  useEffect(load, [load]);

  async function act(name: string, fn: () => Promise<string>) {
    setBusy(name);
    try {
      toast("success", await fn());
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Admin</h1>
          <p className="muted">Data loading and re-checking. Most days, nothing here needs touching.</p>
        </div>
      </div>

      <div className="grid-2">
        <section className="card pad">
          <h3>Status</h3>
          <dl className="facts">
            <dt>Working as of</dt><dd>{meta?.as_of_date ?? "—"}</dd>
            <dt>Last data load</dt><dd>{fmtDateTime(meta?.last_sync_finished_at)}</dd>
          </dl>
          <div className="chips">
            {Object.entries(meta?.task_counts_by_status ?? {}).map(([s, n]) => (
              <Badge key={s} tone={s === "open" ? "blue" : s === "in_progress" ? "amber" : "neutral"}>
                {STATUS_LABEL[s as TaskStatus] ?? titleCase(s)}: {n}
              </Badge>
            ))}
          </div>
        </section>

        <section className="card pad">
          <h3>Actions</h3>
          <div className="stack">
            <div>
              <button className="btn btn-primary" disabled={busy !== null}
                onClick={() => act("sync", async () => {
                  const r = await api.runSync();
                  return `Data loaded. ${r.changed_patient_ids.length} patients changed.`;
                })}>{busy === "sync" ? "Loading…" : "Load latest patient data"}</button>
              <p className="muted">Reads the source files and queues any changed patients for re-checking.</p>
            </div>
            <div>
              <button className="btn" disabled={busy !== null}
                onClick={() => act("due", async () => `${(await api.evaluate(false)).enqueued_count} patients queued.`)}>
                {busy === "due" ? "Queuing…" : "Re-check patients who are due"}
              </button>
            </div>
            <div>
              <button className="btn btn-danger-outline" disabled={busy !== null} onClick={() => setConfirmAll(true)}>
                Re-check everyone…
              </button>
              <p className="muted">Use after changing a care program.</p>
            </div>
          </div>
        </section>
      </div>

      <h3 className="section-title">Recent data loads</h3>
      {runs === null ? <Spinner /> : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Started</th><th>Finished</th><th>Result</th><th>Details</th></tr></thead>
            <tbody>
              {runs.length === 0 && <tr><td colSpan={4} className="muted">No loads yet.</td></tr>}
              {runs.map((r) => (
                <tr key={r.run_id}>
                  <td>{fmtDateTime(r.started_at)}</td>
                  <td>{fmtDateTime(r.finished_at)}</td>
                  <td><Badge tone={r.status === "completed" || r.status === "succeeded" ? "green" : r.status === "running" ? "amber" : "red"}>{titleCase(r.status)}</Badge></td>
                  <td className="muted small">{summarize(r.counts_json)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirmAll && (
        <Modal title="Re-check every patient?" onClose={() => setConfirmAll(false)}
          footer={<>
            <button className="btn" onClick={() => setConfirmAll(false)}>Cancel</button>
            <button className="btn btn-danger" onClick={() => {
              setConfirmAll(false);
              act("all", async () => `${(await api.evaluate(true)).enqueued_count} patients queued.`);
            }}>Yes, re-check everyone</button>
          </>}>
          <p>This queues the whole patient list. Tasks may be created or closed while it runs.</p>
        </Modal>
      )}
    </div>
  );
}
