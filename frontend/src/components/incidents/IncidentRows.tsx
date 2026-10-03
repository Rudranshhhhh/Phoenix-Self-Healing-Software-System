import { Link } from "react-router-dom";
import type { IncidentSummary, SourceType } from "../../types/incident";
import { since } from "../../lib/format";
import { statusLabel } from "../../lib/status";
import { StatusIcon } from "./StatusIcon";
import { MiniPipeline } from "./MiniPipeline";

const FOUND_IN: Record<SourceType, string> = {
  github_actions: "Found in CI",
  docker_runtime: "Found in a running container",
};

export function IncidentRows({ incidents }: { incidents: IncidentSummary[] }) {
  const n = incidents.length;
  return (
    <div className="overflow-hidden rounded-box border border-line bg-surface">
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 border-b border-line bg-subtle px-4 py-3 text-[14px] text-muted">
        <span className="font-semibold text-body">
          {n} {n === 1 ? "incident" : "incidents"}
        </span>
        <span>Recently updated first</span>
      </div>
      <ul>
        {incidents.map((incident) => {
          const label = statusLabel(incident.status);
          return (
            <li key={incident.id} className="border-t border-line first:border-t-0">
              <Link
                to={`/app/incidents/${incident.id}`}
                className="flex items-start gap-3 px-4 py-3.5 text-body no-underline hover:bg-subtle"
              >
                <StatusIcon status={incident.status} className="mt-1" />

                <span className="block min-w-0 flex-1">
                  <span className="block text-[16px] leading-[1.4] [overflow-wrap:anywhere]">
                    <span className="font-semibold text-ink">{incident.exception_type}:</span>{" "}
                    {incident.message}
                  </span>
                  <span className="mt-0.5 flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5 text-[13px] text-muted">
                    <span className="font-dot text-[15px] font-bold text-ink">{incident.id}</span>
                    <span>
                      {FOUND_IN[incident.source_type]}, updated {since(incident.updated_at)}
                    </span>
                  </span>
                  {/* phone: pipeline + label under the meta line */}
                  <span className="mt-2 flex items-center gap-2 sm:hidden">
                    <MiniPipeline status={incident.status} />
                    <span className="text-[13px] text-muted">{label}</span>
                  </span>
                </span>

                {/* desktop: label over pipeline on the right */}
                <span className="hidden shrink-0 flex-col items-end gap-1.5 pt-[3px] text-[13px] text-muted sm:flex">
                  <span>{label}</span>
                  <MiniPipeline status={incident.status} />
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
