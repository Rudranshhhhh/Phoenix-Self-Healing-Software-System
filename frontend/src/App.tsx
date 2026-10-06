import { useEffect } from "react";
import { BrowserRouter, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { SessionProvider } from "./state/SessionContext";
import { SiteFooter, SiteHeader } from "./components/chrome/Site";
import { KeyboardShortcuts } from "./components/chrome/KeyboardShortcuts";
import Home from "./pages/Home";
import Connect from "./pages/Connect";
import Dashboard from "./pages/Dashboard";
import IncidentPage from "./pages/IncidentPage";
import NotFound from "./pages/NotFound";
import ChickPreview from "./pages/ChickPreview";
import ArcPreview from "./pages/ArcPreview";

/** Land at the top of each new page, or on the target of an in-page anchor. */
function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      requestAnimationFrame(() =>
        document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
      return;
    }
    window.scrollTo(0, 0);
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
        <KeyboardShortcuts />
        <Routes>
          <Route element={<SiteLayout />}>
            <Route path="/" element={<Home />} />
            <Route path="/connect" element={<Connect />} />
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
