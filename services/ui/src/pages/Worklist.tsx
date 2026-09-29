import { useEffect, useMemo, useState } from "react";
import { DueLabel, StatusBadge } from "../components/bits";
import { usePanel } from "../components/PatientPanel";
import { TaskActions } from "../components/TaskActions";
import { Badge, EmptyState, ErrorState, Spinner } from "../components/ui";
import { fmtPhone, patientName, titleCase, TYPE_LABEL } from "../format";
import { usePaged } from "../hooks";
import { useSession } from "../session";
import type { Program, TaskFilters } from "../types";

const SPECIALTIES = ["Cardiology", "Endocrinology", "Nephrology", "Ophthalmology", "PCP", "Podiatry"];

type ViewId = "todo" | "mine" | "overdue" | "all";

export function Worklist() {
  const { api, user } = useSession();
  const panel = usePanel();
  const [view, setView] = useState<ViewId>("todo");
  const [specialty, setSpecialty] = useState("");
  const [taskType, setTaskType] = useState("");
  const [program, setProgram] = useState("");
  const [search, setSearch] = useState("");
  const [programs, setPrograms] = useState<Program[]>([]);

  useEffect(() => {
    api.programs().then((r) => setPrograms(r.items.filter((p) => p.active)), () => {});
  }, [api]);

  const filters = useMemo<TaskFilters>(() => {
    const base: TaskFilters = { specialty, task_type: taskType, program };
    if (view === "todo") base.status = ["open"];
    if (view === "mine") { base.status = ["in_progress"]; base.assigned_to = user.id; }
    if (view === "overdue") base.overdue = true;
    return base;
  }, [view, specialty, taskType, program, user.id]);

  const list = usePaged((cursor) => api.tasks(filters, cursor), [api, filters, panel.dataVersion]);

  const q = search.trim().toLowerCase();
  const digits = q.replace(/\D/g, "");
  const rows = q
    ? list.items.filter((t) => {
        const p = t.patient;
        const text = `${p ? patientName(p) : ""} ${t.patient_id}`.toLowerCase();
        return text.includes(q) || (digits.length >= 3 && (p?.phone.replace(/\D/g, "") ?? "").includes(digits));
      })
    : list.items;

  const views: { id: ViewId; label: string }[] = [
    { id: "todo", label: "To do" },
    { id: "mine", label: "My tasks" },
    { id: "overdue", label: "Overdue" },
    { id: "all", label: "All active" },
  ];
  const filtered = Boolean(specialty || taskType || program || q);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Worklist</h1>
          <p className="muted">Patients who are due for a visit. Take a task, make the call, then record what happened.</p>
        </div>
        <button className="btn" onClick={list.reload}>↻ Refresh</button>
      </div>

      <div className="toolbar">
        <div className="segmented" role="tablist" aria-label="Task view">
          {views.map((v) => (
            <button key={v.id} role="tab" aria-selected={view === v.id}
              className={view === v.id ? "seg seg-on" : "seg"} onClick={() => setView(v.id)}>{v.label}</button>
          ))}
        </div>
        <input id="search" className="search" type="search" placeholder="Search name, phone or ID   ( / )"
          value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search loaded tasks" />
        <select value={specialty} onChange={(e) => setSpecialty(e.target.value)} aria-label="Visit type">
          <option value="">All visit types</option>
          {SPECIALTIES.map((s) => <option key={s}>{s}</option>)}
        </select>
        {user.role !== "scheduler" && (
          <select value={taskType} onChange={(e) => setTaskType(e.target.value)} aria-label="Task type">
            <option value="">Schedule + referral</option>
            <option value="scheduling">Schedule visit</option>
            <option value="referral">Needs referral</option>
          </select>
        )}
        <select value={program} onChange={(e) => setProgram(e.target.value)} aria-label="Program">
          <option value="">All programs</option>
          {programs.map((p) => <option key={p.program_id} value={p.program_id}>{titleCase(p.program_id)}</option>)}
        </select>
        {filtered && (
          <button className="btn btn-ghost" onClick={() => { setSpecialty(""); setTaskType(""); setProgram(""); setSearch(""); }}>Clear filters</button>
        )}
      </div>

      {list.loading ? <Spinner /> : list.error ? <ErrorState message={list.error} onRetry={list.reload} /> : rows.length === 0 ? (
        <EmptyState icon="✓" title={filtered ? "No tasks match these filters" : view === "mine" ? "You have no tasks in progress" : "All caught up"}
          hint={view === "mine" ? "Switch to “To do” to take a new one." : undefined} />
      ) : (
        <div className="card table-wrap">
          <table className="table">
            <thead>
              <tr><th>Patient</th><th>Phone</th><th>Needs</th><th>Due</th><th>Status</th><th className="col-action">Next step</th></tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.task_id} className="row-click" tabIndex={0}
                  onClick={() => panel.open(t.patient_id, t.task_id)}
                  onKeyDown={(e) => e.key === "Enter" && panel.open(t.patient_id, t.task_id)}>
                  <td>
                    <strong>{patientName(t.patient, t.patient_id)}</strong>
                    <div className="muted">
                      {t.patient ? `${t.patient.age} · ` : ""}{t.patient_id}
                      {t.patient && t.patient.language.toLowerCase() !== "english" && <> · <Badge tone="amber">{t.patient.language}</Badge></>}
                    </div>
                  </td>
                  <td className="nowrap">
                    {t.patient && (
                      <a href={`tel:${t.patient.phone.replace(/[^\d+]/g, "")}`} onClick={(e) => e.stopPropagation()}>
                        {fmtPhone(t.patient.phone)}
                      </a>
                    )}
                  </td>
                  <td>
                    <strong>{t.specialty}</strong>
                    <div><Badge tone={t.task_type === "referral" ? "purple" : "blue"}>{TYPE_LABEL[t.task_type]}</Badge></div>
                  </td>
                  <td><DueLabel task={t} /></td>
                  <td><StatusBadge task={t} /></td>
                  <td className="col-action" onClick={(e) => e.stopPropagation()}>
                    <TaskActions task={t} variant="primary" onChanged={list.reload} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="table-foot">
            <span className="muted">
              {rows.length} shown{list.hasMore ? " · more available" : ""}
              {q && list.hasMore ? " (search covers loaded rows only)" : ""}
            </span>
            {list.hasMore && (
              <button className="btn" onClick={list.loadMore} disabled={list.loadingMore}>
                {list.loadingMore ? "Loading…" : "Load more"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
