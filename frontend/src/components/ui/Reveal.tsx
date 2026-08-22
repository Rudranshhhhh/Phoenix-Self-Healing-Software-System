import type { ReactNode } from "react";
import { useReveal } from "../../hooks/useReveal";
import { cn } from "../../lib/cn";

/** Content that rises into place the first time it is scrolled to. */
export function Reveal({
  children,
  delay = 0,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
  as?: "div" | "section" | "li" | "tr";
}) {
  const { ref, shown } = useReveal<HTMLDivElement>();
  return (
    <Tag
      ref={ref as never}
      data-shown={shown}
      className={cn("reveal", className)}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </Tag>
  );
}
