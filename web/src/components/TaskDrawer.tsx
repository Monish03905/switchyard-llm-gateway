import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useFetch } from "../lib/hooks";
import type { EvalTaskDetail } from "../lib/types";
import { titleCase } from "../lib/format";
import { ConfidenceMeter, ReasonBars, ScoreDial } from "./Charts";
import { Skeleton, TierBadge } from "./UI";

export function TaskDrawer({ taskId, onClose }: { taskId: string | null; onClose: () => void }) {
  const { data, error, loading } = useFetch<EvalTaskDetail>(
    taskId ? `/api/evals/tasks/${encodeURIComponent(taskId)}` : null,
  );

  useEffect(() => {
    if (!taskId) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.classList.add("is-locked");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("is-locked");
    };
  }, [taskId, onClose]);

  if (!taskId) return null;

  const threshold = Number(data?.route.features.threshold ?? 0.33);

  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Exam task sheet">
        <header className="drawer-head">
          <div>
            <p className="eyebrow">Exam task sheet</p>
            <h2>{taskId}</h2>
          </div>
          <button className="drawer-close" type="button" onClick={onClose} aria-label="Close task sheet">
            CLOSE ×
          </button>
        </header>

        <div className="drawer-body">
          {loading ? <Skeleton lines={7} /> : null}
          {error ? <div className="error-note">{error}</div> : null}
          {data ? (
            <>
              <div className="drawer-flags">
                <TierBadge tier={data.route.tier} />
                <span className="badge badge-muted">{titleCase(data.category)}</span>
                <span className="badge badge-muted">difficulty {data.difficulty}</span>
                <span className="drawer-time">{data.answer_type}</span>
              </div>

              <section className="drawer-section">
                <h3>Prompt</h3>
                <p className="drawer-prompt">{data.prompt}</p>
              </section>

              <section className="drawer-section">
                <h3>Reference answer</h3>
                <p className="drawer-answer">{data.expected}</p>
              </section>

              <section className="drawer-section">
                <h3>Grading contract</h3>
                <div className="drawer-kv-grid">
                  <div>
                    <span>step budget</span>
                    <strong>{data.max_steps}</strong>
                  </div>
                  <div>
                    <span>tools gate</span>
                    <strong>{data.strict_tools ? "strict" : "soft"}</strong>
                  </div>
                  <div>
                    <span>required tools</span>
                    <strong>{data.required_tools.length ? data.required_tools.join(", ") : "none"}</strong>
                  </div>
                </div>
                <p className="drawer-note">
                  Weighted 0.60 answer, 0.25 tools, 0.15 step discipline. A task that needed a tool fails
                  even with a lucky answer.
                </p>
              </section>

              <section className="drawer-section">
                <h3>Predicted route</h3>
                <p className="drawer-reason">{data.route.summary}</p>
                <div className="drawer-route-grid">
                  <ScoreDial
                    score={Number(data.route.score)}
                    threshold={threshold}
                    tier={data.route.tier}
                  />
                  <div>
                    <ConfidenceMeter confidence={data.route.confidence} />
                    <p className="drawer-note">
                      score {data.route.score.toFixed(2)} against threshold {threshold.toFixed(2)} ·
                      confidence {data.route.confidence.toFixed(2)}
                    </p>
                  </div>
                </div>
                <ReasonBars reasons={data.route.reasons} />
              </section>

              {data.note ? (
                <section className="drawer-section">
                  <h3>Designer note</h3>
                  <p className="drawer-reason">{data.note}</p>
                </section>
              ) : null}

              <p className="drawer-note">
                Task sheets are read-only. Actual grading runs live in the{" "}
                <Link to="/gauntlet" onClick={onClose}>
                  gauntlet drill-down
                </Link>
                .
              </p>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
