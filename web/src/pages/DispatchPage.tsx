import { useState, type FormEvent, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { useFetch } from "../lib/hooks";
import { api, errorMessage } from "../lib/api";
import type { AgentStep, DispatchResponse, Health, Policy } from "../lib/types";
import { grams, latency, money } from "../lib/format";
import { RouteReport } from "../components/RouteReport";
import { RequestDrawer } from "../components/RequestDrawer";
import { ArrowGlyph } from "../components/Icons";
import {
  Badge,
  Empty,
  ErrorNote,
  PageHeader,
  Panel,
  Segmented,
  Skeleton,
  Stamp,
  TierBadge,
  Toggle,
} from "../components/UI";

const POLICIES: { value: Policy; label: string; title: string }[] = [
  { value: "auto", label: "Auto", title: "The yardmaster decides" },
  { value: "thrift", label: "Thrift", title: "Pin to the cheap rail" },
  { value: "prime", label: "Prime", title: "Pin to the strong rail" },
];

const SAMPLES = [
  {
    label: "Quick math",
    prompt: "What is 15% of 240?",
    tools: false,
    note: "one operation · thrift",
  },
  {
    label: "Unit change",
    prompt: "What is 12 kilometers in miles?",
    tools: true,
    note: "conversion tool · thrift",
  },
  {
    label: "Fact shelf",
    prompt: "What is the capital of Canada?",
    tools: true,
    note: "lookup tool · thrift",
  },
  {
    label: "Exam prompt",
    prompt: "Explain in two sentences why retries need exponential backoff.",
    tools: false,
    note: "prose · prime",
  },
];

export function DispatchPage() {
  const [prompt, setPrompt] = useState("What is 15% of 240?");
  const [policy, setPolicy] = useState<Policy>("auto");
  const [tools, setTools] = useState(false);
  const [maxSteps, setMaxSteps] = useState(4);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DispatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const health = useFetch<Health>("/health", 30_000);

  const completion = result?.completion;
  const agent = result?.agent;
  const route =
    completion?.route ??
    agent?.steps
      .slice()
      .reverse()
      .find((step) => step.route)?.route;
  const receiptId = completion?.request_id ?? agent?.request_ids[0] ?? null;
  const simulated = health.data?.simulated ?? false;

  const dispatch = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!prompt.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await api.post<DispatchResponse>("/api/dispatch", {
        prompt: prompt.trim(),
        policy,
        use_tools: tools,
        max_steps: maxSteps,
      });
      setResult(response);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      dispatch();
    }
  };

  return (
    <>
      <PageHeader
        kicker="Dispatch desk / playground"
        title={
          <>
            Put a prompt through the gate. <em>See the reasoning.</em>
          </>
        }
        lede="One composer, two rails. Choose a policy or let the yardmaster score the prompt and pick. Tool runs show every step and every receipt."
        actions={
          <Link to="/ledger" className="btn">
            Receipts <ArrowGlyph />
          </Link>
        }
      />

      <div className="dispatch-grid">
        <div className="dispatch-column">
          <Panel kicker="Composer" title="Shape the call" className="composer-panel">
            <form onSubmit={dispatch}>
              <label className="field">
                <span>Prompt</span>
                <textarea
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  onKeyDown={onKeyDown}
                  rows={7}
                  maxLength={8000}
                  placeholder="Ask for arithmetic, a conversion, a reference fact, or a planning answer."
                />
              </label>

              <div className="composer-controls">
                <div className="field">
                  <span>Policy</span>
                  <Segmented
                    ariaLabel="Routing policy"
                    options={POLICIES}
                    value={policy}
                    onChange={setPolicy}
                  />
                </div>
                <div className="field field-compact">
                  <span>Tools</span>
                  <Toggle
                    checked={tools}
                    onChange={setTools}
                    label="Run the agent loop"
                    hint="calculator, convert, lookup"
                  />
                </div>
                {tools ? (
                  <div className="field field-compact">
                    <span>Step budget</span>
                    <select value={maxSteps} onChange={(event) => setMaxSteps(Number(event.target.value))}>
                      <option value={3}>3 steps</option>
                      <option value={4}>4 steps</option>
                      <option value={6}>6 steps</option>
                    </select>
                  </div>
                ) : null}
              </div>

              <div className="composer-actions">
                <button type="submit" className="btn btn-solid" disabled={loading || !prompt.trim()}>
                  {loading ? "Dispatching…" : tools ? "Dispatch agent" : "Dispatch"}
                  <ArrowGlyph />
                </button>
                <span className="composer-hint">⌘ / Ctrl + Enter</span>
                {simulated ? <Badge tone="warn">simulator</Badge> : <Badge tone="ok">live rail</Badge>}
              </div>
            </form>

            <div className="sample-shelf">
              <p className="sample-label">Load a proven prompt</p>
              <div className="sample-grid">
                {SAMPLES.map((sample) => (
                  <button
                    key={sample.label}
                    type="button"
                    className="sample-card"
                    onClick={() => {
                      setPrompt(sample.prompt);
                      setTools(sample.tools);
                      setResult(null);
                      setError(null);
                    }}
                  >
                    <strong>{sample.label}</strong>
                    <span>{sample.prompt}</span>
                    <small>{sample.note}</small>
                  </button>
                ))}
              </div>
            </div>

            {simulated ? (
              <p className="simulator-note">
                <strong>Simulator boundary:</strong> arithmetic, conversions, the fact shelf, and the
                36 exam prompts answer offline. Open prose needs a Groq or OpenAI key in <code>.env</code>.
              </p>
            ) : null}
          </Panel>

          <div className="rules-card">
            <p className="panel-kicker">What the router sees</p>
            <div className="rule-line">
              <span>+</span>
              <p>Code fences, reasoning verbs, multi-step arithmetic, unit changes, safety words.</p>
            </div>
            <div className="rule-line">
              <span>−</span>
              <p>Short lookups and greetings pull the score down. The threshold sits at 0.33.</p>
            </div>
            <div className="rule-line">
              <span>·</span>
              <p>Agent scaffolding is excluded. The router scores the human turn, not the tool schema.</p>
            </div>
            <Link to="/notes#router" className="link-button">
              Read the routing notes <ArrowGlyph />
            </Link>
          </div>
        </div>

        <div className="dispatch-column">
          <Panel
            kicker="Answer"
            title={loading ? "On the rail" : agent ? "Agent finished" : completion ? "Delivered" : "Waiting for a call"}
            actions={
              receiptId ? (
                <button className="link-button" type="button" onClick={() => setSelected(receiptId)}>
                  receipt <ArrowGlyph />
                </button>
              ) : null
            }
          >
            {loading ? <Skeleton lines={5} /> : null}
            {error ? <ErrorNote message={error} /> : null}
            {!loading && !result && !error ? (
              <Empty
                mark="→"
                title="No call on the board"
                body="Pick a sample or write a prompt. The answer, the route and the meter will land here together."
              />
            ) : null}

            {completion ? (
              <div className="answer-sheet">
                <div className="answer-flags">
                  <Stamp tone="volt">ANSWER</Stamp>
                  <TierBadge tier={completion.tier} />
                  {completion.cache_hit ? <Badge tone="cache">cache</Badge> : null}
                  {completion.fallback_used ? <Badge tone="warn">fallback</Badge> : null}
                  <span className="mono-meta">{completion.model}</span>
                </div>
                <p className="answer-text">{completion.text}</p>
                <div className="answer-meta">
                  <span>{completion.usage.total_tokens.toLocaleString()} tokens</span>
                  <span>{money(completion.cost_usd)}</span>
                  <span>{latency(completion.latency_ms)}</span>
                  <span>{grams(completion.co2e_g)}</span>
                  <span>saved {money(completion.saved_usd)}</span>
                </div>
                <div className="attempt-strip">
                  {completion.attempts.map((attempt, index) => (
                    <span key={index} className={`attempt-chip attempt-${attempt.status}`}>
                      {attempt.provider}/{attempt.model} · {attempt.status}
                      {attempt.latency_ms ? ` · ${latency(attempt.latency_ms)}` : ""}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {agent ? (
              <div className="answer-sheet">
                <div className="answer-flags">
                  <Stamp tone={agent.error ? "signal" : "volt"}>{agent.error ? "STOPPED" : "ANSWER"}</Stamp>
                  <Badge tone="ink">{agent.steps_count} steps</Badge>
                  {agent.tier ? <TierBadge tier={agent.tier} /> : null}
                  <span className="mono-meta">{agent.model || agent.provider}</span>
                </div>
                {agent.error ? <ErrorNote message={agent.error} /> : null}
                <p className="answer-text">{agent.answer || "The agent stopped without an answer."}</p>
                <div className="answer-meta">
                  <span>{agent.usage.total_tokens.toLocaleString()} tokens</span>
                  <span>{money(agent.cost_usd)}</span>
                  <span>{latency(agent.latency_ms)}</span>
                  <span>{grams(agent.co2e_g)}</span>
                  <span>stop: {agent.stopped_reason}</span>
                </div>
                <div className="receipt-links">
                  {agent.request_ids.map((id) => (
                    <button key={id} type="button" className="receipt-link" onClick={() => setSelected(id)}>
                      {id}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </Panel>

          {route ? (
            <Panel
              kicker="Route report"
              title={completion ? "Why this rail" : "Why the final rail"}
              className="route-panel"
            >
              <RouteReport
                route={route}
                model={completion?.model ?? agent?.model}
                provider={completion?.provider ?? agent?.provider}
                tokens={completion?.usage.total_tokens ?? agent?.usage.total_tokens}
                cost={completion?.cost_usd ?? agent?.cost_usd}
                saved={completion?.saved_usd}
                co2={completion?.co2e_g ?? agent?.co2e_g}
                latencyMs={completion?.latency_ms ?? agent?.latency_ms}
                cacheHit={completion?.cache_hit}
                fallbackUsed={completion?.fallback_used}
                onOpenReceipt={receiptId ? () => setSelected(receiptId) : undefined}
              />
            </Panel>
          ) : null}

          {agent ? (
            <Panel kicker="Agent loop" title="Step by step" className="trace-panel">
              <TraceTimeline steps={agent.steps} />
            </Panel>
          ) : null}
        </div>
      </div>

      <RequestDrawer requestId={selected} onClose={() => setSelected(null)} />
    </>
  );
}

function TraceTimeline({ steps }: { steps: AgentStep[] }) {
  return (
    <ol className="trace">
      {steps.map((step, index) => (
        <li key={`${step.n}-${index}`} className={`trace-step trace-${step.type}`}>
          <div className="trace-rail" aria-hidden="true">
            <span className={`trace-node ${step.ok ? "is-ok" : "is-bad"}`} />
          </div>
          <div className="trace-body">
            <header className="trace-head">
              <span className="trace-n">STEP {String(step.n).padStart(2, "0")}</span>
              <Badge tone={step.type === "tool" ? "thrift" : step.type === "answer" ? "volt" : "bad"}>
                {step.type}
              </Badge>
              {step.tier ? <span className="mono-meta">{step.tier} rail</span> : null}
              {step.route ? <span className="mono-meta">score {step.route.score.toFixed(2)}</span> : null}
              {step.latency_ms ? <span className="mono-meta">{latency(step.latency_ms)}</span> : null}
            </header>

            {step.type === "tool" ? (
              <>
                <div className="trace-call">
                  <code>{step.tool}</code>
                  <span>{JSON.stringify(step.args)}</span>
                </div>
                <pre className={`trace-result ${step.ok ? "" : "is-bad"}`}>{step.result}</pre>
              </>
            ) : null}

            {step.type === "answer" ? <p className="trace-answer">{step.answer}</p> : null}
            {step.error ? <p className="trace-error">{step.error}</p> : null}
            {step.note ? <p className="trace-note">{step.note}</p> : null}
            {step.route ? <p className="trace-why">why: {step.route.summary}</p> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
