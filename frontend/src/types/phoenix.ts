// ============================================================================
// Phoenix frontend — domain types
//
// These mirror the shapes the SDK reports and the Phoenix service returns.
// Everything the UI renders today comes from `src/mock/`; when the real API
// lands, only the modules under `src/mock/` need to change.
// ============================================================================

export type Severity = "low" | "medium" | "high" | "critical";

/** Where an incident is in the repair pipeline. */
export type RepairStage =
  | "open" // captured, nothing attempted
  | "reproducing" // agent is replaying the failing frame in a sandbox
  | "patching" // LLM is writing the patch
  | "testing" // your test suite is running against the patch
  | "awaiting_review" // patch is ready, needs a human yes
  | "pr_open" // pull request created
  | "declined" // human said no
  | "unfixable"; // agent could not reproduce or could not patch

// ---------------------------------------------------------------------------
// GitHub
// ---------------------------------------------------------------------------

export interface GithubUser {
  login: string;
  name: string;
  avatarUrl: string;
  company: string;
}

/** Result of scanning a repo's dependency manifests for phoenix-sdk. */
export type SdkScan =
  | { state: "pending" }
  | { state: "scanning" }
  | { state: "installed"; version: string; foundIn: string; line: number }
  | { state: "outdated"; version: string; latest: string; foundIn: string; line: number }
  | { state: "missing"; checked: string[] };

export interface Repository {
  id: number;
  owner: string;
  name: string;
  private: boolean;
  language: string;
  pushedAt: string; // ISO
  defaultBranch: string;
  description: string;
  scan: SdkScan;
}

// ---------------------------------------------------------------------------
// Incidents
// ---------------------------------------------------------------------------

export interface StackFrame {
  file: string;
  line: number;
  fn: string;
  code: string;
  /** True for the frame the agent believes caused the failure. */
  blame?: boolean;
}

export interface RequestContext {
  method: string;
  path: string;
  status: number;
  userAgent: string;
  releaseSha: string;
}

export interface PatchHunk {
  file: string;
  startLine: number;
  removed: string[];
  added: string[];
}

export interface ProposedFix {
  summary: string;
  reasoning: string;
  hunks: PatchHunk[];
  testsRun: number;
  testsPassed: number;
  branch: string;
  prNumber?: number;
}

export interface Incident {
  id: string;
  service: string;
  exception: string;
  message: string;
  severity: Severity;
  count: number;
  usersAffected: number;
  firstSeen: string; // ISO
  lastSeen: string; // ISO
  stage: RepairStage;
  frames: StackFrame[];
  request: RequestContext;
  /** Why the agent stopped, when the stage is `unfixable`. */
  note?: string;
  fix?: ProposedFix;
}
