import { useState, type ReactNode } from "react";
import { ArrowGlyph } from "./Icons";

export function PageHeader({
  kicker,
  title,
  lede,
  actions,
}: {
  kicker: string;
  title: ReactNode;
  lede?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div className="page-head-copy">
        <p className="eyebrow">{kicker}</p>
        <h1 className="page-title">{title}</h1>
        {lede ? <p className="page-lede">{lede}</p> : null}
      </div>
      {actions ? <div className="page-head-actions">{actions}</div> : null}
    </header>
  );
}

export function Panel({
  title,
  kicker,
  actions,
  children,
  className = "",
  bodyClassName = "",
}: {
  title?: ReactNode;
  kicker?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title || kicker || actions ? (
        <header className="panel-head">
          <div>
            {kicker ? <p className="panel-kicker">{kicker}</p> : null}
            {title ? <h2 className="panel-title">{title}</h2> : null}
          </div>
          {actions ? <div className="panel-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className={`panel-body ${bodyClassName}`}>{children}</div>
    </section>
  );
}

type Tone = "thrift" | "prime" | "cache" | "ok" | "warn" | "bad" | "muted" | "volt" | "ink";

export function Badge({ children, tone = "muted" }: { children: ReactNode; tone?: Tone }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function TierBadge({ tier }: { tier: string }) {
  const tone: Tone = tier === "prime" ? "prime" : tier === "thrift" ? "thrift" : "cache";
  return <Badge tone={tone}>{tier === "cache" ? "cache" : `${tier} rail`}</Badge>;
}

export function StatusDot({ status }: { status: string }) {
  const tone =
    status === "ok" || status === "completed"
      ? "ok"
      : status === "running"
        ? "warn"
        : status === "blocked" || status === "cancelling"
          ? "warn"
          : "bad";
  return (
    <span className={`status status-${tone}`}>
      <span className="status-dot" />
      {status}
    </span>
  );
}

export function Stat({
  label,
  value,
  note,
  accent = "ink",
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  accent?: "ink" | "volt" | "signal" | "periwinkle";
}) {
  return (
    <article className={`stat stat-${accent}`}>
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {note ? <p className="stat-note">{note}</p> : null}
    </article>
  );
}

export function Empty({
  title,
  body,
  action,
  mark = "∅",
}: {
  title: string;
  body: ReactNode;
  action?: ReactNode;
  mark?: string;
}) {
  return (
    <div className="empty">
      <span className="empty-mark" aria-hidden="true">
        {mark}
      </span>
      <h3>{title}</h3>
      <p>{body}</p>
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton-set" aria-label="Loading">
      {Array.from({ length: lines }).map((_, index) => (
        <div
          key={index}
          className={`skeleton ${index === 0 ? "skeleton-title" : ""}`}
          style={{ width: index === 0 ? "42%" : `${88 - index * 9}%` }}
        />
      ))}
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-note" role="alert">
      <span className="error-tag">FAULT</span>
      <p>{message}</p>
      {onRetry ? (
        <button className="link-button" onClick={onRetry} type="button">
          Retry <ArrowGlyph />
        </button>
      ) : null}
    </div>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };
  return (
    <button className="copy-button" type="button" onClick={copy}>
      {copied ? "Copied" : label}
    </button>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { value: T; label: string; title?: string }[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={option.value === value ? "is-active" : ""}
          aria-pressed={option.value === value}
          title={option.title}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span className="toggle-track" aria-hidden="true">
        <span className="toggle-knob" />
      </span>
      <span className="toggle-copy">
        <span>{label}</span>
        {hint ? <small>{hint}</small> : null}
      </span>
    </label>
  );
}

export function KeyValue({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="keyvalue">
      <span className="keyvalue-label">{label}</span>
      <span className="keyvalue-value">{children}</span>
    </div>
  );
}

export function Stamp({ children, tone = "signal" }: { children: ReactNode; tone?: "signal" | "volt" | "ink" }) {
  return <span className={`stamp stamp-${tone}`}>{children}</span>;
}
