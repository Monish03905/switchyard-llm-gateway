import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useFetch } from "../lib/hooks";
import { api, errorMessage } from "../lib/api";
import type { Completion, DispatchResponse, Overview, RequestSummary } from "../lib/types";
import { ago, clock, compact, grams, latency, money, pct, pctValue, signed } from "../lib/format";
import { BudgetGauge, RouteDonut, TrafficChart } from "../components/Charts";
import { RequestDrawer } from "../components/RequestDrawer";
import {
  ArrowGlyph,
  DialGlyph,
  IconGauntlet,
  IconLedger,
  IconNotes,
} from "../components/Icons";
import {
  Badge,
  Empty,
  ErrorNote,
  PageHeader,
  Panel,
  Segmented,
  Skeleton,
  Stamp,
  Stat,
  StatusDot,
  TierBadge,
} from "../components/UI";

const HOURS = [
  { value: "6", label: "6h" },
  { value: "24", label: "24h" },
  { value: "72", label: "3d" },
  { value: "168", label: "7d" },
];

export function YardPage() {
  const [hours, setHours] = useState("24");
  const overview = useFetch<Overview>(`/api/overview?hours=${hours}`, 15_000);
  const [quick, setQuick] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<Completion | null>(null);
  const [quickError, setQuickError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const data = overview.data;
  const windowLabel = hours === "24" ? "last 24 hours" : `last ${hours} hours`;

  const ask = async (event: FormEvent) => {
    event.preventDefault();
    if (!quick.trim() || asking) return;
    setAsking(true);
    setQuickError(null);
    setAnswer(null);
    try {
      const response = await api.post<DispatchResponse>("/api/dispatch", {
        prompt: quick.trim(),
        policy: "auto",
      });
      if (response.completion) {
        setAnswer(response.completion);
        overview.reload();
      } else {
        setQuickError("The agent answered without a receipt. Open the dispatch desk for tool runs.");
      }
    } catch (error) {
      setQuickError(errorMessage(error));
    } finally {
      setAsking(false);
    }
  };

  return (
    <>
      <PageHeader
        kicker="Yard office / live board"
        title={
          <>
            One gate. Many engines. <em>Every call on the record.</em>
          </>
        }
        lede={
          <>
            Switchyard routes each prompt to the cheapest rail that can carry it, fails over when a
            provider stumbles, and mints a hash-chained receipt for every answer.
          </>
        }
        actions={
          <>
            <Link to="/gauntlet" className="btn btn-solid">
              <IconGauntlet size={16} /> Run the gauntlet
            </Link>
            <Link to="/ledger" className="btn">
              <IconLedger size={16} /> Open the ledger
            </Link>
          </>
        }
      />

      {data?.meta.simulated ? (
        <div className="mode-banner">
          <span className="mode-stamp">REHEARSAL</span>
          <p>
            <strong>The simulator is holding the levers.</strong> Costs, carbon and pass rates below
            are a calibrated rehearsal, not a provider bill. Add a Groq or OpenAI key to put the
            same routes on live rails.
          </p>
          <Link to="/notes#simulator" className="text-link">
            Read the honesty note <ArrowGlyph />
          </Link>
        </div>
      ) : null}

      {overview.error && !data ? <ErrorNote message={overview.error} onRetry={overview.reload} /> : null}

      {data ? (
        <div className="ticker" aria-label="Yard summary">
          <div className="ticker-track">
            {[0, 1].map((copy) => (
              <div className="ticker-group" key={copy} aria-hidden={copy === 1}>
                <span>
                  MODE <strong>{data.meta.mode}</strong>
                </span>
                <span>
                  CHAIN <strong>{data.guardrails.chain.ok ? "SEALED" : "BROKEN"}</strong>
                </span>
                <span>
                  CACHE <strong>{pct(data.stats.cache_hit_rate)}</strong>
                </span>
                <span>
                  P95 <strong>{latency(data.stats.latency_p95_ms)}</strong>
                </span>
                <span>
                  SPEND <strong>{money(data.stats.cost_usd)}</strong>
                </span>
                <span>
                  AVOIDED <strong>{money(data.stats.saved_usd)}</strong>
                </span>
                <span>
                  GAUNTLET{" "}
                  <strong>{data.last_batch ? data.last_batch.status : "NOT RUN"}</strong>
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <form className="quick-ask" onSubmit={ask}>
        <div className="quick-ask-copy">
          <span className="quick-ask-label">Ask the yard</span>
          <p>Type a prompt and watch the router pick a rail in real time.</p>
        </div>
        <div className="quick-ask-field">
          <input
            value={quick}
            onChange={(event) => setQuick(event.target.value)}
            placeholder="What is 18% of 240? Or: convert 12 km to miles."
            aria-label="Prompt for the yard"
            maxLength={4000}
          />
          <button type="submit" className="btn btn-solid" disabled={asking || !quick.trim()}>
            {asking ? "Routing…" : "Send"} <ArrowGlyph />
          </button>
        </div>
      </form>

      {quickError ? <ErrorNote message={quickError} /> : null}

      {answer ? (
        <div className="quick-result">
          <div className="quick-result-main">
            <div className="quick-result-head">
              <TierBadge tier={answer.tier} />
              <span className="mono-meta">{answer.model}</span>
              {answer.cache_hit ? <Badge tone="cache">cache</Badge> : null}
              {answer.fallback_used ? <Badge tone="warn">fallback</Badge> : null}
            </div>
            <p className="quick-result-answer">{answer.text}</p>
            <div className="quick-result-meta">
              <span>score {answer.route.score.toFixed(2)}</span>
              <span>confidence {pct(answer.route.confidence, 0)}</span>
              <span>{latency(answer.latency_ms)}</span>
              <span>{money(answer.cost_usd)}</span>
              <span>saved {money(answer.saved_usd)}</span>
            </div>
          </div>
          <div className="quick-result-side">
            <button className="link-button" type="button" onClick={() => setSelected(answer.request_id)}>
              Open receipt <ArrowGlyph />
            </button>
            <small>{answer.route.summary}</small>
          </div>
        </div>
      ) : null}

      {!data && overview.loading ? (
        <div className="stat-grid">
          {[0, 1, 2, 3].map((index) => (
            <article className="stat" key={index}>
              <Skeleton lines={3} />
            </article>
          ))}
        </div>
      ) : null}

      {data ? (
        <>
          <div className="yard-window">
            <Segmented
              ariaLabel="Time window"
              options={HOURS}
              value={hours}
              onChange={setHours}
            />
            <span className="mono-meta">window: {windowLabel} · times in UTC</span>
          </div>

          <div className="stat-grid">
            <Stat
              label="Requests sealed"
              value={compact(data.stats.requests)}
              note={
                <>
                  {data.stats.ok} ok · {data.stats.errors} faults · {data.stats.blocked} blocked
                </>
              }
              accent="ink"
            />
            <Stat
              label="Spend avoided"
              value={money(data.stats.saved_usd)}
              note={
                <>
                  {pctValue(data.stats.saved_pct)} less than the prime baseline ·{" "}
                  {money(data.stats.cost_usd)} spent
                </>
              }
              accent="volt"
            />
            <Stat
              label="Cache hit rate"
              value={pct(data.stats.cache_hit_rate)}
              note={
                <>
                  {data.stats.cache_hits} answers served without a provider call
                </>
              }
              accent="periwinkle"
            />
            <Stat
              label="P95 latency"
              value={latency(data.stats.latency_p95_ms)}
              note={
                <>
                  average {latency(data.stats.latency_avg_ms)} · {grams(data.stats.saved_co2e_g)}{" "}
                  CO₂e avoided
                </>
              }
              accent="signal"
            />
          </div>

          <div className="yard-grid">
            <Panel
              kicker="Pulse"
              title="Traffic & spend"
              actions={<span className="mono-meta">{data.stats.requests} calls</span>}
            >
              <TrafficChart points={data.timeline.points} />
            </Panel>
            <Panel kicker="Where it went" title="Route mix">
              <RouteDonut mix={data.route_mix} />
            </Panel>
            <Panel kicker="Guard" title="Daily budget" className="panel-span">
              <BudgetGauge
                spent={data.guardrails.budget.spent}
                limit={data.guardrails.budget.limit}
                remaining={data.guardrails.budget.remaining}
              />
              <div className="mini-list">
                <span>
                  <DialGlyph /> rate limit <strong>{data.guardrails.limiter.rpm} rpm</strong>
                </span>
                <span>
                  <DialGlyph /> prompts stored{" "}
                  <strong>{data.meta.privacy.store_prompts ? "yes" : "no"}</strong>
                </span>
                <span>
                  <DialGlyph /> ledger key{" "}
                  <strong>{data.meta.privacy.default_ledger_key ? "dev default" : "custom"}</strong>
                </span>
              </div>
            </Panel>
          </div>

          <div className="yard-grid yard-grid-even">
            <Panel
              kicker="Last exam"
              title="The gauntlet says"
              actions={
                <Link to="/gauntlet" className="link-button">
                  full record <ArrowGlyph />
                </Link>
              }
            >
              {data.last_batch ? (
                <LastExam batch={data.last_batch} />
              ) : (
                <Empty
                  mark="36"
                  title="No exam on the board"
                  body="Thirty-six tasks, three policies, one chart. Run the gauntlet to turn opinions into receipts."
                  action={
                    <Link to="/gauntlet" className="btn btn-solid">
                      Set the policies <ArrowGlyph />
                    </Link>
                  }
                />
              )}
            </Panel>

            <Panel
              kicker="Ledger"
              title="The chain is the product"
              actions={
                <Link to="/ledger" className="link-button">
                  full ledger <ArrowGlyph />
                </Link>
              }
            >
              <div className="chain-card">
                <div className={`chain-seal ${data.guardrails.chain.ok ? "is-ok" : "is-bad"}`}>
                  <span>{data.guardrails.chain.ok ? "SEALED" : "BROKEN"}</span>
                  <strong>{data.guardrails.chain.entries}</strong>
                  <small>entries verified</small>
                </div>
                <div className="chain-copy">
                  <p>{data.guardrails.chain.detail}</p>
                  <p className="mono-meta">
                    checked {clock(data.guardrails.chain.checked_ms)} · HMAC-SHA256 links
                  </p>
                  <div className="breaker-row">
                    {Object.entries(data.guardrails.breakers).map(([name, health]) => (
                      <span className={`breaker breaker-${health.breaker.state}`} key={name}>
                        {name}: {health.breaker.state}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="chain-notes">
                <span>Costs logged per call</span>
                <span>Carbon estimated per token</span>
                <span>Prompts {data.meta.privacy.store_prompts ? "stored" : "reduced to previews"}</span>
              </div>
            </Panel>
          </div>

          <Panel
            kicker="Traffic tape"
            title="Recent receipts"
            actions={<span className="mono-meta">last {data.recent.length} calls</span>}
            bodyClassName="flush"
          >
            {data.recent.length ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Prompt</th>
                      <th>Rail</th>
                      <th>Model</th>
                      <th>Latency</th>
                      <th>Spend</th>
                      <th>Flags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent.map((row) => (
                      <ReceiptRow key={row.id} row={row} onOpen={() => setSelected(row.id)} />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="The tape is blank"
                body="Send a prompt from the yard or the dispatch desk. Receipts appear here within a second."
              />
            )}
          </Panel>

          <div className="yard-footnotes">
            <article>
              <IconNotes size={18} />
              <div>
                <h3>Why a gateway</h3>
                <p>
                  One contract for every provider, one place to enforce budgets, one ledger for
                  answers. Integrations get simpler as the model shelf grows.
                </p>
              </div>
            </article>
            <article>
              <IconGauntlet size={18} />
              <div>
                <h3>Why an exam</h3>
                <p>
                  Routing claims are cheap. Thirty-six fixed tasks across three policies make the
                  cost-quality trade visible, reproducible and CI-ready.
                </p>
              </div>
            </article>
            <article>
              <IconLedger size={18} />
              <div>
                <h3>Why receipts</h3>
                <p>
                  Model spend is hard to audit when prompts vanish. A chained receipt links prompt
                  hash, route, spend and answer in one row.
                </p>
              </div>
            </article>
          </div>
        </>
      ) : null}

      <RequestDrawer requestId={selected} onClose={() => setSelected(null)} />
    </>
  );
}

function LastExam({ batch }: { batch: NonNullable<Overview["last_batch"]> }) {
  const runs = batch.runs ?? [];
  const yard = runs.find((run) => run.policy === "yardmaster");
  const prime = runs.find((run) => run.policy === "prime");
  const comparison = batch.comparison?.yardmaster_vs_prime;

  if (!yard || !prime || !comparison) {
    return (
      <div className="last-exam">
        <div className="last-exam-head">
          <Stamp tone="ink">{batch.status}</Stamp>
          <span className="mono-meta">{batch.label}</span>
        </div>
        <p className="muted-copy">
          {batch.status === "running"
            ? `${batch.tasks_done} of ${batch.tasks_total} tasks scored. The comparison appears when the yardmaster crosses the line.`
            : "This batch did not produce a three-policy comparison. Run a full gauntlet."}
        </p>
        <Link to={`/gauntlet?batch=${batch.id}`} className="btn">
          Open batch <ArrowGlyph />
        </Link>
      </div>
    );
  }

  return (
    <div className="last-exam">
      <div className="last-exam-head">
        <Stamp tone={batch.status === "completed" ? "volt" : "ink"}>{batch.status}</Stamp>
        <span className="mono-meta">{batch.label}</span>
        <span className="mono-meta">{ago(batch.created_ms)}</span>
      </div>
      <div className="last-exam-numbers">
        <div>
          <span>router saved</span>
          <strong>{pctValue(comparison.cost_saved_pct)}</strong>
          <small>against always-prime</small>
        </div>
        <div>
          <span>pass delta</span>
          <strong className={comparison.pass_delta_pts < 0 ? "is-down" : "is-up"}>
            {signed(comparison.pass_delta_pts, 1, " pts")}
          </strong>
          <small>{pct(yard.pass_rate)} vs {pct(prime.pass_rate)}</small>
        </div>
        <div>
          <span>CO₂e saved</span>
          <strong>{pctValue(comparison.co2_saved_pct)}</strong>
          <small>{grams(yard.total_co2e_g)} router footprint</small>
        </div>
      </div>
      <div className="last-exam-runs">
        {runs.map((run) => (
          <Link key={run.id} to={`/gauntlet?batch=${batch.id}`} className="mini-run">
            <Badge tone={run.policy === "yardmaster" ? "volt" : run.policy}>
              {run.policy === "yardmaster" ? "router" : run.policy}
            </Badge>
            <strong>{pct(run.pass_rate)}</strong>
            <span>{money(run.total_cost_usd)}</span>
            <small>avg score {run.avg_score.toFixed(2)}</small>
          </Link>
        ))}
      </div>
      <p className="chart-note">
        {batch.tasks_total} scored outcomes. {batch.mode === "simulated" ? "Rehearsal prices, fixed dataset." : "Live prices, fixed dataset."}
      </p>
    </div>
  );
}

function ReceiptRow({ row, onOpen }: { row: RequestSummary; onOpen: () => void }) {
  return (
    <tr onClick={onOpen} tabIndex={0} onKeyDown={(event) => event.key === "Enter" && onOpen()}>
      <td className="cell-time">{clock(row.created_at)}</td>
      <td className="cell-prompt">
        <span>{row.prompt_preview || "—"}</span>
        <small>{row.source}</small>
      </td>
      <td>
        <StatusDot status={row.status} />
        <span className="cell-tier">{row.cache_hit ? "cache" : row.tier}</span>
      </td>
      <td className="cell-model">{row.model || "—"}</td>
      <td className="cell-num">{latency(row.latency_ms)}</td>
      <td className="cell-num">{money(row.cost_usd)}</td>
      <td>
        <span className="flag-row">
          {row.cache_hit ? <Badge tone="cache">cache</Badge> : null}
          {row.fallback_used ? <Badge tone="warn">fallback</Badge> : null}
          {!row.cache_hit && !row.fallback_used ? <span className="muted">—</span> : null}
        </span>
      </td>
    </tr>
  );
}
