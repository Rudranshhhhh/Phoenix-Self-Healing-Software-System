/**
 * OAuthCallback — /connect/callback
 *
 * The browser lands here after GitHub redirects back to the backend
 * (/api/github/callback), which:
 *   1. Verifies the `state` parameter
 *   2. Exchanges the code for a GitHub access token
 *   3. Sets an HttpOnly signed session cookie
 *   4. Redirects the browser to http://localhost:3000/connect/callback  ← here
 *
 * At this point the session cookie is already in the browser's cookie jar.
 * This component just calls /api/github/me to pull the user profile into
 * React state, then navigates to /connect (the repository picker).
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { useSession } from "../state/SessionContext";

type Phase = "loading" | "error";

export default function OAuthCallback() {
  const { refreshUser } = useSession();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [phase, setPhase] = useState<Phase>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const ran = useRef(false); // StrictMode guard — run the effect only once

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    // If GitHub redirected here with an error (user denied, etc.)
    const oauthError = searchParams.get("error");
    if (oauthError) {
      const desc = searchParams.get("error_description") ?? oauthError;
      setErrorMsg(`GitHub returned an error: ${desc}`);
      setPhase("error");
      return;
    }

    // Cookie is already set by the backend redirect — just load the user.
    refreshUser()
      .then(() => {
        navigate("/connect", { replace: true });
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setErrorMsg(`Could not load your GitHub profile: ${msg}`);
        setPhase("error");
      });
  }, [refreshUser, navigate, searchParams]);

  if (phase === "error") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 px-4 text-center">
        <p className="max-w-md text-[15px] leading-relaxed text-body">{errorMsg}</p>
        <a
          href="/connect"
          className="rounded-box border border-line bg-surface px-5 py-2.5 text-[14px] font-medium text-ink hover:bg-subtle"
        >
          Try again
        </a>
      </div>
    );
  }

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
      <RefreshCw size={28} className="animate-spin text-muted" />
      <p className="text-[15px] text-muted">Finishing GitHub sign-in…</p>
    </div>
  );
}
