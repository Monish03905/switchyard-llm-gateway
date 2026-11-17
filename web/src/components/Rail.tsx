import { NavLink } from "react-router-dom";
import { YardMark, IconYard, IconDispatch, IconGauntlet, IconLedger, IconSwitchboard, IconNotes } from "./Icons";
import { useTicker } from "../lib/hooks";

export type ThemeId = "paper" | "dusk" | "blueprint";

export const THEMES: { id: ThemeId; label: string; note: string }[] = [
  { id: "paper", label: "Paper", note: "warm daylight" },
  { id: "dusk", label: "Dusk", note: "night shift" },
  { id: "blueprint", label: "Blueprint", note: "cold drafting" },
];

const NAV = [
  { to: "/", label: "Yard", index: "01", Icon: IconYard, end: true },
  { to: "/dispatch", label: "Dispatch", index: "02", Icon: IconDispatch },
  { to: "/gauntlet", label: "Gauntlet", index: "03", Icon: IconGauntlet },
  { to: "/ledger", label: "Ledger", index: "04", Icon: IconLedger },
  { to: "/switchboard", label: "Switchboard", index: "05", Icon: IconSwitchboard },
  { to: "/notes", label: "Field notes", index: "06", Icon: IconNotes },
];

export function Rail({
  theme,
  onTheme,
  mode,
  version,
}: {
  theme: ThemeId;
  onTheme: (theme: ThemeId) => void;
  mode: string;
  version: string;
}) {
  const now = useTicker(1000);
  const utc = new Date(now).toISOString().slice(11, 19);

  return (
    <aside className="rail">
      <div className="rail-brand">
        <YardMark size={44} />
        <div>
          <strong>SWITCHYARD</strong>
          <span>one gate, many engines</span>
        </div>
      </div>

      <div className="rail-rule">
        <span>Control room</span>
        <span>v{version || "1.0.0"}</span>
      </div>

      <nav className="rail-nav" aria-label="Main">
        {NAV.map(({ to, label, index, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `rail-link ${isActive ? "is-active" : ""}`}
          >
            <span className="rail-index">{index}</span>
            <Icon size={17} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="rail-spacer" />

      <div className="rail-mode">
        <span className={`live-dot ${mode === "simulated" ? "is-sim" : ""}`} aria-hidden="true" />
        <div>
          <strong>{mode || "checking"}</strong>
          <small>{mode === "simulated" ? "rehearsal rail" : mode === "live" ? "live rail" : "handshake"}</small>
        </div>
      </div>

      <div className="rail-clock">
        <span>{utc}</span>
        <small>UTC</small>
      </div>

      <div className="theme-switch" role="group" aria-label="Theme">
        {THEMES.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`theme-chip theme-${item.id} ${theme === item.id ? "is-active" : ""}`}
            onClick={() => onTheme(item.id)}
            aria-pressed={theme === item.id}
            aria-label={`${item.label} theme`}
            title={item.note}
          >
            <span className="theme-swatch" aria-hidden="true" />
            <span className="theme-label">{item.label}</span>
          </button>
        ))}
      </div>

      <p className="rail-note">Receipts, not vibes.</p>
    </aside>
  );
}
