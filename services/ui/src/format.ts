import type { Resolution, TaskStatus, TaskType } from "./types";

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(DAY.test(iso) ? `${iso}T00:00:00` : iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function fmtDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.replace(" ", "T"));
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

export function fmtPhone(raw: string): string {
  const d = raw.replace(/\D/g, "");
  const n = d.length === 11 && d.startsWith("1") ? d.slice(1) : d;
  return n.length === 10 ? `(${n.slice(0, 3)}) ${n.slice(3, 6)}-${n.slice(6)}` : raw;
}

export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const TYPE_LABEL: Record<TaskType, string> = {
  scheduling: "Schedule visit",
  referral: "Needs referral",
};

export const STATUS_LABEL: Record<TaskStatus, string> = {
  open: "To do",
  in_progress: "In progress",
  completed: "Done",
  declined: "Declined",
  closed: "Closed",
};

export const RESOLUTION_LABEL: Record<Resolution, string> = {
  booked: "Appointment booked",
  referral_approved: "Referral approved",
  referral_not_indicated: "Referral not needed",
};

export const ROLE_LABEL: Record<string, string> = {
  scheduler: "Front Desk",
  clinical: "Clinical",
  admin: "Admin",
};

export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export const patientName = (p?: { first_name: string; last_name: string } | null, fallback = "Unknown patient") =>
  p ? `${p.first_name} ${p.last_name}` : fallback;
