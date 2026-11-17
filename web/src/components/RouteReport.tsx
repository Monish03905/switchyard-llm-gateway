import type { Route } from "../lib/types";
import { grams, latency, money, pct } from "../lib/format";
import { ConfidenceMeter, ReasonBars, ScoreDial } from "./Charts";
import { Badge, TierBadge } from "./UI";
import { ArrowGlyph } from "./Icons";

export function RouteReport({
  route,
  model,
  provider,
  tokens,
  cost,
  saved,
  co2,
  latencyMs,
  cacheHit,
  fallbackUsed,
  onOpenReceipt,
}: {
  route: Route;
  model?: string;
  provider?: string;
  tokens?: number;
  cost?: number;
  saved?: number;
  co2?: number;
  latencyMs?: number;
  cacheHit?: boolean;
  fallbackUsed?: boolean;
  onOpenReceipt?: () => void;
}) {
  const features = route.features as Record<string, unknown>;
  const chips = [
    features.chars ? `${features.chars} chars` : null,
    features.approx_tokens ? `~${features.approx_tokens} tokens` : null,
    features.numbers ? `${features.numbers} numbers` : null,
    features.question_marks ? `${features.question_marks} question marks` : null,
    features.multi_step ? "multi-step" : null,
    features.has_fence ? "code fence" : features.has_code ? "code shaped" : null,
    features.greeting ? "greeting" : null,
    features.short_lookup ? "lookup" : null,
  ].filter(Boolean) as string[];

  return (
    <div className="route-report">
      <div className="route-flags">
        <TierBadge tier={route.tier} />
        <Badge tone="ink">policy {route.policy}</Badge>
        {cacheHit ? <Badge tone="cache">cache hit</Badge> : null}
        {fallbackUsed ? <Badge tone="warn">fallback used</Badge> : null}
        {route.pinned_model ? <Badge tone="muted">pinned</Badge> : null}
      </div>

      <p className="route-summary">{route.summary}</p>

      <div className="route-dials">
        <ScoreDial score={route.score} threshold={Number(features.threshold ?? 0.33)} tier={route.tier} />
        <div className="route-confidence">
          <ConfidenceMeter confidence={route.confidence} />
          <p>
            Threshold sits at <strong>{Number(features.threshold ?? 0.33).toFixed(2)}</strong>. Anything
            above it takes the prime rail.
          </p>
          <div className="chip-row">
            {chips.map((chip) => (
              <span className="mini-chip" key={chip}>
                {chip}
              </span>
            ))}
          </div>
        </div>
      </div>

      <ReasonBars reasons={route.reasons} />

      <div className="route-meta">
        <div>
          <span>model</span>
          <strong>{model || "—"}</strong>
        </div>
        <div>
          <span>provider</span>
          <strong>{provider || "—"}</strong>
        </div>
        <div>
          <span>tokens</span>
          <strong>{tokens ? tokens.toLocaleString() : "—"}</strong>
        </div>
        <div>
          <span>spend</span>
          <strong>{cost !== undefined ? money(cost) : "—"}</strong>
        </div>
        <div>
          <span>avoided</span>
          <strong>{saved !== undefined ? money(saved) : "—"}</strong>
        </div>
        <div>
          <span>CO₂e</span>
          <strong>{co2 !== undefined ? grams(co2) : "—"}</strong>
        </div>
        <div>
          <span>latency</span>
          <strong>{latencyMs !== undefined ? latency(latencyMs) : "—"}</strong>
        </div>
        <div>
          <span>confidence</span>
          <strong>{pct(route.confidence, 0)}</strong>
        </div>
      </div>

      {onOpenReceipt ? (
        <button className="link-button" type="button" onClick={onOpenReceipt}>
          Open the receipt <ArrowGlyph />
        </button>
      ) : null}
    </div>
  );
}
