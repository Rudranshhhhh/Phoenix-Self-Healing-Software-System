import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "../../lib/cn";

type Tone = "primary" | "quiet" | "ghost" | "danger";

const TONES: Record<Tone, string> = {
  primary: "bg-ink text-white border-ink hover:bg-body hover:border-body",
  quiet: "bg-surface text-ink border-line hover:bg-subtle",
  ghost: "bg-transparent text-body border-transparent hover:bg-subtle hover:text-ink",
  danger: "bg-transparent text-fail border-fail/40 hover:bg-del-bg hover:border-fail",
};

const SIZES = {
  sm: "h-8 px-3 text-[12.5px]",
  md: "h-10 px-4 text-[14px]",
  lg: "h-12 px-6 text-[15px]",
};

const SHELL =
  "inline-flex items-center justify-center gap-2 rounded-box border font-medium no-underline transition-colors duration-150 " +
  "disabled:opacity-40 disabled:pointer-events-none whitespace-nowrap";

interface Shared {
  tone?: Tone;
  size?: keyof typeof SIZES;
  children: ReactNode;
  className?: string;
}

export function Button({
  tone = "quiet",
  size = "md",
  className,
  children,
  ...rest
}: Shared & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={cn(SHELL, TONES[tone], SIZES[size], className)} {...rest}>
      {children}
    </button>
  );
}

export function ButtonLink({
  to,
  tone = "quiet",
  size = "md",
  className,
  children,
}: Shared & { to: string }) {
  return (
    <Link to={to} className={cn(SHELL, TONES[tone], SIZES[size], className)}>
      {children}
    </Link>
  );
}
