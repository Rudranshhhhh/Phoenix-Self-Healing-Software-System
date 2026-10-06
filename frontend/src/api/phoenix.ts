import type { Incident, IncidentListResponse } from "../types/incident";

// ---------------------------------------------------------------------------
// Phoenix API client. In dev BASE is empty, so requests go to /api on the
// Vite server and its proxy forwards them to phoenix-api on port 8000.
// ---------------------------------------------------------------------------

const BASE: string = import.meta.env.VITE_API_URL ?? "";

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`GET ${path} failed with ${response.status} ${response.statusText}`.trim());
  }
  return (await response.json()) as T;
}

export function getIncidents(signal?: AbortSignal): Promise<IncidentListResponse> {
  return getJson("/api/incidents?page_size=100", signal);
}

/** Starts a simulated run (POST /api/demo/run). If one is already running (409), returns its id. */
export async function runDemo(): Promise<{ incident_id: string }> {
  const response = await fetch(`${BASE}/api/demo/run`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (response.ok || response.status === 409) {
    const body = (await response.json()) as { incident_id?: string };
    if (body.incident_id) return { incident_id: body.incident_id };
  }
  throw new Error(`POST /api/demo/run failed with ${response.status} ${response.statusText}`.trim());
}

export function getIncident(id: string, signal?: AbortSignal): Promise<Incident> {
  return getJson(`/api/incidents/${encodeURIComponent(id)}`, signal);
}
