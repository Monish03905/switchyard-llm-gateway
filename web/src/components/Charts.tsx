import type { EvalRun, Reason, Tier, TimelinePoint } from "../lib/types";
import { money, moneyShort, pct, pctValue } from "../lib/format";

const POLICY_COLOR: Record<string, string> = {
  thrift: "var(--periwinkle)",
  prime: "var(--signal)",
  yardmaster: "var(--volt-deep)",
};

const TIER_COLOR: Record<string, string> = {
  thrift: "var(--periwinkle)",
  prime: "var(--signal)",
  cache: "var(--volt-deep)",
};

export function TrafficChart({ points }: { points: TimelinePoint[] }) {
  const width = 720;
  const height = 236;
  const pad = { l: 46, r: 14, t: 20, b: 30 };
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  const slot = innerW / Math.max(points.length, 1);
  const barWidth = Math.max(3, slot * 0.52);
  const maxCost = Math.max(...points.map((point) => point.cost_usd), 0.000001);
  const maxRequests = Math.max(...points.map((point) => point.requests), 1);
  const zero = points.every((point) => point.requests === 0);

  const x = (index: number) => pad.l + slot * index + slot / 2;
  const barHeight = (value: number) => (value / maxCost) * innerH * 0.8;
  const lineY = (value: number) => pad.t + innerH - (value / maxRequests) * innerH * 0.92;

  const line = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(1)},${lineY(point.requests).toFixed(1)}`)
    .join(" ");

  return (
    <div className="chart-block">
      <div className="chart-legend">
        <span>
          <i className="legend-bar" /> spend
        </span>
        <span>
          <i className="legend-line" /> requests
        </span>
        <span className="chart-hint">last {points.length} bins · UTC</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="chart" role="img" aria-label="Traffic and spend over time">
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <line
            key={fraction}
            x1={pad.l}
            x2={width - pad.r}
            y1={pad.t + innerH * fraction}
            y2={pad.t + innerH * fraction}
            className="chart-grid"
          />
        ))}
        {points.map((point, index) => {
          const heightPx = Math.max(point.cost_usd > 0 ? 2 : 0, barHeight(point.cost_usd));
          return (
            <g key={point.t}>
              <rect
                x={x(index) - barWidth / 2}
                y={pad.t + innerH - heightPx}
                width={barWidth}
                height={heightPx}
                className="chart-bar"
              >
                <title>
                  {point.label} · {point.requests} requests · {money(point.cost_usd)}
                </title>
              </rect>
            </g>
          );
        })}
        <path d={line} className="chart-line" />
        {points.map((point, index) =>
          point.requests > 0 ? (
            <circle key={`dot-${point.t}`} cx={x(index)} cy={lineY(point.requests)} r={2.6} className="chart-dot" />
          ) : null,
        )}
        {points.map((point, index) =>
          index % 4 === 0 ? (
            <text key={`label-${point.t}`} x={x(index)} y={height - 9} className="chart-axis" textAnchor="middle">
              {point.label}
            </text>
          ) : null,
        )}
        <text x={pad.l - 8} y={pad.t + 4} className="chart-axis" textAnchor="end">
          {moneyShort(maxCost)}
        </text>
        <text x={pad.l - 8} y={pad.t + innerH} className="chart-axis" textAnchor="end">
          $0
        </text>
        <text x={width - pad.r} y={pad.t - 6} className="chart-axis" textAnchor="end">
          peak {maxRequests} req
        </text>
        {zero ? (
          <text x={width / 2} y={pad.t + innerH / 2} className="chart-empty-label" textAnchor="middle">
            Quiet yard. Send a prompt to draw the first bar.
          </text>
        ) : null}
      </svg>
    </div>
  );
}

export function RouteDonut({ mix }: { mix: { thrift?: number; prime?: number; cache?: number; total: number } }) {
  const total = mix.total ?? 0;
  const slices = [
    { key: "thrift", label: "thrift", value: mix.thrift ?? 0 },
    { key: "prime", label: "prime", value: mix.prime ?? 0 },
    { key: "cache", label: "cache", value: mix.cache ?? 0 },
  ];
  const circumference = 2 * Math.PI * 54;
  let offset = 0;

  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 150 150" className="donut" role="img" aria-label="Route mix">
        <circle cx="75" cy="75" r="54" className="donut-track" strokeWidth="18" fill="none" />
        {slices.map((slice) => {
          const fraction = total ? slice.value / total : 0;
          const dash = fraction * circumference;
          const circle = (
            <circle
              key={slice.key}
              cx="75"
              cy="75"
              r="54"
              fill="none"
              stroke={TIER_COLOR[slice.key]}
              strokeWidth="18"
              strokeDasharray={`${dash} ${circumference - dash}`}
              strokeDashoffset={-offset}
              transform="rotate(-90 75 75)"
            >
              <title>
                {slice.label}: {slice.value}
              </title>
            </circle>
          );
          offset += dash;
          return circle;
        })}
        <text x="75" y="72" textAnchor="middle" className="donut-value">
          {total}
        </text>
        <text x="75" y="88" textAnchor="middle" className="donut-label">
          sealed calls
        </text>
      </svg>
      <ul className="donut-legend">
        {slices.map((slice) => (
          <li key={slice.key}>
            <i style={{ background: TIER_COLOR[slice.key] }} />
            <span>{slice.label}</span>
            <strong>{slice.value}</strong>
            <small>{total ? pct(slice.value / total, 0) : "0%"}</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CostPassScatter({ runs }: { runs: EvalRun[] }) {
  const width = 640;
  const height = 300;
  const pad = { l: 52, r: 24, t: 24, b: 42 };
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  const maxCost = Math.max(...runs.map((run) => run.total_cost_usd), 0.0001) * 1.25;
  const x = (cost: number) => pad.l + (cost / maxCost) * innerW;
  const y = (rate: number) => pad.t + innerH - rate * innerH;

  if (!runs.length) {
    return <div className="chart-empty">No exam on the board yet.</div>;
  }

  return (
    <div className="chart-block">
      <div className="chart-legend">
        <span>
          <i className="legend-dot" style={{ background: POLICY_COLOR.thrift }} /> thrift
        </span>
        <span>
          <i className="legend-dot" style={{ background: POLICY_COLOR.prime }} /> prime
        </span>
        <span>
          <i className="legend-dot" style={{ background: POLICY_COLOR.yardmaster }} /> router
        </span>
        <span className="chart-hint">cost → · pass rate ↑</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="chart" role="img" aria-label="Cost versus pass rate">
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <g key={fraction}>
            <line x1={pad.l} x2={width - pad.r} y1={y(fraction)} y2={y(fraction)} className="chart-grid" />
            <text x={pad.l - 8} y={y(fraction) + 3} className="chart-axis" textAnchor="end">
              {Math.round(fraction * 100)}%
            </text>
          </g>
        ))}
        <line x1={x(0)} x2={x(maxCost)} y1={y(0)} y2={y(0)} className="chart-axis-line" />
        <line x1={pad.l} x2={pad.l} y1={pad.t} y2={height - pad.b} className="chart-axis-line" />
        <line x1={pad.l} x2={width - pad.r} y1={y(0.9)} y2={y(0.9)} className="chart-threshold" />
        <text x={width - pad.r} y={y(0.9) - 6} textAnchor="end" className="chart-axis">
          90% line
        </text>
        {runs.map((run) => (
          <g key={run.id}>
            <circle cx={x(run.total_cost_usd) + 2.5} cy={y(run.pass_rate) + 2.5} r="8" fill="var(--ink)" opacity="0.9" />
            <circle
              cx={x(run.total_cost_usd)}
              cy={y(run.pass_rate)}
              r="8"
              fill={POLICY_COLOR[run.policy] ?? "var(--ink)"}
              stroke="var(--ink)"
              strokeWidth="1.5"
            >
              <title>
                {run.policy}: {pct(run.pass_rate)} pass · {money(run.total_cost_usd)} spend
              </title>
            </circle>
            <text
              x={x(run.total_cost_usd) + 13}
              y={y(run.pass_rate) + 3.5}
              className="chart-point-label"
            >
              {run.policy === "yardmaster" ? "router" : run.policy}
            </text>
          </g>
        ))}
        {[0, 0.5, 1].map((fraction) => (
          <text
            key={`tick-${fraction}`}
            x={x(maxCost * fraction)}
            y={height - 16}
            className="chart-axis"
            textAnchor="middle"
          >
            {moneyShort(maxCost * fraction)}
          </text>
        ))}
        <text x={width - pad.r} y={height - 2} className="chart-axis" textAnchor="end">
          total spend
        </text>
      </svg>
    </div>
  );
}

export function BudgetGauge({
  spent,
  limit,
  remaining,
}: {
  spent: number;
  limit: number;
  remaining: number;
}) {
  if (!limit || limit <= 0) {
    return <p className="budget-unlimited">No daily cap set. The meter is wide open.</p>;
  }
  const ratio = Math.min(1, spent / limit);
  const tone = ratio >= 0.95 ? "is-critical" : ratio >= 0.7 ? "is-warm" : "";
  return (
    <div className={`budget-gauge ${tone}`}>
      <div className="budget-bar">
        <span style={{ width: `${Math.max(ratio * 100, ratio > 0 ? 2 : 0)}%` }} />
        {[25, 50, 75].map((tick) => (
          <i key={tick} style={{ left: `${tick}%` }} />
        ))}
      </div>
      <div className="budget-meta">
        <span>
          <strong>{money(spent)}</strong> spent today
        </span>
        <span>{money(remaining)} left of {money(limit)}</span>
      </div>
      <p className="budget-note">
        {ratio >= 0.95
          ? "The gate is about to close. New prime routes will be blocked."
          : ratio >= 0.7
            ? "Guard is watching. Prime routes may be downgraded."
            : "The budget guard is quiet."}
      </p>
    </div>
  );
}

function polar(cx: number, cy: number, radius: number, angle: number) {
  const radians = (angle * Math.PI) / 180;
  return { x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians) };
}

function arc(cx: number, cy: number, radius: number, start: number, end: number) {
  const from = polar(cx, cy, radius, start);
  const to = polar(cx, cy, radius, end);
  const large = end - start <= 180 ? 0 : 1;
  return `M${from.x.toFixed(2)},${from.y.toFixed(2)} A${radius},${radius} 0 ${large} 1 ${to.x.toFixed(2)},${to.y.toFixed(2)}`;
}

export function ScoreDial({
  score,
  threshold,
  tier,
}: {
  score: number;
  threshold: number;
  tier: Tier | string;
}) {
  const max = 1.4;
  const clamp = (value: number) => Math.min(max, Math.max(0, value));
  const angle = (value: number) => 180 + (clamp(value) / max) * 180;
  const color = tier === "prime" ? "var(--signal)" : "var(--periwinkle)";
  const thresholdPoint = polar(72, 74, 52, angle(threshold));
  const scorePoint = polar(72, 74, 52, angle(score));

  return (
    <svg viewBox="0 0 144 100" className="score-dial" role="img" aria-label={`Route score ${score}`}>
      <path d={arc(72, 74, 52, 180, 360)} className="dial-track" strokeWidth="10" fill="none" />
      <path d={arc(72, 74, 52, 180, angle(score))} stroke={color} strokeWidth="10" fill="none" strokeLinecap="butt" />
      <line
        x1={thresholdPoint.x}
        y1={thresholdPoint.y}
        x2={polar(72, 74, 61, angle(threshold)).x}
        y2={polar(72, 74, 61, angle(threshold)).y}
        className="dial-threshold"
      />
      <circle cx={scorePoint.x} cy={scorePoint.y} r="4" fill="var(--ink)" />
      <text x="72" y="70" textAnchor="middle" className="dial-value">
        {score.toFixed(2)}
      </text>
      <text x="72" y="84" textAnchor="middle" className="dial-label">
        score / threshold {threshold.toFixed(2)}
      </text>
    </svg>
  );
}

export function ConfidenceMeter({ confidence }: { confidence: number }) {
  return (
    <div className="confidence">
      <div className="confidence-head">
        <span>confidence</span>
        <strong>{pct(confidence, 0)}</strong>
      </div>
      <div className="confidence-track">
        <span style={{ width: `${Math.min(100, Math.max(0, confidence * 100))}%` }} />
      </div>
    </div>
  );
}

export function ReasonBars({ reasons }: { reasons: Reason[] }) {
  if (!reasons.length) {
    return <p className="reason-empty">No weighted signals. The router kept it neutral.</p>;
  }
  const max = Math.max(...reasons.map((reason) => Math.abs(reason.weight)), 0.01);
  return (
    <ul className="reason-bars">
      {reasons.map((reason, index) => {
        const positive = reason.weight >= 0;
        const width = Math.max(4, (Math.abs(reason.weight) / max) * 100);
        return (
          <li key={`${reason.label}-${index}`} className={positive ? "is-up" : "is-down"}>
            <div className="reason-copy">
              <span>{reason.label}</span>
              <strong>
                {positive ? "+" : "−"}
                {Math.abs(reason.weight).toFixed(2)}
              </strong>
            </div>
            <div className="reason-track">
              <span style={{ width: `${width}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function PolicyBars({
  runs,
  metric,
  formatter,
}: {
  runs: EvalRun[];
  metric: "pass_rate" | "total_cost_usd" | "avg_score";
  formatter: (value: number) => string;
}) {
  const max = Math.max(...runs.map((run) => run[metric]), 0.0001);
  return (
    <ul className="policy-bars">
      {runs.map((run) => (
        <li key={run.id}>
          <span className="policy-name">{run.policy === "yardmaster" ? "router" : run.policy}</span>
          <div className="policy-track">
            <span
              style={{
                width: `${Math.max(2, (run[metric] / max) * 100)}%`,
                background: POLICY_COLOR[run.policy] ?? "var(--ink)",
              }}
            />
          </div>
          <strong>{formatter(run[metric])}</strong>
        </li>
      ))}
    </ul>
  );
}

export function CostPassNote({ runs }: { runs: EvalRun[] }) {
  const prime = runs.find((run) => run.policy === "prime");
  const yard = runs.find((run) => run.policy === "yardmaster");
  if (!prime || !yard) return null;
  return (
    <p className="chart-note">
      Router spends <strong>{pctValue(prime.total_cost_usd ? (1 - yard.total_cost_usd / prime.total_cost_usd) * 100 : 0)}</strong>{" "}
      less than prime and gives up{" "}
      <strong>{Math.abs((yard.pass_rate - prime.pass_rate) * 100).toFixed(1)} pts</strong> of pass rate.
      The scatter is the argument: distance from the top-left corner is what you pay for certainty.
    </p>
  );
}
