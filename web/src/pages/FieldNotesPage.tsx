import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { useFetch } from "../lib/hooks";
import type { Overview } from "../lib/types";
import { compact, grams, latency, pctValue } from "../lib/format";
import { ArrowGlyph } from "../components/Icons";
import { PageHeader, Panel, Stamp, TierBadge } from "../components/UI";

const TOC = [
  { id: "why", label: "Why a yard" },
  { id: "router", label: "Router notes" },
  { id: "reliability", label: "Reliability" },
  { id: "exam", label: "The exam" },
  { id: "ledger", label: "Receipts" },
  { id: "simulator", label: "Simulator" },
  { id: "api", label: "API" },
  { id: "ship", label: "Ship it" },
  { id: "stack", label: "Stack" },
];

const FEATURES = [
  { signal: "Code fence", weight: "+0.40", why: "A block is the strongest tell for reasoning work; backticks alone score +0.36." },
  { signal: "Reasoning language", weight: "+0.24", why: "Two or more verbs (explain, design, debug, compare) score +0.14 for one." },
  { signal: "Multi-step arithmetic", weight: "+0.36", why: "Three or more numbers plus a sequence word. A lone expression adds +0.10." },
  { signal: "Structured ask", weight: "+0.34", why: "list, steps, summarize, walk me through." },
  { signal: "Safety-sensitive words", weight: "+0.38", why: "Refusal quality is not a cheap-rail task." },
  { signal: "Unit conversion", weight: "+0.34", why: "Precision matters; the strong rail is steadier." },
  { signal: "Long brief", weight: "+0.20", why: "Past 900 characters; a +0.10 bump starts at 450." },
  { signal: "Extra questions", weight: "+0.08", why: "Each question mark after the first." },
  { signal: "Short lookup", weight: "−0.14", why: "One fact, one line, no need to burn prime tokens." },
  { signal: "Greeting / small talk", weight: "−0.30", why: "Politeness does not need a frontier model." },
];

export function FieldNotesPage() {
  const location = useLocation();
  const overview = useFetch<Overview>("/api/overview?hours=168", 30_000);
  const stats = overview.data?.stats;
  const yard = overview.data?.last_batch?.comparison?.yardmaster_vs_prime;

  useEffect(() => {
    if (!location.hash) return;
    const id = location.hash.slice(1);
    const timer = window.setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
    return () => window.clearTimeout(timer);
  }, [location.hash]);

  return (
    <>
      <PageHeader
        kicker="Field notes / the long version"
        title={
          <>
            A routing yard is a promise: <em>the right engine for the call.</em>
          </>
        }
        lede="Switchyard is an LLMOps working model — a gateway, a router that explains itself, a fixed exam, and a ledger you can audit. These are the notes I would want if I inherited it."
        actions={<Stamp tone="ink">REV 1.0 · NOV 2026</Stamp>}
      />

      <div className="proof-strip">
        <div>
          <span>requests this week</span>
          <strong>{stats ? compact(stats.requests) : "—"}</strong>
        </div>
        <div>
          <span>router saving vs prime</span>
          <strong>{yard ? pctValue(yard.cost_saved_pct) : stats ? pctValue(stats.saved_pct) : "—"}</strong>
        </div>
        <div>
          <span>p95 latency</span>
          <strong>{stats ? latency(stats.latency_p95_ms) : "—"}</strong>
        </div>
        <div>
          <span>CO₂e avoided</span>
          <strong>{stats ? grams(stats.saved_co2e_g) : "—"}</strong>
        </div>
      </div>

      <div className="notes-grid">
        <nav className="notes-toc" aria-label="Field notes sections">
          <p className="panel-kicker">On this page</p>
          <ol>
            {TOC.map((item, index) => (
              <li key={item.id}>
                <a href={`#${item.id}`}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  {item.label}
                </a>
              </li>
            ))}
          </ol>
          <div className="notes-toc-foot">
            <p>Read the receipts?</p>
            <Link to="/ledger" className="text-link">
              Open the ledger <ArrowGlyph />
            </Link>
          </div>
        </nav>

        <div className="notes-body">
          <section id="why" className="note-section">
            <p className="eyebrow">01 / Why a yard</p>
            <h2>Most LLM demos answer one question: can it talk?</h2>
            <p>
              Production asks three harder ones. Which model should take this call? What happens when it
              fails? Can you prove afterward what it cost and why it was chosen? Those questions are not
              model problems. They are yard problems: routing, signalling, records.
            </p>
            <p>
              So the project is built as a control room, not a chat window. A request enters one gate. The
              gate scores the human turn, looks at cache and circuit state, picks a rail, retries with
              backoff, falls back if it must, and writes a tamper-evident receipt. The cockpit shows the
              same story the API returns.
            </p>
            <div className="pull-quote">
              <p>
                A gateway is where an LLM stops being a demo and starts being an operating expense with a
                paper trail.
              </p>
              <span>— yardmaster&apos;s note, first shift</span>
            </div>
          </section>

          <Panel kicker="Architecture" title="One gate, two rails, one record" className="arch-panel">
            <div className="arch-board">
              <div className="arch-lane">
                <div className="arch-node">
                  <span className="arch-tag">edge</span>
                  <strong>Client / SDK</strong>
                  <small>OpenAI-compatible JSON</small>
                </div>
                <span className="arch-arrow" aria-hidden="true">
                  →
                </span>
                <div className="arch-node arch-gate">
                  <span className="arch-tag">gate</span>
                  <strong>FastAPI</strong>
                  <small>auth · rate limit · budget</small>
                </div>
                <span className="arch-arrow" aria-hidden="true">
                  →
                </span>
                <div className="arch-node arch-router">
                  <span className="arch-tag">signal</span>
                  <strong>Rule router</strong>
                  <small>weighted features, threshold 0.33</small>
                </div>
                <span className="arch-arrow" aria-hidden="true">
                  →
                </span>
                <div className="arch-node arch-rails">
                  <span className="arch-tag">rail</span>
                  <strong>Primary → fallback</strong>
                  <small>
                    <TierBadge tier="thrift" /> <TierBadge tier="prime" />
                  </small>
                </div>
              </div>
              <div className="arch-lane arch-lane-side">
                <div className="arch-node arch-small">
                  <span className="arch-tag">fast path</span>
                  <strong>Response cache</strong>
                  <small>exact match, TTL</small>
                </div>
                <div className="arch-node arch-small">
                  <span className="arch-tag">safety</span>
                  <strong>Circuit breaker</strong>
                  <small>closed · open · half-open</small>
                </div>
                <div className="arch-node arch-small">
                  <span className="arch-tag">tools</span>
                  <strong>Agent loop</strong>
                  <small>calculator · convert · lookup</small>
                </div>
                <div className="arch-node arch-small arch-ledger">
                  <span className="arch-tag">evidence</span>
                  <strong>HMAC receipt chain</strong>
                  <small>seq · prev hash · entry hash</small>
                </div>
              </div>
              <p className="arch-caption">
                The gauntlet runs the same gate with a fixed 36-task exam, so routing policy is measured
                with the wiring production actually uses.
              </p>
            </div>
          </Panel>

          <section id="router" className="note-section">
            <p className="eyebrow">02 / Router notes</p>
            <h2>The router explains itself, and it only reads the human.</h2>
            <p>
              The router is deliberately rule-based: fast, deterministic, and cheap enough to run on every
              call. Features add or subtract weight. Above <code>0.33</code> the call goes prime; below it
              stays thrift. Confidence grows with distance from the threshold, capped at 0.97 so the UI
              never claims certainty it has not earned.
            </p>
            <div className="feature-table">
              <div className="feature-head">
                <span>Signal</span>
                <span>Weight</span>
                <span>Why</span>
              </div>
              {FEATURES.map((row) => (
                <div className="feature-row" key={row.signal}>
                  <span>{row.signal}</span>
                  <strong className={row.weight.startsWith("+") ? "is-up" : row.weight.startsWith("−") ? "is-down" : ""}>
                    {row.weight}
                  </strong>
                  <span>{row.why}</span>
                </div>
              ))}
            </div>
            <p className="section-note">
              One correction matters: the router scores the <strong>user turn only</strong>. An earlier
              version scored the whole message list, including the agent&apos;s tool schema. Every agent
              call then looked like code and drifted to prime, erasing the savings the router existed to
              create. The fix is one filter, and it is the first thing the route map checks.
            </p>
          </section>

          <section id="reliability" className="note-section">
            <p className="eyebrow">03 / Reliability</p>
            <h2>Failure is a routing event, not an exception.</h2>
            <div className="two-col">
              <div>
                <h3>Retry, then fall back</h3>
                <p>
                  Provider errors that smell temporary — timeouts, 429s, 5xx — are retried with exponential
                  backoff and jitter, up to a small cap. If the primary stays down, the request moves to the
                  secondary provider on the same rail. Every attempt is recorded on the receipt, including
                  the ones that failed.
                </p>
                <h3>Break the circuit, not the yard</h3>
                <p>
                  Repeated failures open a breaker for that provider. While open, calls skip it and go
                  straight to the fallback. After a cooldown the breaker goes half-open: one probe decides
                  whether to close or stay open.
                </p>
              </div>
              <div>
                <h3>Cache only what is safe</h3>
                <p>
                  Responses are cached on an exact-match key: mode, tier, provider, model, normalised
                  messages, temperature. Hit <code>X-Switchyard-Cache: off</code> on the request when
                  freshness matters. The cache reports its hits and misses, and a purge lever exists for a
                  reason.
                </p>
                <h3>A budget guard with teeth</h3>
                <p>
                  A daily cap is checked before dispatch. Near the limit, prime routes can be downgraded.
                  At the limit, new prime spend is blocked with a 402 instead of quietly overrunning the
                  month.
                </p>
              </div>
            </div>
          </section>

          <section id="exam" className="note-section">
            <p className="eyebrow">04 / The exam</p>
            <h2>Thirty-six tasks that do not flatter a model.</h2>
            <p>
              The gauntlet is fixed on purpose. Quick arithmetic, multi-step word problems, unit
              conversions, reference lookups, code reading, extraction, planning, safety refusals, and
              traps. Each task is scored three ways:
            </p>
            <div className="score-weights">
              <div>
                <strong>0.60</strong>
                <span>answer</span>
                <small>exact, numeric tolerance, keyword set, or refusal quality</small>
              </div>
              <div>
                <strong>0.25</strong>
                <span>tools</span>
                <small>required tool used, and used in the right order</small>
              </div>
              <div>
                <strong>0.15</strong>
                <span>steps</span>
                <small>under the step budget, no wasted loops</small>
              </div>
            </div>
            <p>
              Three policies run the same set: <strong>thrift</strong> pinned cheap, <strong>prime</strong>{" "}
              pinned strong, and <strong>yardmaster</strong> letting the router choose per task. The
              scatter chart is the deliverable: cost on the x-axis, pass rate on the y-axis, and a 90% line
              for the eye. A router that saves money by failing more is not a win, and the board says so.
            </p>
            <p className="section-note">
              Two honest misses remain by design: a lookup answer that omits the exact keyword, and the
              strawberry letter count. The exam is not tuned until it flatters the router. If a task is
              wrong, the task gets fixed and every policy re-runs.
            </p>
            <Link to="/gauntlet" className="link-button">
              Open the exam board <ArrowGlyph />
            </Link>
          </section>

          <section id="ledger" className="note-section">
            <p className="eyebrow">05 / Receipts</p>
            <h2>A plain log can be edited. A chain argues back.</h2>
            <p>
              Every completed call is written as a receipt: prompt hash, route features, attempts, tokens,
              price, energy, carbon, and outcome. Each receipt hashes its payload together with the previous
              receipt&apos;s hash, then signs it with HMAC-SHA256. Editing, deleting or reordering a row
              breaks every link after it. One endpoint verifies the entire chain.
            </p>
            <p>
              Prompts themselves are a privacy choice. With <code>STORE_PROMPTS=false</code> only the hash
              is kept; the cockpit shows “prompt withheld” and the lane still reconciles. Turn storage on
              for a demo where the receipts should teach, off for traffic you do not own.
            </p>
            <div className="pull-quote">
              <p>Receipts, not vibes.</p>
              <span>The footer line is also the design rule.</span>
            </div>
          </section>

          <section id="simulator" className="note-section">
            <p className="eyebrow">06 / Simulator</p>
            <h2>The demo rail is not a model, and it says so.</h2>
            <p>
              With no provider key, Switchyard runs a deterministic simulated provider. It follows the same
              request contract, has a thrift model and a prime model with deliberately different behaviour,
              and is labelled <em>simulated</em> on every surface. It is calibrated so the router and exam
              are meaningful offline, not so the demo looks smarter than it is.
            </p>
            <p>
              It handles arithmetic, conversions, a small shelf of stable facts, and the 36 exam prompts.
              Open prose gets an honest refusal that points at the fix. Add <code>GROQ_API_KEY</code> or{" "}
              <code>OPENAI_API_KEY</code> to <code>.env</code>, restart, and the same requests go out on the
              live rail. The cockpit&apos;s mode badge flips from <em>simulator</em> to <em>live rail</em>.
            </p>
            <div className="simulator-callout">
              <Stamp tone="signal">HONESTY NOTE</Stamp>
              <p>
                If the badge says simulator, no external model was called. Numbers are still real
                measurements of this system — latency, tokens, cache, ledger — but the “model” is local
                code. Do not quote simulated quality as model quality.
              </p>
            </div>
          </section>

          <section id="api" className="note-section">
            <p className="eyebrow">07 / API</p>
            <h2>Drop-in shape, extra evidence.</h2>
            <p>
              The chat endpoint follows the OpenAI envelope, so an existing client can point at it with a
              base URL change. The extra <code>switchyard</code> block carries the route, attempts, cache
              status, spend avoided and carbon. Model aliases <code>auto</code>, <code>thrift</code> and{" "}
              <code>prime</code> work anywhere a model name does.
            </p>
            <pre className="code-block">{`curl -s http://127.0.0.1:8000/v1/chat/completions \\
  -H 'Content-Type: application/json' \\
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "What is 47 * 13?"}]
  }' | jq '.choices[0].message.content, .switchyard.tier'`}</pre>
            <p>
              The playground uses <code>POST /api/dispatch</code>; the agent loop is the same endpoint with{" "}
              <code>use_tools: true</code>. Interactive docs live at <a className="text-link" href="/docs">/docs</a>,
              Prometheus text metrics at <a className="text-link" href="/metrics/prometheus">/metrics/prometheus</a>.
            </p>
          </section>

          <section id="ship" className="note-section">
            <p className="eyebrow">08 / Ship it</p>
            <h2>The last mile is part of the build.</h2>
            <p>
              Docker builds the cockpit and serves it from FastAPI as static files, with SPA deep links
              falling back to <code>index.html</code>. Compose adds Postgres and Redis for a persistent
              deployment; SQLite and the in-memory cache are the zero-dependency defaults. A Render
              blueprint is included for a free-tier demo, and GitHub Actions runs lint, the test suite and
              a small eval gate before a deploy.
            </p>
            <pre className="code-block">{`cp .env.example .env      # add a provider key if you have one
docker compose up --build # app + postgres + redis
# or, locally:
uvicorn app.main:app --reload
cd web && npm install && npm run build`}</pre>
            <p>
              Environment variables that matter: <code>GROQ_API_KEY</code> or{" "}
              <code>OPENAI_API_KEY</code>, <code>ADMIN_TOKEN</code>, <code>LEDGER_KEY</code>,{" "}
              <code>DAILY_BUDGET_USD</code>, <code>DATABASE_URL</code>, <code>REDIS_URL</code>,{" "}
              <code>STORE_PROMPTS</code>. Secrets stay in <code>.env</code>; the file is gitignored and the
              image never bakes it in.
            </p>
          </section>

          <section id="stack" className="note-section">
            <p className="eyebrow">09 / Stack</p>
            <h2>Boring infrastructure, interesting decisions.</h2>
            <div className="stack-grid">
              <div>
                <h3>Backend</h3>
                <p>Python 3.11, FastAPI, SQLAlchemy async, httpx, Pydantic v2, SQLite or Postgres.</p>
              </div>
              <div>
                <h3>Frontend</h3>
                <p>React 19, TypeScript, Vite, React Router. Hand-rolled SVG charts, no chart dependency.</p>
              </div>
              <div>
                <h3>Ops</h3>
                <p>Docker multi-stage, Compose, GitHub Actions, Render blueprint, Prometheus text metrics.</p>
              </div>
              <div>
                <h3>Deliberate non-choices</h3>
                <p>
                  No vector database, no fine-tuning, no agent framework. The interesting work is in the
                  gate, not in hiding orchestration behind another layer.
                </p>
              </div>
            </div>
            <div className="notes-signoff">
              <p>
                Built to be read by a reviewer, not just run by a demo. If you are interviewing me, start
                with the route map, then ask why the agent earlier routed to prime. That answer is the
                project.
              </p>
              <span>— the yardmaster</span>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
