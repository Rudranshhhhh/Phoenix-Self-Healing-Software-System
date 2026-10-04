import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { GithubMark, Wordmark } from "../brand/Wordmark";
import { cn } from "../../lib/cn";

const NAV = [
  { to: "/#how", label: "How it works" },
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
        "sticky top-0 z-40 border-b transition-colors duration-300",
        lifted ? "border-line bg-page/90 backdrop-blur-md" : "border-transparent bg-page",
      )}
    >
      <div className="mx-auto flex h-16 max-w-[1200px] items-center gap-8 px-4 sm:px-6">
        <Link to="/" aria-label="Phoenix home" className="shrink-0">
          <Wordmark />
        </Link>

        <nav className="hidden items-center gap-6 md:flex">
          {NAV.map((item) => (
            <a key={item.to} href={item.to} className="text-[14px] text-muted transition-colors hover:text-ink">
              {item.label}
            </a>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-4">
          <NavLink to="/app" className="hidden text-[14px] text-muted transition-colors hover:text-ink sm:inline">
            Dashboard
          </NavLink>
          <Link
            to="/connect"
            className="inline-flex h-9 items-center gap-2 rounded-box border border-line bg-surface px-3.5 text-[13px] font-medium text-ink transition-colors hover:bg-subtle"
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
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto max-w-[1200px] px-4 py-12 sm:px-6">
        <div className="flex flex-col gap-10 md:flex-row md:items-start md:justify-between">
          <div className="max-w-sm">
            <Wordmark />
            <p className="mt-3 text-[14px] leading-relaxed text-muted">
              A failing CI run goes in. A tested pull request comes out. Nothing merges without someone saying yes.
            </p>
          </div>

          <div className="flex gap-14">
            <FooterColumn
              title="Product"
              links={[
                { label: "How it works", href: "/#how" },
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

        <div className="mt-10 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-4 text-[12px] text-muted">
          <span>Phoenix · self-healing software system</span>
          <span className="sm:ml-auto">The incidents on this build are simulated.</span>
        </div>
      </div>
    </footer>
  );
}

function FooterColumn({ title, links }: { title: string; links: Array<{ label: string; href: string }> }) {
  return (
    <div>
      <span className="text-[13px] font-semibold text-ink">{title}</span>
      <ul className="mt-3 list-none space-y-2 p-0">
        {links.map((l) => (
          <li key={l.label}>
            <a href={l.href} className="text-[14px] text-body no-underline transition-colors hover:text-ink">
              {l.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
