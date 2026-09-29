import { useState } from "react";
import { ApiError } from "../api";
import { RESOLUTION_LABEL, addDays } from "../format";
import { useSession } from "../session";
import type { Resolution, Task } from "../types";
import { Modal, useToast } from "./ui";

type Mode = "complete" | "decline" | "snooze" | null;

const RESOLUTIONS: Record<Task["task_type"], Resolution[]> = {
  scheduling: ["booked"],
  referral: ["referral_approved", "referral_not_indicated"],
};

const DECLINE_REASONS = [
  "Patient declined",
  "Already seen elsewhere",
  "Moved or changed provider",
  "Wrong number / cannot be reached",
  "Other",
];

const SNOOZE_REASONS = ["No answer", "Left voicemail", "Patient asked to call back", "Other"];

/**
 * The buttons for one task. `variant="primary"` shows only the single next step
 * (for dense table rows); `variant="full"` shows every option.
 */
export function TaskActions({ task, onChanged, variant = "full" }: {
  task: Task; onChanged: () => void; variant?: "primary" | "full";
}) {
  const { api, user, meta } = useSession();
  const toast = useToast();
  const [mode, setMode] = useState<Mode>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mine = task.assigned_to === user.id;

  async function run(fn: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setMode(null);
      toast("success", success);
      onChanged();
    } catch (e) {
      if (e instanceof ApiError && e.isConflict) {
        setMode(null);
        toast("error", "Someone else just updated this task. It has been refreshed, so please review it and try again.");
        onChanged();
      } else {
        setError(e instanceof Error ? e.message : "Something went wrong.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (task.status === "open") {
    return (
      <button className="btn btn-primary" disabled={busy}
        onClick={() => run(() => api.claim(task), "Task is yours. Take your time.")}>
        {busy ? "Claiming…" : "Take task"}
      </button>
    );
  }

  if (task.status === "in_progress" && !mine) {
    return <span className="muted">Being handled by {task.assigned_to ?? "someone else"}</span>;
  }

  if (task.status !== "in_progress") return null;

  return (
    <>
      <div className="btn-row">
        <button className="btn btn-success" onClick={() => setMode("complete")}>
          {task.task_type === "scheduling" ? "Booked ✓" : "Complete ✓"}
        </button>
        {variant === "full" && (
          <>
            <button className="btn" onClick={() => setMode("snooze")}>Call back later</button>
            <button className="btn btn-danger-outline" onClick={() => setMode("decline")}>Patient declined</button>
          </>
        )}
      </div>

      {mode === "complete" && (
        <CompleteModal task={task} busy={busy} error={error} onClose={() => setMode(null)}
          onSubmit={(r, note) => run(() => api.complete(task, r, note), "Task completed. Nice work.")} />
      )}
      {mode === "snooze" && (
        <SnoozeModal asOf={meta?.as_of_date} busy={busy} error={error} onClose={() => setMode(null)}
          onSubmit={(until, reason) => run(() => api.snooze(task, until, reason), "Task returned to the list for later.")} />
      )}
      {mode === "decline" && (
        <DeclineModal busy={busy} error={error} onClose={() => setMode(null)}
          onSubmit={(reason, days) => run(() => api.decline(task, reason, days), "Recorded. We will not ask again for a while.")} />
      )}
    </>
  );
}

function ErrorLine({ error }: { error: string | null }) {
  return error ? <p className="form-error" role="alert">{error}</p> : null;
}

function CompleteModal({ task, busy, error, onClose, onSubmit }: {
  task: Task; busy: boolean; error: string | null; onClose: () => void;
  onSubmit: (r: Resolution, note?: string) => void;
}) {
  const options = RESOLUTIONS[task.task_type];
  const [resolution, setResolution] = useState<Resolution>(options[0]);
  const [note, setNote] = useState("");
  return (
    <Modal title={`Complete: ${task.specialty}`} onClose={onClose}
      footer={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-success" disabled={busy} onClick={() => onSubmit(resolution, note.trim())}>
          {busy ? "Saving…" : "Mark complete"}
        </button>
      </>}>
      <fieldset className="choices">
        <legend>What happened?</legend>
        {options.map((r) => (
          <label key={r} className={`choice ${resolution === r ? "choice-on" : ""}`}>
            <input type="radio" name="resolution" checked={resolution === r} onChange={() => setResolution(r)} />
            {RESOLUTION_LABEL[r]}
          </label>
        ))}
      </fieldset>
      <label className="field">
        <span>Note (optional)</span>
        <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Appointment date, who you spoke with…" />
      </label>
      <ErrorLine error={error} />
    </Modal>
  );
}

function SnoozeModal({ asOf, busy, error, onClose, onSubmit }: {
  asOf?: string; busy: boolean; error: string | null; onClose: () => void;
  onSubmit: (until: string, reason: string) => void;
}) {
  const base = asOf ?? new Date().toISOString().slice(0, 10);
  const presets = [{ label: "Tomorrow", days: 1 }, { label: "In 3 days", days: 3 }, { label: "Next week", days: 7 }, { label: "In 2 weeks", days: 14 }];
  const [until, setUntil] = useState(addDays(base, 3));
  const [reason, setReason] = useState(SNOOZE_REASONS[0]);
  return (
    <Modal title="Call back later" onClose={onClose}
      footer={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={busy || until <= base} onClick={() => onSubmit(until, reason)}>
          {busy ? "Saving…" : "Save for later"}
        </button>
      </>}>
      <p className="muted">The task goes back on the shared list and reappears after this date.</p>
      <div className="chips" role="group" aria-label="Quick dates">
        {presets.map((p) => (
          <button key={p.days} type="button" className={`chip ${until === addDays(base, p.days) ? "chip-on" : ""}`}
            onClick={() => setUntil(addDays(base, p.days))}>{p.label}</button>
        ))}
      </div>
      <label className="field">
        <span>Or pick a date</span>
        <input type="date" value={until} min={addDays(base, 1)} onChange={(e) => setUntil(e.target.value)} />
      </label>
      <label className="field">
        <span>Reason</span>
        <select value={reason} onChange={(e) => setReason(e.target.value)}>
          {SNOOZE_REASONS.map((r) => <option key={r}>{r}</option>)}
        </select>
      </label>
      <ErrorLine error={error} />
    </Modal>
  );
}

function DeclineModal({ busy, error, onClose, onSubmit }: {
  busy: boolean; error: string | null; onClose: () => void; onSubmit: (reason: string, days: number) => void;
}) {
  const [reason, setReason] = useState(DECLINE_REASONS[0]);
  const [other, setOther] = useState("");
  const [days, setDays] = useState(90);
  const finalReason = reason === "Other" ? other.trim() : reason;
  return (
    <Modal title="Patient declined" onClose={onClose}
      footer={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-danger" disabled={busy || !finalReason} onClick={() => onSubmit(finalReason, days)}>
          {busy ? "Saving…" : "Confirm decline"}
        </button>
      </>}>
      <label className="field">
        <span>Reason</span>
        <select value={reason} onChange={(e) => setReason(e.target.value)}>
          {DECLINE_REASONS.map((r) => <option key={r}>{r}</option>)}
        </select>
      </label>
      {reason === "Other" && (
        <label className="field">
          <span>Tell us more</span>
          <input value={other} onChange={(e) => setOther(e.target.value)} autoFocus />
        </label>
      )}
      <fieldset className="choices choices-inline">
        <legend>Do not ask again for</legend>
        {[30, 60, 90, 180].map((d) => (
          <label key={d} className={`choice ${days === d ? "choice-on" : ""}`}>
            <input type="radio" name="days" checked={days === d} onChange={() => setDays(d)} />
            {d} days
          </label>
        ))}
      </fieldset>
      <ErrorLine error={error} />
    </Modal>
  );
}
