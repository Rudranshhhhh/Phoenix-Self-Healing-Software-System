import { useEffect, useRef, useState } from "react";

export interface PollState<T> {
  data: T | null;
  error: Error | null;
  /** True only until the first response; later refreshes stay quiet. */
  loading: boolean;
}

/**
 * Fetch now, then again `intervalMs` after each response finishes, so requests
 * never overlap. Keeps the last good data through errors, pauses while the tab
 * is hidden, and refetches as soon as it is visible again.
 *
 * `fetcher` must be stable (a module function or a useCallback); a new fetcher
 * starts a fresh poll and clears the previous data.
 */
export function usePolling<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  intervalMs = 2500,
  enabled = true,
): PollState<T> {
  const [state, setState] = useState<PollState<T>>({ data: null, error: null, loading: enabled });
  const lastFetcher = useRef(fetcher);

  useEffect(() => {
    if (lastFetcher.current !== fetcher) {
      lastFetcher.current = fetcher;
      setState({ data: null, error: null, loading: enabled });
    }

    if (!enabled) {
      setState((prev) =>
        prev.data === null && prev.error === null && !prev.loading
          ? prev
          : { data: null, error: null, loading: false },
      );
      return;
    }

    let cancelled = false;
    let inFlight = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;

    const schedule = () => {
      if (cancelled || document.hidden) return; // resumed by onVisibility
      timer = setTimeout(tick, intervalMs);
    };

    const tick = async () => {
      timer = undefined;
      if (cancelled || document.hidden) return;

      const request = new AbortController();
      controller = request;
      inFlight = true;
      try {
        const data = await fetcher(request.signal);
        if (cancelled) return;
        setState({ data, error: null, loading: false });
      } catch (err) {
        if (cancelled || request.signal.aborted) return;
        const error = err instanceof Error ? err : new Error(String(err));
        setState((prev) => ({ data: prev.data, error, loading: false }));
      } finally {
        inFlight = false;
      }
      schedule();
    };

    const onVisibility = () => {
      if (document.hidden) {
        clearTimeout(timer);
        timer = undefined;
      } else if (!inFlight) {
        clearTimeout(timer);
        void tick();
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    void tick();

    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [fetcher, intervalMs, enabled]);

  return state;
}
