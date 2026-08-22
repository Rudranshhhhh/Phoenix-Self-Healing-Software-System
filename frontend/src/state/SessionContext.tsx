import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { GithubUser, Repository } from "../types/phoenix";
import { MOCK_USER } from "../mock/repos";

// ---------------------------------------------------------------------------
// Who is signed in and which repository they are watching. Persisted to
// sessionStorage so a refresh on the dashboard doesn't bounce you to sign-in.
// ---------------------------------------------------------------------------

const KEY = "phoenix.session";

interface Persisted {
  user: GithubUser | null;
  repo: Repository | null;
}

function read(): Persisted {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw) return JSON.parse(raw) as Persisted;
  } catch {
    // A corrupt or unavailable store just means signed out.
  }
  return { user: null, repo: null };
}

function write(next: Persisted) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Private-mode storage failures are not worth surfacing.
  }
}

interface SessionValue extends Persisted {
  signIn: () => GithubUser;
  signOut: () => void;
  selectRepo: (repo: Repository) => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const initial = read();
  const [user, setUser] = useState<GithubUser | null>(initial.user);
  const [repo, setRepo] = useState<Repository | null>(initial.repo);

  const signIn = useCallback(() => {
    setUser(MOCK_USER);
    write({ user: MOCK_USER, repo: null });
    setRepo(null);
    return MOCK_USER;
  }, []);

  const signOut = useCallback(() => {
    setUser(null);
    setRepo(null);
    write({ user: null, repo: null });
  }, []);

  const selectRepo = useCallback(
    (next: Repository) => {
      setRepo(next);
      write({ user, repo: next });
    },
    [user],
  );

  const value = useMemo<SessionValue>(
    () => ({ user, repo, signIn, signOut, selectRepo }),
    [user, repo, signIn, signOut, selectRepo],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside <SessionProvider>");
  return value;
}
