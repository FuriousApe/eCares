import { fmtDate, STATUS_LABEL, titleCase } from "../format";
import { useSession } from "../session";
import type { Task } from "../types";
import { Badge, type Tone } from "./ui";

const TIER_TONE: Record<string, Tone> = {
  high_risk: "red",
  high_priority: "red",
  moderate: "amber",
  standard: "neutral",
  low_risk: "green",
  unmonitored: "purple",
};

export const TierBadge = ({ tier }: { tier: string }) => <Badge tone={TIER_TONE[tier] ?? "neutral"}>{titleCase(tier)}</Badge>;

/** Due date, with a loud "N days overdue" when it applies. */
export function DueLabel({ task }: { task: Task }) {
  if (task.days_overdue && task.days_overdue > 0) {
    return (
      <span className="due-late">
        {fmtDate(task.due_date)} <Badge tone="red">{task.days_overdue} days overdue</Badge>
      </span>
    );
  }
  return <span>{task.due_date ? fmtDate(task.due_date) : "No date"}</span>;
}

export function StatusBadge({ task }: { task: Task }) {
  const { user } = useSession();
  const mine = task.assigned_to === user.id;
  const tone: Tone = task.status === "open" ? "neutral" : task.status === "in_progress" ? (mine ? "blue" : "amber") : task.status === "completed" ? "green" : "neutral";
  return (
    <Badge tone={tone}>
      {task.status === "in_progress" ? (mine ? "Yours" : `With ${task.assigned_to ?? "someone"}`) : STATUS_LABEL[task.status]}
    </Badge>
  );
}
