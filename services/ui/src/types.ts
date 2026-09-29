// Mirrors services/worklist_api/schemas.py.

export type Role = "scheduler" | "clinical" | "admin";
export type TaskType = "scheduling" | "referral";
export type TaskStatus = "open" | "in_progress" | "completed" | "declined" | "closed";
export type Resolution = "booked" | "referral_approved" | "referral_not_indicated";

export interface Patient {
  patient_id: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender: string;
  phone: string;
  language: string;
  pcp_provider_name: string | null;
  age: number;
}

export interface Enrollment {
  program_id: string;
  program_version: number;
  tier: string;
  evaluated_at: string;
}

export interface Need {
  program_id: string;
  specialty: string;
  cadence_days: number;
  last_visit_date: string | null;
  due_date: string | null;
  has_upcoming: boolean;
}

export interface Task {
  task_id: number;
  patient_id: string;
  program_id: string;
  tier: string;
  specialty: string;
  task_type: TaskType;
  status: TaskStatus;
  due_date: string | null;
  days_overdue: number | null;
  snooze_until: string | null;
  resolution: string | null;
  assigned_to: string | null;
  program_version: number;
  version: number;
  created_at: string;
  updated_at: string;
  patient: Patient | null;
}

export interface PatientWithContext {
  patient: Patient;
  enrollments: Enrollment[];
  visible_tasks: Task[];
}

export interface PatientDetail {
  patient: Patient;
  enrollments: Enrollment[];
  needs: Need[];
  visible_tasks: Task[];
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface AuditEntry {
  event_id: string;
  occurred_at: string;
  actor: string;
  action: string;
  entity: string;
  patient_id: string | null;
  before_json: string;
  after_json: string;
  request_id: string;
  result: string;
}

export interface Meta {
  as_of_date: string;
  last_sync_finished_at: string | null;
  task_counts_by_status: Record<string, number>;
}

export interface SyncRun {
  run_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  counts_json: string;
  watermarks_json: string;
}

export interface Program {
  program_id: string;
  version: number;
  definition_json: string;
  active: boolean;
}

export interface TaskFilters {
  status?: string[];
  specialty?: string;
  task_type?: string;
  program?: string;
  assigned_to?: string;
  overdue?: boolean;
}
