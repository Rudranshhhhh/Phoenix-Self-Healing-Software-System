import { useCallback } from "react";
import { getIncident, getIncidents } from "../api/phoenix";
import type { IncidentSummary } from "../types/incident";
import { usePolling } from "./usePolling";

// Polls the Phoenix API. Not to be confused with the legacy hooks/useIncidents.ts.

const NO_INCIDENTS: IncidentSummary[] = [];

export function useIncidentList() {
  const { data, error, loading } = usePolling(getIncidents);
  return { incidents: data?.items ?? NO_INCIDENTS, error, loading };
}

/** The full incident, polled while `id` is set. */
export function useIncident(id: string | null) {
  const fetcher = useCallback(
    (signal: AbortSignal) =>
      id === null ? Promise.reject(new Error("No incident selected")) : getIncident(id, signal),
    [id],
  );
  const { data, error, loading } = usePolling(fetcher, 2500, id !== null);
  return { incident: data, error, loading };
}
