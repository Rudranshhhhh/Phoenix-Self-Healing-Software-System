import type { ComponentProps } from "react";
import type { Chip } from "../components/ui/Primitives";
import type { IncidentStatus } from "../types/incident";

export type ChipTone = NonNullable<ComponentProps<typeof Chip>["tone"]>;

const LABELS: Record<IncidentStatus, string> = {
  detected: "Detected",
  diagnosing: "Diagnosing",
  fix_proposed: "Fix proposed",
  validating: "Validating",
  validated: "Validated",
  rejected: "Rejected",
  pr_opened: "PR opened",
};

// Same tones the old repair stages used: open → brick, agent working → iris,
// waiting on a human → sodium, PR open → jade, declined → neutral.
const TONES: Record<IncidentStatus, ChipTone> = {
  detected: "brick",
  diagnosing: "iris",
  fix_proposed: "iris",
  validating: "iris",
  validated: "sodium",
  rejected: "neutral",
  pr_opened: "jade",
};

export function statusLabel(status: IncidentStatus): string {
  return LABELS[status];
}

export function statusTone(status: IncidentStatus): ChipTone {
  return TONES[status];
}
