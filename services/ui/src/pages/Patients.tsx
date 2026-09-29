import { useState } from "react";
import { TierBadge } from "../components/bits";
import { usePanel } from "../components/PatientPanel";
import { Badge, EmptyState, ErrorState, Spinner } from "../components/ui";
import { fmtPhone, patientName } from "../format";
import { useDebounced, usePaged } from "../hooks";
import { useSession } from "../session";

export function Patients() {
  const { api } = useSession();
  const panel = usePanel();
  const [q, setQ] = useState("");
  const term = useDebounced(q.trim());
  const list = usePaged((cursor) => api.patients(term, cursor), [api, term, panel.dataVersion]);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Patients</h1>
          <p className="muted">Look someone up when they call in.</p>
        </div>
      </div>

      <div className="toolbar">
        <input id="search" className="search search-lg" type="search" autoFocus
          placeholder="Search by name, phone or patient ID   ( / )"
          value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search patients" />
      </div>

      {list.loading ? <Spinner /> : list.error ? <ErrorState message={list.error} onRetry={list.reload} /> : list.items.length === 0 ? (
        <EmptyState icon="🔍" title="No patients found" hint="Check the spelling, or try the phone number." />
      ) : (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Patient</th><th>Phone</th><th>Programs</th><th>Open tasks</th></tr></thead>
            <tbody>
              {list.items.map(({ patient: p, enrollments, visible_tasks }) => {
                const open = visible_tasks.filter((t) => t.status === "open" || t.status === "in_progress").length;
                return (
                  <tr key={p.patient_id} className="row-click" tabIndex={0}
                    onClick={() => panel.open(p.patient_id)} onKeyDown={(e) => e.key === "Enter" && panel.open(p.patient_id)}>
                    <td>
                      <strong>{patientName(p)}</strong>
                      <div className="muted">{p.age} · {p.gender} · {p.patient_id}</div>
                    </td>
                    <td className="nowrap">{fmtPhone(p.phone)}</td>
                    <td>
                      <div className="chips">
                        {enrollments.length === 0 && <span className="muted">—</span>}
                        {enrollments.map((e) => <TierBadge key={e.program_id} tier={e.tier} />)}
                      </div>
                    </td>
                    <td>{open > 0 ? <Badge tone="blue">{open} open</Badge> : <span className="muted">None</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="table-foot">
            <span className="muted">{list.items.length} shown{list.hasMore ? " · more available" : ""}</span>
            {list.hasMore && <button className="btn" onClick={list.loadMore} disabled={list.loadingMore}>{list.loadingMore ? "Loading…" : "Load more"}</button>}
          </div>
        </div>
      )}
    </div>
  );
}
