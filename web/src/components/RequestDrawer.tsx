import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useFetch } from "../lib/hooks";
import type { RequestDetail } from "../lib/types";
import { clock, grams, latency, money, shortHash, titleCase } from "../lib/format";
import { ConfidenceMeter, ReasonBars, ScoreDial } from "./Charts";
import { Skeleton, StatusDot, TierBadge } from "./UI";

export function RequestDrawer({ requestId, onClose }: { requestId: string | null; onClose: () => void }) {
  const { data, error, loading } = useFetch<RequestDetail>(
    requestId ? `/api/requests/${encodeURIComponent(requestId)}` : null,
  );

  useEffect(() => {
    if (!requestId) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.classList.add("is-locked");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("is-locked");
    };
  }, [requestId, onClose]);

  if (!requestId) return null;

  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Receipt detail">
        <header className="drawer-head">
          <div>
            <p className="eyebrow">Receipt dossier</p>
            <h2>{shortHash(requestId, 12, 8)}</h2>
          </div>
          <button className="drawer-close" type="button" onClick={onClose} aria-label="Close receipt">
            CLOSE ×
          </button>
        </header>

        <div className="drawer-body">
          {loading ? <Skeleton lines={7} /> : null}
          {error ? <div className="error-note">{error}</div> : null}
          {data ? (
            <>
              <div className="drawer-flags">
                <StatusDot status={data.status} />
                <TierBadge tier={data.tier} />
                {data.cache_hit ? <span className="badge badge-cache">cache hit</span> : null}
                {data.fallback_used ? <span className="badge badge-warn">fallback</span> : null}
                <span className="drawer-time">{clock(data.created_at)}</span>
              </div>

              <section className="drawer-section">
                <h3>Prompt</h3>
                <p className="drawer-prompt">{(data.prompt_text ?? data.prompt_preview) || "—"}</p>
                {!data.prompt_text ? (
                  <p className="privacy-note">
                    Full prompt storage is off. This preview is the only trace on disk.
                  </p>
                ) : null}
              </section>

              <section className="drawer-section">
                <h3>Answer</h3>
                <p className="drawer-answer">{(data.response_text ?? data.response_preview) || data.error || "—"}</p>
              </section>

              <section className="drawer-section">
                <h3>Why this rail</h3>
                <p className="drawer-reason">{data.route_reason}</p>
                <div className="drawer-route-grid">
                  <ScoreDial
                    score={Number(data.features.score ?? 0)}
                    threshold={data.features.threshold ?? 0.33}
                    tier={data.tier}
                  />
                  <div>
                    <ConfidenceMeter confidence={data.route_confidence} />
                    <p className="drawer-note">
                      {data.requested_model === "auto" ? "auto policy" : `requested ${data.requested_model}`} ·{" "}
                      {data.attempts} attempt{data.attempts === 1 ? "" : "s"}
                    </p>
                    <p className="drawer-note">
                      {data.features.chars ?? 0} chars · {data.features.approx_tokens ?? 0} approx tokens ·{" "}
                      {data.features.numbers ?? 0} numbers
                    </p>
                  </div>
                </div>
                <ReasonBars reasons={data.features.contributions ?? []} />
              </section>

              <section className="drawer-section">
                <h3>Attempts</h3>
                <ol className="attempt-list">
                  {data.attempts_detail.map((attempt, index) => (
                    <li key={index}>
                      <span className={`attempt-dot attempt-${attempt.status}`} />
                      <div>
                        <strong>
                          {attempt.provider} / {attempt.model}
                        </strong>
                        <small>
                          {attempt.tier} rail · {attempt.status}
                          {attempt.latency_ms ? ` · ${latency(attempt.latency_ms)}` : ""}
                          {attempt.retry ? ` · retry ${attempt.retry}` : ""}
                        </small>
                        {attempt.error ? <em>{attempt.error}</em> : null}
                      </div>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="drawer-section">
                <h3>Meter</h3>
                <div className="drawer-kv-grid">
                  <div><span>spend</span><strong>{money(data.cost_usd)}</strong></div>
                  <div><span>baseline</span><strong>{money(data.baseline_cost_usd)}</strong></div>
                  <div><span>avoided</span><strong>{money(data.saved_usd)}</strong></div>
                  <div><span>tokens</span><strong>{data.tokens.toLocaleString()}</strong></div>
                  <div><span>latency</span><strong>{latency(data.latency_ms)}</strong></div>
                  <div><span>CO₂e</span><strong>{grams(data.co2e_g)}</strong></div>
                </div>
                <p className="drawer-note">
                  {data.provider || "no provider"} · {data.model || "no model"} · source {titleCase(data.source)}
                </p>
              </section>

              <section className="drawer-section">
                <h3>Chain</h3>
                <div className="hash-list">
                  <div><span>seq</span><code>{data.seq}</code></div>
                  <div><span>prompt</span><code>{shortHash(data.prompt_hash, 14, 10)}</code></div>
                  <div><span>prev</span><code>{shortHash(data.prev_hash, 14, 10)}</code></div>
                  <div><span>entry</span><code>{shortHash(data.entry_hash, 14, 10)}</code></div>
                </div>
                <p className="drawer-note">
                  Each entry hashes the one above it with an HMAC key. Edit a row and the chain below breaks.
                </p>
              </section>

              {data.batch_id ? (
                <section className="drawer-section">
                  <h3>Exam links</h3>
                  <p className="drawer-note">
                    Batch{" "}
                    <Link to={`/gauntlet?batch=${data.batch_id}`} onClick={onClose}>
                      {shortHash(data.batch_id, 10, 6)}
                    </Link>
                    {data.task_id ? ` · task ${data.task_id}` : ""}
                  </p>
                </section>
              ) : null}

              <details className="drawer-json">
                <summary>Raw routing features</summary>
                <pre>{JSON.stringify(data.features, null, 2)}</pre>
              </details>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
