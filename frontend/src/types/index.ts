// ============================================================================
// Phoenix Frontend — Shared TypeScript Types
// Mirrors the backend domain model exactly.
// ============================================================================

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type FailureType =
  | 'CONTAINER_DOWN'
  | 'HIGH_CPU'
  | 'HIGH_MEMORY'
  | 'DATABASE_UNREACHABLE'
  | 'REDIS_DOWN'
  | 'HEALTH_ENDPOINT_FAILURE'
  | 'REPEATED_RESTARTS'
  | 'UNKNOWN';

export type IncidentStatus =
  | 'DETECTED'
  | 'DIAGNOSING'
  | 'RECOVERING'
  | 'VERIFYING'
  | 'ESCALATED'
  | 'RESOLVED';

export type IncidentPhase =
  | 'DETECTED'
  | 'DIAGNOSED'
  | 'RECOVERY_STARTED'
  | 'RECOVERY_COMPLETED'
  | 'RECOVERY_FAILED'
  | 'VERIFIED'
  | 'VERIFICATION_FAILED'
  | 'ESCALATED'
  | 'RESOLVED';

export interface TimelineEvent {
  phase: IncidentPhase;
  message: string;
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface ServiceSnapshot {
  service: string;
  container_name: string;
  container_status: string;
  cpu_percent: number;
  memory_percent: number;
  memory_mb: number;
  restart_count: number;
  health_status?: string;
  health_latency_ms?: number;
  db_reachable?: boolean;
  redis_reachable?: boolean;
  log_errors: string[];
  collected_at: string;
}

export interface Incident {
  incident_id: string;
  service: string;
  container_name: string;
  failure_type: FailureType;
  severity: Severity;
  confidence_score: number;
  status: IncidentStatus;
  root_cause: string;
  grok_summary?: string;
  grok_recommendations?: string[];
  metrics_snapshot: ServiceSnapshot;
  recovery_strategy?: string;
  retry_count: number;
  resolved: boolean;
  detected_at: string;
  diagnosed_at?: string;
  recovery_started_at?: string;
  verification_completed_at?: string;
  resolved_at?: string;
  timeline: TimelineEvent[];
}

export interface MetricSnapshot {
  service: string;
  container_name?: string;
  container_status?: string;
  cpu_percent: number;
  memory_percent: number;
  memory_mb?: number;
  restart_count?: number;
  health_status?: string;
  health_latency_ms?: number;
  timestamp?: string;
  collected_at?: string;
}

export interface ContainerState {
  service: string;
  container_name?: string;
  container_status: string;
  cpu_percent: number;
  memory_percent: number;
  memory_mb: number;
  restart_count: number;
  health_status?: string;
  last_seen?: string;
}

export interface DashboardSummary {
  total_incidents: number;
  active_incidents: number;
  resolved_incidents: number;
  escalated_incidents: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
