import { Link } from "react-router-dom";
import { Wordmark } from "../brand/Wordmark";

function LiveIndicator({ live }: { live: boolean }) {
  return (
    <span className="ml-auto mt-[3px] flex shrink-0 items-center gap-2 text-sm text-body">
      <span
        aria-hidden="true"
        className={live ? "size-2 rounded-full bg-pass" : "size-2 rounded-full border-[1.5px] border-muted"}
      />
      {live ? "Live" : "Offline"}
    </span>
  );
}

/** Slim chrome for the monitoring view. Left group wraps on narrow screens; Live stays top-right. */
export function AppHeader({
  owner,
  repo,
  branch,
  live,
}: {
  owner: string;
  repo: string;
  branch: string;
  release: string;
  live: boolean;
  user?: string;
}) {
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex max-w-[1200px] items-start gap-x-5 px-4 py-4 sm:px-6">
        <div className="flex min-w-0 flex-wrap items-center gap-x-5 gap-y-2">
          <Link to="/" aria-label="Phoenix home">
            <Wordmark />
          </Link>
          <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm text-body">
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.3"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-muted"
            >
              <path d="M3.5 2.5h8a1 1 0 0 1 1 1v9.5h-8.5a1 1 0 0 1-1-1z" />
              <path d="M3.5 11.5a1 1 0 0 1 1-1h8" />
            </svg>
            <span className="[overflow-wrap:anywhere]">
              {owner} / <span className="font-semibold text-ink">{repo}</span>
            </span>
            <span className="inline-flex items-center gap-1 rounded-box border border-line bg-subtle px-[7px] font-mono text-xs leading-5 text-body">
              <svg
                width="12"
                height="12"
                viewBox="0 0 16 16"
                aria-hidden="true"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.3"
                strokeLinecap="round"
                className="text-muted"
              >
                <circle cx="4.5" cy="3.5" r="1.7" />
                <circle cx="4.5" cy="12.5" r="1.7" />
                <circle cx="11.5" cy="5" r="1.7" />
                <path d="M4.5 5.2v5.6M11.5 6.7c0 3-7 2.5-7 4.1" />
              </svg>
              {branch}
            </span>
          </div>
          <Link to="/connect" className="text-sm text-body hover:text-ink">
            Switch repository
          </Link>
        </div>
        <LiveIndicator live={live} />
      </div>
    </header>
  );
}
