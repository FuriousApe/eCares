import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { fmtDate, fmtDateTime, fmtPhone, patientName, STATUS_LABEL, titleCase, TYPE_LABEL } from "../format";
import { useSession } from "../session";
import type { AuditEntry, Patient, PatientDetail, Task } from "../types";
import { TaskActions } from "./TaskActions";
import { Badge, CopyButton, Drawer, ErrorState, Spinner } from "./ui";
import { DueLabel, StatusBadge, TierBadge } from "./bits";

interface PanelApi {
  open: (patientId: string, focusTaskId?: number) => void;
  /** Bumps whenever any task changed, so lists behind the panel refetch. */
  dataVersion: number;
}
const Ctx = createContext<PanelApi>({ open: () => {}, dataVersion: 0 });
export const usePanel = () => useContext(Ctx);

export function PanelProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<{ id: string; focus?: number } | null>(null);
  const [dataVersion, setDataVersion] = useState(0);
  const open = useCallback((id: string, focus?: number) => setTarget({ id, focus }), []);
  const value = useMemo(() => ({ open, dataVersion }), [open, dataVersion]);

  return (
    <Ctx.Provider value={value}>
      {children}
      {target && (
        <Drawer label="Patient details" onClose={() => setTarget(null)}>
          <PatientPanel patientId={target.id} focusTaskId={target.focus} onChanged={() => setDataVersion((v) => v + 1)} />
        </Drawer>
      )}
    </Ctx.Provider>
  );
}

function PatientPanel({ patientId, focusTaskId, onChanged }: {
  patientId: string; focusTaskId?: number; onChanged: () => void;
}) {
  const { api } = useSession();
  const [data, setData] = useState<PatientDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.patient(patientId).then((d) => { setData(d); setError(null); }, (e: Error) => setError(e.message));
  }, [api, patientId]);
  useEffect(load, [load]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <Spinner label="Loading patient…" />;

  const changed = () => { load(); onChanged(); };
  const tasks = [...data.visible_tasks].sort(
    (a, b) => Number(b.task_id === focusTaskId) - Number(a.task_id === focusTaskId),
  );
  const active = tasks.filter((t) => t.status === "open" || t.status === "in_progress");
  const past = tasks.filter((t) => !active.includes(t));

  return (
    <div className="panel">
      <PatientHeader p={data.patient} />

      <section>
        <h3>Programs</h3>
        <div className="chips">
          {data.enrollments.length === 0 && <span className="muted">Not enrolled in any program</span>}
          {data.enrollments.map((e) => (
            <span key={e.program_id} className="chip-static">{titleCase(e.program_id)} <TierBadge tier={e.tier} /></span>
          ))}
        </div>
      </section>

      <section>
        <h3>To do for this patient</h3>
        {active.length === 0 && <p className="muted">Nothing needs action right now.</p>}
        {active.map((t) => <TaskCard key={t.task_id} task={t} focused={t.task_id === focusTaskId} onChanged={changed} />)}
      </section>

      <section>
        <h3>Care schedule</h3>
        {data.needs.length === 0 ? (
          <p className="muted">No recurring visits required.</p>
        ) : (
          <table className="mini-table">
            <thead><tr><th>Visit type</th><th>Last visit</th><th>Next due</th><th /></tr></thead>
            <tbody>
              {data.needs.map((n) => (
                <tr key={`${n.program_id}-${n.specialty}`}>
                  <td>{n.specialty}</td>
                  <td>{fmtDate(n.last_visit_date)}</td>
                  <td>{fmtDate(n.due_date)}</td>
                  <td>{n.has_upcoming && <Badge tone="green">Visit booked</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {past.length > 0 && (
        <section>
          <h3>Earlier tasks</h3>
          {past.map((t) => <TaskCard key={t.task_id} task={t} onChanged={changed} />)}
        </section>
      )}
    </div>
  );
}

function PatientHeader({ p }: { p: Patient }) {
  const nonEnglish = p.language.toLowerCase() !== "english";
  return (
    <header className="patient-head">
      <h2>{patientName(p)}</h2>
      <p className="muted">
        {p.age} years · {p.gender} · Born {fmtDate(p.date_of_birth)} · ID {p.patient_id}
      </p>
      <div className="callbox">
        <div>
          <span className="label">Phone</span>
          <a className="phone-big" href={`tel:${p.phone.replace(/[^\d+]/g, "")}`}>{fmtPhone(p.phone)}</a>
        </div>
        <CopyButton text={p.phone} label="Copy phone number" />
        <div className="callbox-meta">
          <span className="label">Language</span>
          <Badge tone={nonEnglish ? "amber" : "neutral"}>{p.language}</Badge>
        </div>
        <div className="callbox-meta">
          <span className="label">Primary doctor</span>
          <span>{p.pcp_provider_name ?? "Not on file"}</span>
        </div>
      </div>
    </header>
  );
}

function TaskCard({ task, focused, onChanged }: { task: Task; focused?: boolean; onChanged: () => void }) {
  const { api } = useSession();
  const [history, setHistory] = useState<AuditEntry[] | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    if (showHistory) api.task(task.task_id).then((r) => setHistory(r.history), () => setHistory([]));
  }, [showHistory, api, task.task_id, task.version]);

  return (
    <article className={`task-card ${focused ? "task-card-focus" : ""}`}>
      <div className="task-card-top">
        <div>
          <strong>{task.specialty}</strong>{" "}
          <Badge tone={task.task_type === "referral" ? "purple" : "blue"}>{TYPE_LABEL[task.task_type]}</Badge>
        </div>
        <StatusBadge task={task} />
      </div>
      <p className="muted">
        Due <DueLabel task={task} /> · {titleCase(task.program_id)}
        {task.snooze_until && ` · snoozed until ${fmtDate(task.snooze_until)}`}
        {task.resolution && ` · ${titleCase(task.resolution)}`}
      </p>
      <TaskActions task={task} onChanged={onChanged} />
      <button className="link" onClick={() => setShowHistory((s) => !s)}>
        {showHistory ? "Hide history" : "Show history"}
      </button>
      {showHistory && (
        history === null ? <Spinner label="Loading history…" /> : history.length === 0 ? (
          <p className="muted">No activity yet.</p>
        ) : (
          <ul className="history">
            {history.map((h) => (
              <li key={h.event_id}>
                <strong>{titleCase(h.action)}</strong> by {h.actor}
                <span className="muted"> · {fmtDateTime(h.occurred_at)}</span>
              </li>
            ))}
          </ul>
        )
      )}
      <span className="visually-hidden">{STATUS_LABEL[task.status]}</span>
    </article>
  );
}
