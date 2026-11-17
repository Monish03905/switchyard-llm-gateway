export function money(value: number | null | undefined): string {
  const amount = Number(value ?? 0);
  if (!Number.isFinite(amount) || amount === 0) return "$0";
  const abs = Math.abs(amount);
  if (abs < 0.001) return `$${amount.toFixed(6)}`;
  if (abs < 0.01) return `$${amount.toFixed(5)}`;
  if (abs < 1) return `$${amount.toFixed(4)}`;
  return `$${amount.toFixed(2)}`;
}

export function moneyShort(value: number | null | undefined): string {
  const amount = Number(value ?? 0);
  if (!Number.isFinite(amount) || amount === 0) return "$0";
  const abs = Math.abs(amount);
  if (abs < 0.0001) return `$${amount.toExponential(1)}`;
  if (abs < 0.01) return `$${amount.toFixed(4)}`;
  if (abs < 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toFixed(2)}`;
}

export function pct(fraction: number | null | undefined, digits = 1): string {
  const value = Number(fraction ?? 0);
  return `${(value * 100).toFixed(digits)}%`;
}

export function pctValue(value: number | null | undefined, digits = 1): string {
  return `${Number(value ?? 0).toFixed(digits)}%`;
}

export function signed(value: number | null | undefined, digits = 1, suffix = ""): string {
  const amount = Number(value ?? 0);
  const sign = amount > 0 ? "+" : "";
  return `${sign}${amount.toFixed(digits)}${suffix}`;
}

export function compact(value: number | null | undefined): string {
  const amount = Number(value ?? 0);
  if (Math.abs(amount) < 1000) return String(Math.round(amount));
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(amount);
}

export function grams(value: number | null | undefined): string {
  const amount = Number(value ?? 0);
  if (amount === 0) return "0 g";
  if (Math.abs(amount) < 0.001) return `${(amount * 1000).toFixed(2)} mg`;
  if (Math.abs(amount) < 1) return `${amount.toFixed(3)} g`;
  return `${amount.toFixed(2)} g`;
}

export function latency(ms: number | null | undefined): string {
  const value = Number(ms ?? 0);
  if (value < 1000) return `${Math.round(value)} ms`;
  if (value < 60_000) return `${(value / 1000).toFixed(2)} s`;
  return `${(value / 60_000).toFixed(1)} min`;
}

export function clock(ms: number | string | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  const date = typeof ms === "string" ? new Date(ms) : new Date(ms);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString("en-GB", {
    timeZone: "UTC",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function dateShort(ms: number | string | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  const date = typeof ms === "string" ? new Date(ms) : new Date(ms);
  if (Number.isNaN(date.getTime())) return "—";
  const sameYear = date.getUTCFullYear() === new Date().getUTCFullYear();
  return date.toLocaleDateString("en-US", {
    timeZone: "UTC",
    month: "short",
    day: "2-digit",
    ...(sameYear ? {} : { year: "numeric" }),
  });
}

export function ago(ms: number | null | undefined, now = Date.now()): string {
  if (!ms) return "—";
  const diff = Math.max(0, now - ms);
  if (diff < 20_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

export function titleCase(value: string): string {
  return value
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function shortHash(value: string | null | undefined, head = 10, tail = 6): string {
  if (!value) return "—";
  if (value.length <= head + tail + 1) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

export function plural(count: number, singular: string, pluralForm?: string): string {
  return count === 1 ? singular : pluralForm ?? `${singular}s`;
}

export function tierLabel(tier: string): string {
  if (tier === "prime") return "Prime rail";
  if (tier === "thrift") return "Thrift rail";
  if (tier === "cache") return "Cache";
  return tier;
}
