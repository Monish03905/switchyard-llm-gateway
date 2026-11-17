import { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { useFetch } from "../lib/hooks";
import type { Health } from "../lib/types";
import { Rail, type ThemeId } from "./Rail";

export function Shell({ theme, onTheme }: { theme: ThemeId; onTheme: (theme: ThemeId) => void }) {
  const health = useFetch<Health>("/health", 30_000);

  useEffect(() => {
    const mode = health.data?.mode;
    if (mode) document.documentElement.dataset.mode = mode;
  }, [health.data?.mode]);

  return (
    <div className="app-shell">
      <Rail
        theme={theme}
        onTheme={onTheme}
        mode={health.data?.mode ?? ""}
        version={health.data?.version ?? ""}
      />
      <main className="yard-main">
        <div className="yard-inner">
          <Outlet />
        </div>
        <footer className="yard-footer">
          <p>
            Switchyard · FastAPI + React · every receipt hash-chained
            <span className="footer-dot">·</span>
            <a href="/docs" target="_blank" rel="noreferrer">
              API desk
            </a>
            <span className="footer-dot">·</span>
            <a href="/metrics/prometheus" target="_blank" rel="noreferrer">
              metrics
            </a>
          </p>
          <p className="yard-footer-note">Built for the last mile: routing, failure, proof.</p>
        </footer>
      </main>
    </div>
  );
}
