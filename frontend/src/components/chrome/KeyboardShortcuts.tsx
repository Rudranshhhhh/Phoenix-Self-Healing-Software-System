import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { TOUR_URL } from "../tour/TourOverlay";

const LIST = [
  { keys: ["?"], label: "Show this list" },
  { keys: ["g", "h"], label: "Go to Home" },
  { keys: ["g", "d"], label: "Go to the dashboard" },
  { keys: ["t"], label: "Start the demo tour" },
  { keys: ["Esc"], label: "Close" },
];

function isTyping(t: EventTarget | null) {
  const el = t as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}

export function KeyboardShortcuts() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const gAt = useRef(0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key === "?") {
        e.preventDefault();
        setOpen((o) => !o);
        return;
      }
      if (e.key === "g") {
        gAt.current = Date.now();
        return;
      }
      const afterG = Date.now() - gAt.current < 1000;
      if (afterG && e.key === "h") {
        gAt.current = 0;
        setOpen(false);
        navigate("/");
      } else if (afterG && e.key === "d") {
        gAt.current = 0;
        setOpen(false);
        navigate("/app");
      } else if (e.key === "t") {
        setOpen(false);
        navigate(TOUR_URL);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 print:hidden">
      <div className="absolute inset-0 bg-ink/15" onClick={() => setOpen(false)} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="kbd-title"
        className="relative w-full max-w-[360px] rounded-box border border-line bg-surface p-5"
      >
        <p id="kbd-title" className="text-[15px] font-medium text-ink">
          Keyboard shortcuts
        </p>
        <ul className="mt-3 divide-y divide-line">
          {LIST.map((s) => (
            <li key={s.label} className="flex items-center justify-between gap-4 py-2 text-[14px] text-body">
              <span>{s.label}</span>
              <span className="flex gap-1">
                {s.keys.map((k) => (
                  <kbd
                    key={k}
                    className="min-w-[1.6rem] rounded-box border border-line bg-code px-1.5 py-0.5 text-center font-mono text-[12px] text-ink"
                  >
                    {k}
                  </kbd>
                ))}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-[12.5px] text-muted">Shortcuts don't fire while you're typing.</p>
      </div>
    </div>
  );
}
