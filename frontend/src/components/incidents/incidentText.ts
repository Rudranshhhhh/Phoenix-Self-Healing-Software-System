import type { IncidentStatus, TimelineEntry, Validation } from "../../types/incident";

/** Phoenix is done with it: the clock stops. */
export function isFinished(status: IncidentStatus): boolean {
  return status === "validated" || status === "rejected" || status === "pr_opened";
}

/** Seconds from the first to the last timeline event. */
export function timelineSpanSecs(timeline: TimelineEntry[]): number {
  if (timeline.length === 0) return 0;
  const times = timeline.map((e) => new Date(e.at).getTime());
  return Math.max(0, (Math.max(...times) - Math.min(...times)) / 1000);
}

type Environment = Validation["environment"];

/** "Docker sandbox" / "Local sandbox" / "Sandbox", for labels. */
export function sandboxLabel(env: Environment): string {
  return env === "docker" ? "Docker sandbox" : env === "local" ? "Local sandbox" : "Sandbox";
}

/** Same, for the middle of a sentence ("in a local sandbox"). */
export function sandboxPhrase(env: Environment): string {
  return env === "docker" ? "Docker sandbox" : env === "local" ? "local sandbox" : "sandbox";
}
