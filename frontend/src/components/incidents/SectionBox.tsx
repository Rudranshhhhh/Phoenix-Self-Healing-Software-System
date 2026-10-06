import type { ReactNode } from "react";

/** GitHub-style box: subtle header bar with title + optional meta, body below. */
export function SectionBox({
  title,
  meta,
  tour,
  children,
}: {
  title: string;
  meta?: ReactNode;
  /** data-tour anchor for the demo tour */
  tour?: string;
  children: ReactNode;
}) {
  return (
    <section data-tour={tour} className="overflow-hidden rounded-box border border-line bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 border-b border-line bg-subtle px-4 py-2.5">
        <h3 className="text-[14px] font-semibold text-ink">{title}</h3>
        {meta && <span className="text-[12px] text-muted">{meta}</span>}
      </div>
      {children}
    </section>
  );
}
