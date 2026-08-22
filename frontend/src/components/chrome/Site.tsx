import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { GithubMark, Wordmark } from "../brand/Wordmark";
import { cn } from "../../lib/cn";

const NAV = [
  { to: "/#how", label: "How it works" },
  { to: "/#install", label: "Install" },
  { to: "/#limits", label: "Limits" },
];

export function SiteHeader() {
  const [lifted, setLifted] = useState(false);

  useEffect(() => {
    const onScroll = () => setLifted(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-40 transition-colors duration-300",
        lifted ? "border-b border-ash-800 bg-ash-950/88 backdrop-blur-md" : "border-b border-transparent",
      )}
    >
      <div className="mx-auto flex h-16 max-w-[1180px] items-center gap-8 px-5 sm:px-8">
        <Link to="/" aria-label="Phoenix home" className="shrink-0">
          <Wordmark />
        </Link>

        <nav className="hidden items-center gap-7 md:flex">
          {NAV.map((item) => (
            <a
              key={item.to}
              href={item.to}
              className="font-mono text-[11px] uppercase tracking-[0.13em] text-bone-3 transition-colors hover:text-bone"
            >
              {item.label}
            </a>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-4">
          <NavLink
            to="/app"
            className="hidden font-mono text-[11px] uppercase tracking-[0.13em] text-bone-3 transition-colors hover:text-bone sm:inline"
          >
            Dashboard
          </NavLink>
          <Link
            to="/connect"
            className="inline-flex h-9 items-center gap-2 rounded-sm border border-ash-700 bg-ash-850 px-3.5 text-[13px] text-bone transition-colors hover:border-ash-600 hover:bg-ash-800"
          >
            <GithubMark size={14} />
            Connect GitHub
          </Link>
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t border-ash-800 bg-ash-925">
      <div className="mx-auto max-w-[1180px] px-5 py-12 sm:px-8">
        <div className="flex flex-col gap-10 md:flex-row md:items-start md:justify-between">
          <div className="max-w-sm">
            <Wordmark />
            <p className="mt-3 text-[14px] leading-relaxed text-bone-3">
              A traceback goes in. A reviewed pull request comes out. Nothing in between happens without
              someone saying yes.
            </p>
          </div>

          <div className="flex gap-14">
            <FooterColumn
              title="Product"
              links={[
                { label: "How it works", href: "/#how" },
                { label: "Install the SDK", href: "/#install" },
                { label: "What it won't do", href: "/#limits" },
              ]}
            />
            <FooterColumn
              title="Project"
              links={[
                { label: "Dashboard", href: "/app" },
                { label: "Connect a repo", href: "/connect" },
              ]}
            />
          </div>
        </div>

        <hr className="rule mt-10" />
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="font-mono text-[11px] text-bone-4">
            Phoenix · self-healing software system
          </span>
          <span className="ml-auto font-mono text-[11px] text-bone-4">
            The metrics and incidents on this build are simulated.
          </span>
        </div>
      </div>
    </footer>
  );
}

function FooterColumn({ title, links }: { title: string; links: Array<{ label: string; href: string }> }) {
  return (
    <div>
      <span className="ledger-label">{title}</span>
      <ul className="mt-3 space-y-2">
        {links.map((l) => (
          <li key={l.label}>
            <a href={l.href} className="text-[14px] text-bone-2 transition-colors hover:text-bone">
              {l.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
