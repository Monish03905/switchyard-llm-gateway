import { useState } from "react";
import { Link } from "react-router-dom";
import { useDeferredValueCompat, useFetch } from "../lib/hooks";
import { apiUrl } from "../lib/api";
import type { ChainState, RequestPage } from "../lib/types";
import { clock, dateShort, latency, money, pct, shortHash, titleCase } from "../lib/format";
import { RequestDrawer } from "../components/RequestDrawer";
import {
  Badge,
  Empty,
  ErrorNote,
  PageHeader,
  Panel,
  Skeleton,
  Stamp,
  StatusDot,
  TierBadge,
} from "../components/UI";
import { ArrowGlyph } from "../components/Icons";

const PAGE_SIZE = 25;
const HOUR_OPTIONS = [
  { value: "24", label: "24 h" },
  { value: "168", label: "7 d" },
  { value: "720", label: "30 d" },
];

export function LedgerPage() {
  const [q, setQ] = useState("");
  const query = useDeferredValueCompat(q);
  const [hours, setHours] = useState("24");
  const [tier, setTier] = useState("all");
  const [status, setStatus] = useState("all");
  const [source, setSource] = useState("all");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);

  const params = new URLSearchParams({ hours, limit: String(PAGE_SIZE), offset: String(offset) });
  if (query.trim()) params.set("q", query.trim());
  if (tier !== "all") params.set("tier", tier);
  if (status !== "all") params.set("status", status);
  if (source !== "all") params.set("source", source);

  const page = useFetch<RequestPage>(`/api/requests?${params.toString()}`, 15_000);
  const chain = useFetch<ChainState>("/api/ledger/verify");

  const reset = (apply: () => void) => {
    apply();
    setOffset(0);
  };

  const total = page.data?.total ?? 0;
  const shown = page.data?.items.length ?? 0;

  return (
    <>
      <PageHeader
        kicker="Ledger / receipts"
        title={
          <>
            Every call leaves a receipt. <em>Change one byte and the chain screams.</em>
          </>
        }
        lede="Prompts, routes, prices and outcomes are written as an HMAC hash chain. Verify the whole ledger in one click, or pull the raw CSV for an audit folder."
        actions={
          <>
            <a className="btn" href={apiUrl(`/api/requests/export.csv?${params.toString()}`)}>
              Export filtered <ArrowGlyph />
            </a>
            <a className="btn" href={apiUrl("/api/ledger/export.csv")}>
              Full chain CSV
            </a>
          </>
        }
      />

      <Panel
        kicker="Chain integrity"
        title="The seal"
        className="chain-panel"
        actions={
          <button className="link-button" type="button" onClick={chain.reload}>
            verify now <ArrowGlyph />
          </button>
        }
      >
        {chain.error ? <ErrorNote message={chain.error} onRetry={chain.reload} /> : null}
        {chain.data ? (
          <div className={`chain-board ${chain.data.ok ? "is-sealed" : "is-broken"}`}>
            <div className="chain-seal">
              <Stamp tone={chain.data.ok ? "volt" : "signal"}>{chain.data.ok ? "SEALED" : "BROKEN"}</Stamp>
              <p>
                <strong>{chain.data.entries}</strong> receipts in the chain
              </p>
              <p className="mono-meta">
                checked {dateShort(chain.data.checked_ms)} · {clock(chain.data.checked_ms)} UTC
              </p>
            </div>
            <div className="chain-copy">
              <p>{chain.data.detail}</p>
              <p className="panel-note">
                Each row hashes its own payload with the previous entry&apos;s hash, then signs it with
                HMAC-SHA256. Reordering, editing or deleting a row breaks every link after it.
                {chain.data.broken_at ? ` First break at ${chain.data.broken_at}.` : ""}
              </p>
            </div>
            <div className="chain-glyphs" aria-hidden="true">
              {["prev", "payload", "hmac", "next"].map((label) => (
                <span key={label}>{label}</span>
              ))}
            </div>
          </div>
        ) : chain.loading ? (
          <Skeleton lines={3} />
        ) : null}
      </Panel>

      <Panel
        kicker="Request log"
        title="Receipts on file"
        actions={<span className="mono-meta">{total.toLocaleString()} matching</span>}
        className="ledger-panel"
      >
        <div className="filter-bar">
          <label className="field field-search">
            <span>Search</span>
            <input
              value={q}
              onChange={(event) => reset(() => setQ(event.target.value))}
              placeholder="prompt, id, model, route reason"
              maxLength={120}
            />
          </label>
          <label className="field field-compact">
            <span>Window</span>
            <select
              value={hours}
              onChange={(event) => reset(() => setHours(event.target.value))}
            >
              {HOUR_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field field-compact">
            <span>Tier</span>
            <select value={tier} onChange={(event) => reset(() => setTier(event.target.value))}>
              <option value="all">all tiers</option>
              <option value="thrift">thrift</option>
              <option value="prime">prime</option>
            </select>
          </label>
          <label className="field field-compact">
            <span>Status</span>
            <select value={status} onChange={(event) => reset(() => setStatus(event.target.value))}>
              <option value="all">all statuses</option>
              <option value="ok">ok</option>
              <option value="error">error</option>
              <option value="blocked">blocked</option>
            </select>
          </label>
          <label className="field field-compact">
            <span>Source</span>
            <select value={source} onChange={(event) => reset(() => setSource(event.target.value))}>
              <option value="all">all sources</option>
              <option value="api">api</option>
              <option value="playground">playground</option>
              <option value="eval">eval</option>
            </select>
          </label>
        </div>

        {page.error ? <ErrorNote message={page.error} onRetry={page.reload} /> : null}
        {page.loading && !page.data ? <Skeleton lines={6} /> : null}
        {page.data && shown === 0 ? (
          <Empty
            mark="∅"
            title="No receipts match"
            body="Widen the window or clear the filters. New calls land here within a couple of seconds."
            action={
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setQ("");
                  setTier("all");
                  setStatus("all");
                  setSource("all");
                  setHours("168");
                  setOffset(0);
                }}
              >
                Clear filters
              </button>
            }
          />
        ) : null}

        {shown ? (
          <>
            <div className="table-scroll">
              <table className="data-table ledger-table">
                <thead>
                  <tr>
                    <th>Receipt</th>
                    <th>When UTC</th>
                    <th>Rail</th>
                    <th>Source</th>
                    <th>Model</th>
                    <th className="num">Tokens</th>
                    <th className="num">Spend</th>
                    <th className="num">Saved</th>
                    <th className="num">Latency</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {page.data?.items.map((row) => (
                    <tr key={row.id} onClick={() => setSelected(row.id)} className="clickable-row">
                      <td>
                        <span className="mono-meta">{shortHash(row.id, 8, 4)}</span>
                        <span className="prompt-preview">{row.prompt_preview || "prompt withheld"}</span>
                      </td>
                      <td>
                        <span>{clock(row.created_ms)}</span>
                        <span className="cell-sub">{dateShort(row.created_ms)}</span>
                      </td>
                      <td>
                        <TierBadge tier={row.cache_hit ? "cache" : row.tier} />
                        {row.fallback_used ? (
                          <span className="cell-sub">
                            <Badge tone="warn">fallback</Badge>
                          </span>
                        ) : null}
                      </td>
                      <td>
                        <span className="mono-meta">{row.source}</span>
                        <span className="cell-sub">policy {row.policy}</span>
                      </td>
                      <td>
                        <span className="mono-meta">{row.model}</span>
                        <span className="cell-sub">{titleCase(row.provider)}</span>
                      </td>
                      <td className="num">{row.tokens.toLocaleString()}</td>
                      <td className="num">{money(row.cost_usd)}</td>
                      <td className="num saved-cell">{row.saved_usd > 0 ? money(row.saved_usd) : "—"}</td>
                      <td className="num">{latency(row.latency_ms)}</td>
                      <td>
                        <StatusDot status={row.status} />
                        <span className="cell-sub">conf {pct(row.route_confidence, 0)}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="pager">
              <span>
                {offset + 1}–{offset + shown} of {total.toLocaleString()}
              </span>
              <div className="pager-buttons">
                <button
                  type="button"
                  className="btn"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Newer
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={offset + shown >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Older
                  <ArrowGlyph />
                </button>
              </div>
            </div>
          </>
        ) : null}
      </Panel>

      <p className="ledger-footnote">
        Click any row to open the full receipt: prompt, response, route features, attempts, and the
        prev/entry hashes that tie it into the chain.{" "}
        <Link to="/notes#ledger" className="text-link">
          Why hash chains instead of a plain log?
        </Link>
      </p>

      <RequestDrawer requestId={selected} onClose={() => setSelected(null)} />
    </>
  );
}
