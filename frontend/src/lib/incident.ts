import type { Incident, IncidentError, IncidentStatus, StackFrame, TimelineEntry } from "../types/incident";
import { duration } from "./format";

/** Phoenix is still working on it (or waiting to open the PR). */
export function isActive(status: IncidentStatus): boolean {
  return status !== "rejected" && status !== "pr_opened";
}

export function blamedFrame(error: IncidentError): StackFrame | null {
  return error.frames.find((f) => f.blame) ?? null;
}

/** Diagnosis file, else blamed frame, else the last frame. */
export function blamedFile(incident: Incident | null): string | null {
  if (!incident) return null;
  const frames = incident.error.frames;
  return (
    incident.diagnosis?.suspect_file ??
    blamedFrame(incident.error)?.file ??
    (frames.length > 0 ? frames[frames.length - 1].file : null)
  );
}

/** When the incident entered `status` (last matching timeline entry), else `fallback`. */
export function stageStartMs(
  status: IncidentStatus,
  timeline: TimelineEntry[] | undefined,
  fallback: string,
): number {
  const entries = timeline?.filter((e) => e.status === status) ?? [];
  const at = entries.length > 0 ? entries[entries.length - 1].at : fallback;
  return new Date(at).getTime();
}

/** m:ss under an hour, then "3h 31m". */
export function stageClock(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s >= 3600) return duration(s);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
