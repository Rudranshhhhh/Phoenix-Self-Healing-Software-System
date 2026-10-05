import { useEffect } from "react";
import { BrowserRouter, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { SessionProvider } from "./state/SessionContext";
import { SiteFooter, SiteHeader } from "./components/chrome/Site";
import Home from "./pages/Home";
import Connect from "./pages/Connect";
import OAuthCallback from "./pages/OAuthCallback";
import Dashboard from "./pages/Dashboard";
import IncidentPage from "./pages/IncidentPage";
import NotFound from "./pages/NotFound";
import ChickPreview from "./pages/ChickPreview";
import ArcPreview from "./pages/ArcPreview";

/** Land at the top of each new page, except when following an in-page anchor. */
function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) return;
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }, [pathname, hash]);
  return null;
}

/** Marketing chrome: full site header and footer. */
function SiteLayout() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="flex-1">
        <Outlet />
      </main>
      <SiteFooter />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <ScrollToTop />
        <Routes>
          <Route element={<SiteLayout />}>
            <Route path="/" element={<Home />} />
            <Route path="/connect" element={<Connect />} />
            {/* GitHub OAuth callback — must be outside SiteLayout so there's no chrome flash */}
            <Route path="/connect/callback" element={<OAuthCallback />} />
            <Route path="*" element={<NotFound />} />
          </Route>

          {/* The monitoring view carries its own, quieter chrome. */}
          <Route path="/app" element={<Dashboard />} />
          <Route path="/app/incidents/:id" element={<IncidentPage />} />
          <Route path="/app/:owner/:repo" element={<Dashboard />} />

          {import.meta.env.DEV && <Route path="/dev/chick" element={<ChickPreview />} />}
          {import.meta.env.DEV && <Route path="/dev/arc" element={<ArcPreview />} />}
        </Routes>
      </SessionProvider>
    </BrowserRouter>
  );
}
