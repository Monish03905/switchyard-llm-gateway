import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, apiUrl, errorMessage, isUnauthorized } from "../lib/api";
import { ago, dateShort, grams, latency, money, pct, pctValue, signed } from "../lib/format";
import { useFetch } from "../lib/hooks";
import type {
  BatchList,
  BatchResults,
  EvalBatch,
  EvalResult,
  RouteMap,
  RunPolicy,
} from "../lib/types";
import { useToast } from "../components/Toast";
import { RequestDrawer } from "../components/RequestDrawer";
import { TaskDrawer } from "../components/TaskDrawer";
import {
  Badge,
  Empty,
  ErrorNote,
  PageHeader,
  Panel,
  Skeleton,
  Stat,
  StatusDot,
  TierBadge,
} from "../components/UI";
import { CostPassNote, CostPassScatter, PolicyBars } from "../components/Charts";
import { ArrowGlyph } from "../components/Icons";

const POLICY_ORDER: RunPolicy[] = ["thrift", "prime", "yardmaster"];
const POLICY_LABEL: Record<RunPolicy, string> = {
  thrift: "Thrift rail",
  prime: "Prime rail",
  yardmaster: "Yardmaster",
};

export function GauntletPage() {
  const [params, setParams] = useSearchParams();
  const selectedId = params.get("batch");
  const [adminToken, setAdminToken] = useState(api.adminToken.get());
  const [policies, setPolicies] = useState<RunPolicy[]>([...POLICY_ORDER]);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [policyFilter, setPolicyFilter] = useState("all");
  const [passFilter, setPassFilter] = useState("all");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [receipt, setReceipt] = useState<string | null>(null);
  const [taskSheet, setTaskSheet] = useState<string | null>(null);
  const toast = useToast();

  const list = useFetch<BatchList>("/api/evals/batches", 2000);
  const detail = useFetch<EvalBatch>(selectedId ? `/api/evals/batches/${selectedId}` : null, 2000);
  const active = detail.data ? ["queued", "running", "cancelling"].includes(detail.data.status) : false;
  const results = useFetch<BatchResults>(
    selectedId ? `/api/evals/batches/${selectedId}/results?limit=400` : null,
    active ? 3000 : 0,
  );
  const routeMap = useFetch<RouteMap>("/api/evals/route-map?policy=auto");

  useEffect(() => {
    if (selectedId) return;
    const items = list.data?.items ?? [];
    if (!items.length) return;
    setParams({ batch: list.data?.active_batch ?? items[0].id }, { replace: true });
  }, [selectedId, list.data, setParams]);

  const batch = detail.data ?? list.data?.items.find((item) => item.id === selectedId) ?? null;
  const runs = detail.data?.runs ?? [];
  const comparison = detail.data?.comparison;
  const prime = runs.find((run) => run.policy === "prime");
  const yard = runs.find((run) => run.policy === "yardmaster");
  const routerSaving =
    prime && yard && prime.total_cost_usd > 0
      ? (1 - yard.total_cost_usd / prime.total_cost_usd) * 100
      : null;
  const passDelta = prime && yard ? (yard.pass_rate - prime.pass_rate) * 100 : null;

  const filtered = useMemo(() => {
    const rows = results.data?.results ?? [];
    return rows.filter((row) => {
      if (policyFilter !== "all" && row.policy !== policyFilter) return false;
      if (passFilter === "pass" && !row.passed) return false;
      if (passFilter === "fail" && row.passed) return false;
      return true;
    });
  }, [results.data, policyFilter, passFilter]);

  const togglePolicy = (policy: RunPolicy) => {
    setPolicies((current) =>
      current.includes(policy)
        ? current.filter((item) => item !== policy)
        : [...current, policy],
    );
  };

  const startBatch = async () => {
    if (!policies.length || busy) return;
    setBusy(true);
    setRunError(null);
    api.adminToken.set(adminToken.trim());
    try {
      const response = await api.post<{ batch: EvalBatch; tasks_per_policy: number }>(
        "/api/evals/batches",
        { policies, label: label.trim() },
        { admin: true },
      );
      toast.push(`Gauntlet queued: ${response.tasks_per_policy} tasks per policy.`, "ok");
      setParams({ batch: response.batch.id });
      setLabel("");
      list.reload();
      results.reload();
    } catch (error) {
      if (isUnauthorized(error)) {
        setRunError("That admin token was refused. Check ADMIN_TOKEN in the server environment.");
      } else {
        setRunError(errorMessage(error));
      }
    } finally {
      setBusy(false);
    }
  };

  const cancelBatch = async () => {
    if (!selectedId) return;
    api.adminToken.set(adminToken.trim());
    try {
      await api.post(`/api/evals/batches/${selectedId}/cancel`, {}, { admin: true });
      toast.push("Cancel noted. The yard will stop after the current task.", "warn");
      detail.reload();
      list.reload();
    } catch (error) {
      toast.push(errorMessage(error), "bad");
    }
  };

  return (
    <>
      <PageHeader
        kicker="Gauntlet / fixed 36-task exam"
        title={
          <>
            Three policies walk in. <em>The board tells the truth.</em>
          </>
        }
        lede="The same exam runs on the cheap rail, the strong rail, and the router. Answers, tool use and step discipline are scored separately, then priced."
        actions={
          <>
            {selectedId ? (
              <a className="btn" href={apiUrl(`/api/evals/batches/${selectedId}/results.csv`)}>
                Export CSV <ArrowGlyph />
              </a>
            ) : (
              <a className="btn" href={apiUrl("/api/evals/tasks")}>
                Task set (JSON) <ArrowGlyph />
              </a>
            )}
            <Link className="btn" to="/notes#exam">
              Exam notes
            </Link>
          </>
        }
      />

      <div className="exam-stats">
        <Stat
          label="Tasks per policy"
          value={batch?.tasks_total ? batch.tasks_total / Math.max(runs.length, 1) : 36}
          note="Fixed set, no sampling"
          accent="ink"
        />
        <Stat
          label="Router saving vs prime"
          value={routerSaving === null ? "—" : pctValue(routerSaving)}
          note={prime && yard ? `${money(prime.total_cost_usd)} → ${money(yard.total_cost_usd)}` : "run a batch"}
          accent="volt"
        />
        <Stat
          label="Pass-rate delta"
          value={passDelta === null ? "—" : `${signed(passDelta)} pts`}
          note="Router minus prime"
          accent="signal"
        />
        <Stat
          label="Router pass rate"
          value={yard ? pct(yard.pass_rate) : "—"}
          note={yard ? `${yard.passed} of ${yard.tasks_total} tasks` : "no run yet"}
          accent="periwinkle"
        />
      </div>

      <div className="gauntlet-grid">
        <div className="gauntlet-main">
          <Panel
            kicker={batch ? `Batch ${batch.id.slice(0, 8)}` : "Batch board"}
            title={batch?.label || "The board"}
            actions={
              batch ? (
                <div className="panel-action-row">
                  <StatusDot status={batch.status} />
                  <span className="mono-meta">{dateShort(batch.created_ms)}</span>
                  {["queued", "running"].includes(batch.status) ? (
                    <button type="button" className="link-button" onClick={cancelBatch}>
                      cancel
                    </button>
                  ) : null}
                </div>
              ) : null
            }
          >
            {detail.error ? <ErrorNote message={detail.error} onRetry={detail.reload} /> : null}
            {detail.loading && !batch ? <Skeleton lines={4} /> : null}
            {!selectedId && !detail.loading ? (
              <Empty
                mark="∅"
                title="No exam on the board"
                body="Queue the first gauntlet from the panel on the right. Thirty-six tasks per policy, about half a minute on the simulator."
              />
            ) : null}

            {batch ? (
              <div className="batch-board">
                <div className="batch-status-row">
                  <p>
                    <strong>{batch.tasks_done}</strong> / {batch.tasks_total} task-runs evaluated
                  </p>
                  <span className="mono-meta">
                    {batch.mode} · {ago(batch.created_ms)}
                  </span>
                </div>
                <div className="progress-track" aria-label="Batch progress">
                  <span style={{ width: `${Math.max(1, batch.progress * 100)}%` }} />
                </div>
                {batch.error ? <ErrorNote message={batch.error} /> : null}

                {comparison ? (
                  <div className="comparison-strip">
                    <div>
                      <span>router spend vs prime</span>
                      <strong>
                        {comparison.yardmaster_vs_prime
                          ? `−${pctValue(comparison.yardmaster_vs_prime.cost_saved_pct)}`
                          : "—"}
                      </strong>
                    </div>
                    <div>
                      <span>pass delta</span>
                      <strong>
                        {comparison.yardmaster_vs_prime
                          ? `${signed(comparison.yardmaster_vs_prime.pass_delta_pts)} pts`
                          : "—"}
                      </strong>
                    </div>
                    <div>
                      <span>tool-use delta</span>
                      <strong>
                        {comparison.yardmaster_vs_prime
                          ? `${signed(comparison.yardmaster_vs_prime.tool_delta_pts)} pts`
                          : "—"}
                      </strong>
                    </div>
                    <div>
                      <span>CO₂ saved</span>
                      <strong>
                        {comparison.yardmaster_vs_prime
                          ? pctValue(comparison.yardmaster_vs_prime.co2_saved_pct)
                          : "—"}
                      </strong>
                    </div>
                  </div>
                ) : null}

                <div className="run-cards">
                  {POLICY_ORDER.map((policy) => {
                    const run = runs.find((item) => item.policy === policy);
                    if (!run) {
                      return (
                        <article key={policy} className="run-card is-missing">
                          <header>
                            <Badge tone={policy === "prime" ? "prime" : policy === "thrift" ? "thrift" : "volt"}>
                              {POLICY_LABEL[policy]}
                            </Badge>
                          </header>
                          <p className="run-missing">Not in this batch.</p>
                        </article>
                      );
                    }
                    return (
                      <article key={policy} className={`run-card ${policy === "yardmaster" ? "is-router" : ""}`}>
                        <header>
                          <Badge tone={policy === "prime" ? "prime" : policy === "thrift" ? "thrift" : "volt"}>
                            {POLICY_LABEL[policy]}
                          </Badge>
                          <StatusDot status={run.status} />
                        </header>
                        <p className="run-rate">{pct(run.pass_rate)}</p>
                        <p className="run-sub">
                          {run.passed}/{run.tasks_total} passed · avg score {run.avg_score.toFixed(2)}
                        </p>
                        <div className="run-meters">
                          <span>tool use {pct(run.tool_rate, 0)}</span>
                          <span>{money(run.total_cost_usd)}</span>
                          <span>{latency(run.p95_latency_ms)} p95</span>
                          <span>{grams(run.total_co2e_g)}</span>
                          <span>{run.total_tokens.toLocaleString()} tok</span>
                        </div>
                        {run.error ? <p className="run-error">{run.error}</p> : null}
                      </article>
                    );
                  })}
                </div>

                {runs.length ? (
                  <>
                    <div className="chart-split">
                      <CostPassScatter runs={runs} />
                      <div className="chart-side">
                        <p className="panel-kicker">Pass rate</p>
                        <PolicyBars runs={runs} metric="pass_rate" formatter={(value) => pct(value, 0)} />
                        <p className="panel-kicker">Average score</p>
                        <PolicyBars
                          runs={runs}
                          metric="avg_score"
                          formatter={(value) => value.toFixed(2)}
                        />
                      </div>
                    </div>
                    <CostPassNote runs={runs} />
                  </>
                ) : null}
              </div>
            ) : null}
          </Panel>

          <Panel
            kicker="Drill-down"
            title="Every task, every score"
            actions={
              batch ? (
                <div className="panel-action-row">
                  <select value={policyFilter} onChange={(event) => setPolicyFilter(event.target.value)}>
                    <option value="all">all policies</option>
                    <option value="thrift">thrift</option>
                    <option value="prime">prime</option>
                    <option value="yardmaster">router</option>
                  </select>
                  <select value={passFilter} onChange={(event) => setPassFilter(event.target.value)}>
                    <option value="all">all results</option>
                    <option value="pass">passed</option>
                    <option value="fail">failed</option>
                  </select>
                </div>
              ) : null
            }
            className="results-panel"
          >
            {results.loading && !results.data ? <Skeleton lines={6} /> : null}
            {results.error ? <ErrorNote message={results.error} onRetry={results.reload} /> : null}
            {results.data && filtered.length === 0 ? (
              <Empty
                mark="·"
                title="Nothing under this filter"
                body="Clear the filters, or run the batch if the exam has not started yet."
              />
            ) : null}
            {filtered.length ? (
              <>
                <div className="table-scroll">
                  <table className="data-table result-table">
                    <thead>
                      <tr>
                        <th>Verdict</th>
                        <th>Task</th>
                        <th>Policy</th>
                        <th>Score</th>
                        <th>Steps</th>
                        <th>Spend</th>
                        <th>Time</th>
                        <th>Answer</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((row) => (
                        <ResultRow
                          key={row.id}
                          row={row}
                          open={expanded === row.id}
                          onToggle={() => setExpanded(expanded === row.id ? null : row.id)}
                          onReceipt={setReceipt}
                          onTask={setTaskSheet}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="table-foot">
                  {filtered.length} of {results.data?.results.length ?? 0} loaded results · weightings:
                  answer 0.60, tools 0.25, steps 0.15. Some sandboxed runs are cancelled, not failed.
                </p>
              </>
            ) : null}
          </Panel>
        </div>

        <div className="gauntlet-side">
          <Panel kicker="Control" title="Queue a gauntlet" className="run-form-panel">
            <p className="panel-lede">
              36 fixed tasks × {policies.length || 0} {policies.length === 1 ? "policy" : "policies"} ={" "}
              <strong>{(policies.length || 0) * 36} task-runs</strong>. One batch at a time keeps the yard
              honest.
            </p>

            <div className="field">
              <span>Policies</span>
              <div className="policy-picks">
                {POLICY_ORDER.map((policy) => {
                  const on = policies.includes(policy);
                  return (
                    <button
                      key={policy}
                      type="button"
                      className={`policy-pick ${on ? "is-on" : ""} policy-pick-${policy}`}
                      aria-pressed={on}
                      onClick={() => togglePolicy(policy)}
                    >
                      {POLICY_LABEL[policy]}
                      <small>{policy === "yardmaster" ? "router picks per task" : "pinned"}</small>
                    </button>
                  );
                })}
              </div>
            </div>

            <label className="field">
              <span>Label (optional)</span>
              <input
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                maxLength={120}
                placeholder="e.g. after router tuning"
              />
            </label>

            <label className="field">
              <span>Admin token</span>
              <input
                type="password"
                value={adminToken}
                onChange={(event) => setAdminToken(event.target.value)}
                placeholder="only needed if ADMIN_TOKEN is set"
                autoComplete="off"
              />
            </label>

            {runError ? <p className="inline-error">{runError}</p> : null}

            <button
              type="button"
              className="btn btn-solid btn-wide"
              onClick={startBatch}
              disabled={busy || !policies.length || Boolean(list.data?.running)}
            >
              {busy ? "Queuing…" : list.data?.running ? "A batch is already running" : "Run the exam"}
              <ArrowGlyph />
            </button>
            <p className="run-footnote">
              The simulator finishes in roughly 30 seconds. Live providers take longer and cost real
              tokens; the budget guard still applies.
            </p>
          </Panel>

          <Panel
            kicker="Route map"
            title="Where the 36 prompts land"
            actions={<span className="mono-meta">threshold {routeMap.data?.threshold ?? 0.33}</span>}
          >
            {routeMap.data ? (
              <>
                <div className="route-map-counts">
                  <div>
                    <TierBadge tier="thrift" />
                    <strong>{routeMap.data.counts.thrift}</strong>
                    <small>cheap rail</small>
                  </div>
                  <div>
                    <TierBadge tier="prime" />
                    <strong>{routeMap.data.counts.prime}</strong>
                    <small>strong rail</small>
                  </div>
                </div>
                <div className="route-map-grid">
                  {routeMap.data.tasks.map((task) => (
                    <span
                      key={task.task_id}
                      className={`route-chip route-chip-${task.tier}`}
                      title={`${task.prompt}\nscore ${task.score.toFixed(2)} · ${task.tier}\n${task.summary}`}
                    >
                      {task.task_id}
                    </span>
                  ))}
                </div>
                <p className="panel-note">
                  Computed from the human turn only, with agent scaffolding excluded, exactly as live
                  traffic is routed. {routeMap.data.note}
                </p>
              </>
            ) : routeMap.error ? (
              <ErrorNote message={routeMap.error} onRetry={routeMap.reload} />
            ) : (
              <Skeleton lines={3} />
            )}
          </Panel>

          <Panel kicker="History" title="Past gauntlets">
            {list.data?.items.length ? (
              <ul className="batch-history">
                {list.data.items.map((item) => {
                  const itemRuns = item.runs ?? [];
                  const yardRun = itemRuns.find((run) => run.policy === "yardmaster");
                  const primeRun = itemRuns.find((run) => run.policy === "prime");
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={item.id === selectedId ? "history-row is-current" : "history-row"}
                        onClick={() => {
                          setParams({ batch: item.id });
                          setExpanded(null);
                        }}
                      >
                        <span className={`history-bullet history-${item.status}`} />
                        <span className="history-main">
                          <strong>{item.label || item.id.slice(0, 10)}</strong>
                          <small>
                            {dateShort(item.created_ms)} · {item.status} · {item.tasks_done}/
                            {item.tasks_total}
                          </small>
                        </span>
                        <span className="history-rates">
                          {primeRun ? <em>P {pct(primeRun.pass_rate, 0)}</em> : null}
                          {yardRun ? <em>R {pct(yardRun.pass_rate, 0)}</em> : null}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : list.loading ? (
              <Skeleton lines={3} />
            ) : (
              <p className="panel-note">No history yet. The first run writes the baseline.</p>
            )}
            <Link to="/notes#exam" className="link-button">
              How grading works <ArrowGlyph />
            </Link>
          </Panel>
        </div>
      </div>

      <RequestDrawer requestId={receipt} onClose={() => setReceipt(null)} />
      <TaskDrawer taskId={taskSheet} onClose={() => setTaskSheet(null)} />
    </>
  );
}

function ResultRow({
  row,
  open,
  onToggle,
  onReceipt,
  onTask,
}: {
  row: EvalResult;
  open: boolean;
  onToggle: () => void;
  onReceipt: (id: string) => void;
  onTask: (id: string) => void;
}) {
  return (
    <>
      <tr className={open ? "is-open" : ""} onClick={onToggle}>
        <td>
          <span className={`verdict ${row.passed ? "verdict-pass" : "verdict-fail"}`}>
            {row.passed ? "PASS" : "MISS"}
          </span>
        </td>
        <td>
          <button
            type="button"
            className="task-inspect"
            onClick={(event) => {
              event.stopPropagation();
              onTask(row.task_id);
            }}
            title="Open the task sheet"
          >
            {row.task_id}
          </button>
          <span className="task-category">{row.category}</span>
        </td>
        <td>
          {row.policy ? (
            <Badge tone={row.policy === "prime" ? "prime" : row.policy === "thrift" ? "thrift" : "volt"}>
              {row.policy === "yardmaster" ? "router" : row.policy}
            </Badge>
          ) : (
            <span className="muted">—</span>
          )}
        </td>
        <td className="num">{row.total_score.toFixed(2)}</td>
        <td className="num">{row.steps_count}</td>
        <td className="num">{money(row.cost_usd)}</td>
        <td className="num">{latency(row.latency_ms)}</td>
        <td className="result-answer-cell">{row.answer || row.error || "—"}</td>
      </tr>
      {open ? (
        <tr className="result-expand-row">
          <td colSpan={8}>
            <div className="result-expand">
              <div className="result-copy">
                <p className="panel-kicker">Answer</p>
                <p>{row.answer || "—"}</p>
                <p className="panel-kicker">Expected</p>
                <p>{row.expected}</p>
                {row.error ? <p className="inline-error">{row.error}</p> : null}
                <button
                  type="button"
                  className="link-button"
                  onClick={() => onTask(row.task_id)}
                >
                  Task sheet <ArrowGlyph />
                </button>
              </div>
              <div className="result-scores">
                <div>
                  <span>answer</span>
                  <strong>{row.answer_score.toFixed(2)}</strong>
                </div>
                <div>
                  <span>tools</span>
                  <strong>{row.tool_score.toFixed(2)}</strong>
                </div>
                <div>
                  <span>steps</span>
                  <strong>{row.step_score.toFixed(2)}</strong>
                </div>
              </div>
              <div className="result-steps">
                {row.steps.length ? (
                  row.steps.map((step, index) => (
                    <span key={index} className={`step-chip step-${step.type} ${step.ok ? "" : "is-bad"}`}>
                      {step.type === "tool" ? `${step.tool}${step.ok ? " ✓" : " ×"}` : step.type}
                    </span>
                  ))
                ) : (
                  <span className="muted">no steps recorded</span>
                )}
              </div>
              {row.request_ids.length ? (
                <div className="receipt-links">
                  {row.request_ids.map((id) => (
                    <button
                      key={id}
                      type="button"
                      className="receipt-link"
                      onClick={(event) => {
                        event.stopPropagation();
                        onReceipt(id);
                      }}
                    >
                      {id}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}
