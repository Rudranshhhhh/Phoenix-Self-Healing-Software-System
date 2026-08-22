import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "../../lib/cn";

type Tone = "primary" | "quiet" | "ghost" | "danger";

const TONES: Record<Tone, string> = {
  primary:
    "bg-sodium text-ash-950 border-sodium hover:bg-[#ffc648] hover:border-[#ffc648] active:translate-y-px font-semibold",
  quiet: "bg-ash-850 text-bone border-ash-700 hover:bg-ash-800 hover:border-ash-600",
  ghost: "bg-transparent text-bone-2 border-transparent hover:text-bone hover:bg-ash-850",
  danger: "bg-transparent text-brick border-brick/40 hover:bg-brick/10 hover:border-brick/70",
};

const SIZES = {
  sm: "h-8 px-3 text-[12.5px]",
  md: "h-10 px-4 text-[14px]",
  lg: "h-12 px-6 text-[15px]",
};

const SHELL =
  "inline-flex items-center justify-center gap-2 rounded-sm border transition-[background-color,border-color,color,transform] duration-150 " +
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
