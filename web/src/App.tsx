import { useEffect, useState } from "react";
import { BrowserRouter, Link, Route, Routes, useLocation } from "react-router-dom";
import { ToastProvider } from "./components/Toast";
import { Shell } from "./components/Shell";
import { type ThemeId } from "./components/Rail";
import { Empty, PageHeader } from "./components/UI";
import { YardPage } from "./pages/YardPage";
import { DispatchPage } from "./pages/DispatchPage";
import { GauntletPage } from "./pages/GauntletPage";
import { LedgerPage } from "./pages/LedgerPage";
import { SwitchboardPage } from "./pages/SwitchboardPage";
import { FieldNotesPage } from "./pages/FieldNotesPage";

const THEME_KEY = "switchyard-theme";

function isTheme(value: string | null): value is ThemeId {
  return value === "paper" || value === "dusk" || value === "blueprint";
}

function readTheme(): ThemeId {
  const fromUrl = new URLSearchParams(window.location.search).get("theme");
  if (isTheme(fromUrl)) return fromUrl;
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (isTheme(stored)) return stored;
  } catch {
    /* storage can be denied; paper is a fine default */
  }
  return "paper";
}

function ScrollManager() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }, [pathname, hash]);
  return null;
}

function NotFound() {
  return (
    <>
      <PageHeader
        kicker="404 / off the rails"
        title={
          <>
            This siding is empty. <em>The yard is that way.</em>
          </>
        }
        lede="The address does not match a page in the cockpit. Nothing is broken; you are simply between signals."
      />
      <Empty
        mark="404"
        title="No page at this address"
        body="Use the rail on the left, or head back to the yard overview and pick up the trail there."
        action={
          <Link className="btn btn-solid" to="/">
            Back to the yard
          </Link>
        }
      />
    </>
  );
}

export function App() {
  const [theme, setTheme] = useState<ThemeId>(readTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* the theme still applies for this tab */
    }
    const url = new URL(window.location.href);
    if (url.searchParams.has("theme")) {
      url.searchParams.delete("theme");
      window.history.replaceState({}, "", url);
    }
  }, [theme]);

  return (
    <ToastProvider>
      <BrowserRouter>
        <ScrollManager />
        <Routes>
          <Route element={<Shell theme={theme} onTheme={setTheme} />}>
            <Route path="/" element={<YardPage />} />
            <Route path="/dispatch" element={<DispatchPage />} />
            <Route path="/gauntlet" element={<GauntletPage />} />
            <Route path="/ledger" element={<LedgerPage />} />
            <Route path="/switchboard" element={<SwitchboardPage />} />
            <Route path="/notes" element={<FieldNotesPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}
