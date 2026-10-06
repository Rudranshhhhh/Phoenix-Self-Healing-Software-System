import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "../ui/Button";

export const TOUR_INCIDENT = "INC-007";
export const TOUR_URL = `/app/incidents/${TOUR_INCIDENT}?tour=1`;

type TourStep = { target: string; title: string; body: string };

const TOUR_STEPS: TourStep[] = [
  { target: "arc", title: "Where Phoenix is", body: "The six steps of a fix. The orange glow means Phoenix is working right now." },
  { target: "root-cause", title: "Root cause", body: "What broke and why, with the file and line Phoenix blames." },
  { target: "diff", title: "The patch", body: "The change Phoenix wrote. Usually a line or two, nothing else in the file moves." },
  { target: "validation", title: "Sandbox tests", body: "Your tests, run against the patch. If any fail, Phoenix stops and leaves your code alone." },
  { target: "pr", title: "Pull request", body: "The fix arrives as a PR on its own branch. A person still reviews and merges it." },
];

type Rect = { top: number; left: number; width: number; height: number };

function findTarget(target: string) {
  const el = document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  return el && el.getClientRects().length > 0 ? el : null;
}

export function TourOverlay({ onClose }: { onClose: () => void }) {
  const [steps, setSteps] = useState<TourStep[] | null>(null);
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);

  // wait for the page data, then keep only steps whose target is on screen
  useEffect(() => {
    let tries = 0;
    let t = 0;
    const find = () => {
      const avail = TOUR_STEPS.filter((s) => findTarget(s.target));
      if (avail.length === TOUR_STEPS.length || tries >= 10) {
        setSteps(avail);
        return;
      }
      tries += 1;
      t = window.setTimeout(find, 300);
    };
    t = window.setTimeout(find, 100);
    return () => window.clearTimeout(t);
  }, []);

  useEffect(() => {
    if (steps && steps.length === 0) onClose();
  }, [steps, onClose]);

  const step = steps?.[i];

  const measure = useCallback(() => {
    if (!step) return;
    const el = findTarget(step.target);
    if (!el) return;
    const r = el.getBoundingClientRect();
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
  }, [step]);

  useEffect(() => {
    if (!step) return;
    findTarget(step.target)?.scrollIntoView({ block: "center", behavior: "smooth" });
    const t = window.setTimeout(measure, 450);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [step, measure]);

  useEffect(() => {
    const n = steps?.length ?? 0;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") setI((v) => Math.min(v + 1, n - 1));
      else if (e.key === "ArrowLeft") setI((v) => Math.max(v - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [steps, onClose]);

  if (!steps || !step || !rect) return null;

  const pad = 6;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const mobile = vw < 640;
  const cardW = Math.min(320, vw - 32);
  const below = rect.top + rect.height + pad + 12;
  const cardTop = below + 190 < vh ? below : Math.max(16, rect.top - pad - 12 - 190);
  const cardLeft = Math.min(Math.max(16, rect.left), vw - cardW - 16);
  const tall = rect.height > vh * 0.6;
  const lastStep = i === steps.length - 1;

  return createPortal(
    <div className="fixed inset-0 z-50 print:hidden">
      <div className="absolute inset-0 bg-ink/15" onClick={onClose} />
      <div
        aria-hidden
        className="pointer-events-none fixed rounded-box border-2 border-ink"
        style={{ top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }}
      />
      <div
        role="dialog"
        aria-label={`Tour, step ${i + 1} of ${steps.length}`}
        className={`fixed rounded-box border border-line bg-surface p-4 ${mobile ? "inset-x-4 bottom-4" : ""}`}
        style={
          mobile
            ? undefined
            : tall
              ? { right: 16, bottom: 16, width: cardW }
              : { top: cardTop, left: cardLeft, width: cardW }
        }
      >
        <p className="font-mono text-[12px] text-muted">
          {i + 1} / {steps.length}
        </p>
        <p className="mt-1 text-[15px] font-medium text-ink">{step.title}</p>
        <p className="mt-1 text-[14px] leading-[1.55] text-body">{step.body}</p>
        <div className="mt-4 flex items-center justify-between gap-2">
          <button type="button" onClick={onClose} className="text-[13px] font-medium text-muted hover:text-ink">
            Skip tour
          </button>
          <div className="flex gap-2">
            <Button size="sm" tone="ghost" onClick={() => setI((v) => v - 1)} disabled={i === 0}>
              Back
            </Button>
            {lastStep ? (
              <Button size="sm" tone="primary" onClick={onClose}>
                Done
              </Button>
            ) : (
              <Button size="sm" tone="primary" onClick={() => setI((v) => v + 1)}>
                Next
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
