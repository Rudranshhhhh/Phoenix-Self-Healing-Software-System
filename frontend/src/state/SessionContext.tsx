import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { GithubUser, Repository } from "../types/phoenix";
import { getGitHubUser, githubLogout, startGitHubLogin } from "../api/phoenix";

// ---------------------------------------------------------------------------
// Session state: who is signed in and which repository they are watching.
//
// After a GitHub OAuth round-trip the backend sets an HttpOnly session cookie.
// On mount we always call GET /api/github/me to check whether a valid session
// exists — this handles both first load and post-redirect restoration.
//
// The selected repo is persisted in sessionStorage so a page refresh on the
// dashboard doesn't bounce the user back to /connect.
// ---------------------------------------------------------------------------

const REPO_KEY = "phoenix.selected_repo";

function readRepo(): Repository | null {
  try {
    const raw = sessionStorage.getItem(REPO_KEY);
    if (raw) return JSON.parse(raw) as Repository;
  } catch {
    // corrupt or unavailable storage → not selected
  }
  return null;
}

function writeRepo(repo: Repository | null) {
  try {
    if (repo) sessionStorage.setItem(REPO_KEY, JSON.stringify(repo));
    else sessionStorage.removeItem(REPO_KEY);
  } catch {
    // private-mode failures are not worth surfacing
  }
}

// ---------------------------------------------------------------------------

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface SessionValue {
  status: AuthStatus;
  user: GithubUser | null;
  repo: Repository | null;
  /** Navigate the browser to GitHub's OAuth page. */
  signIn: () => void;
  /** Call DELETE /api/github/logout, clear local state. */
  signOut: () => void;
  /** Called by the Connect page after the user picks a repo. */
  selectRepo: (repo: Repository) => void;
  /** Called by OAuthCallback after a successful round-trip to reload the user. */
  refreshUser: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<GithubUser | null>(null);
  const [repo, setRepo] = useState<Repository | null>(readRepo);

  // On mount: check whether the backend already has a valid session cookie.
  useEffect(() => {
    const controller = new AbortController();
    getGitHubUser(controller.signal)
      .then((u) => {
        setUser(u);
        setStatus(u ? "authenticated" : "unauthenticated");
      })
      .catch(() => {
        setStatus("unauthenticated");
      });
    return () => controller.abort();
  }, []);

  const signIn = useCallback(() => {
    startGitHubLogin(); // full-page navigation to /api/github/login → GitHub → callback
  }, []);

  const signOut = useCallback(async () => {
    try {
      await githubLogout();
    } catch {
      // best-effort — clear local state regardless
    }
    setUser(null);
    setRepo(null);
    writeRepo(null);
    setStatus("unauthenticated");
  }, []);

  const selectRepo = useCallback((next: Repository) => {
    setRepo(next);
    writeRepo(next);
  }, []);

  /** Called by OAuthCallback to pull the user profile after the cookie is set. */
  const refreshUser = useCallback(async () => {
    const u = await getGitHubUser();
    setUser(u);
    setStatus(u ? "authenticated" : "unauthenticated");
  }, []);

  const value = useMemo<SessionValue>(
    () => ({ status, user, repo, signIn, signOut, selectRepo, refreshUser }),
    [status, user, repo, signIn, signOut, selectRepo, refreshUser],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside <SessionProvider>");
  return value;
}
