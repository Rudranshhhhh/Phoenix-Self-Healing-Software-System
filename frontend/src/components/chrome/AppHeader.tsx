import { Link } from "react-router-dom";
import { ChevronsUpDown, GitBranch } from "lucide-react";
import { Mark } from "../brand/Wordmark";
import { Chip, Dot, Label } from "../ui/Primitives";

/** Slim chrome for the monitoring view. Deliberately quieter than the site header. */
export function AppHeader({
  owner,
  repo,
  branch,
  release,
  live,
  user,
}: {
  owner: string;
  repo: string;
  branch: string;
  release: string;
  live: boolean;
  user?: string;
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-ash-800 bg-ash-950/92 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[1420px] items-center gap-4 px-4 sm:px-6">
        <Link to="/" aria-label="Phoenix home" className="shrink-0 text-bone">
          <Mark size={20} />
        </Link>

        <span aria-hidden className="h-4 w-px bg-ash-700" />

        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate font-mono text-[13px] text-bone-3">
            {owner}/<span className="font-medium text-bone">{repo}</span>
          </span>
          <span className="hidden items-center gap-1 font-mono text-[11px] text-bone-4 sm:flex">
            <GitBranch size={11} />
            {branch}
          </span>
        </span>

        <Link
          to="/connect"
          className="hidden shrink-0 items-center gap-1 font-mono text-[10.5px] uppercase tracking-[0.12em] text-bone-4 transition-colors hover:text-bone md:flex"
        >
          <ChevronsUpDown size={11} />
          Switch
        </Link>

        <div className="ml-auto flex items-center gap-3 sm:gap-5">
          <Chip className="hidden sm:inline-flex">{release}</Chip>
          <span className="flex items-center gap-2">
            <Dot tone={live ? "healthy" : "offline"} pulse={live} />
            <Label className={live ? "text-jade" : "text-bone-4"}>
              {live ? "Live · 1.5s" : "No reports"}
            </Label>
          </span>
          {user && (
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-xs border border-ash-700 bg-ash-850 font-mono text-[10.5px] text-bone-2">
              {user.slice(0, 2).toUpperCase()}
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
