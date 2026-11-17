import { useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage, isUnauthorized } from "../lib/api";
import { ago, compact, latency, money, titleCase } from "../lib/format";
import { useFetch } from "../lib/hooks";
import type { AdminState, ProbeResult, ProviderPage } from "../lib/types";
import { useToast } from "../components/Toast";
import { BudgetGauge } from "../components/Charts";
import { ArrowGlyph } from "../components/Icons";
import {
  Badge,
  ErrorNote,
  KeyValue,
  PageHeader,
  Panel,
  Skeleton,
  Stamp,
  Stat,
} from "../components/UI";

export function SwitchboardPage() {
  const [token, setToken] = useState(api.adminToken.get());
  const [fails, setFails] = useState(2);
  const [probing, setProbing] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();

  const providers = useFetch<ProviderPage>("/api/providers", 10_000);
  const admin = useFetch<AdminState>("/api/admin/state", 5000, true);
  const state = admin.data;

  const applyToken = () => {
    api.adminToken.set(token.trim());
    admin.reload();
    providers.reload();
    toast.push(token.trim() ? "Admin token stored for this tab." : "Admin token cleared.", "ok");
  };

  const guard = async (action: () => Promise<void>) => {
    api.adminToken.set(token.trim());
    try {
      await action();
      providers.reload();
      admin.reload();
    } catch (error) {
      toast.push(
        isUnauthorized(error)
          ? "Admin token refused. Set ADMIN_TOKEN on the server and paste it here."
          : errorMessage(error),
        "bad",
      );
    }
  };

  const probe = async (name: string) => {
    setProbing(name);
    await guard(async () => {
      const result = await api.post<ProbeResult>(`/api/providers/${name}/probe`, {}, { admin: true });
      toast.push(
        result.ok
          ? `${name} answered in ${latency(result.latency_ms ?? 1)}`
          : `${name} probe failed: ${result.error ?? "unknown error"}`,
        result.ok ? "ok" : "bad",
      );
    });
    setProbing(null);
  };

  const armSquall = async () => {
    setBusy("squall");
    await guard(async () => {
      const result = await api.post<{ detail: string }>("/api/admin/squall", { fails }, { admin: true });
      toast.push(result.detail, "warn");
    });
    setBusy(null);
  };

  const disarmSquall = async () => {
    setBusy("squall");
    await guard(async () => {
      const result = await api.del<{ detail: string }>("/api/admin/squall", { admin: true });
      toast.push(result.detail, "ok");
    });
    setBusy(null);
  };

  const purgeCache = async () => {
    setBusy("cache");
    await guard(async () => {
      const result = await api.post<{ removed: number; note: string }>(
        "/api/admin/cache/purge",
        {},
        { admin: true },
      );
      toast.push(`${result.note} (${result.removed} entries removed)`, "ok");
    });
    setBusy(null);
  };

  const resetBreakers = async () => {
    setBusy("breaker");
    await guard(async () => {
      await api.post("/api/admin/breakers/reset", {}, { admin: true });
      toast.push("Breakers reset to closed.", "ok");
    });
    setBusy(null);
  };

  return (
    <>
      <PageHeader
        kicker="Switchboard / providers & levers"
        title={
          <>
            Fail loudly. Route around it. <em>Leave the evidence.</em>
          </>
        }
        lede="Probe providers, trip the breaker, arm a simulated squall, or burn the cache. Every lever writes its effect straight into the ledger."
        actions={
          <Link to="/ledger" className="btn">
            Watch the ledger <ArrowGlyph />
          </Link>
        }
      />

      <div className="switch-stats">
        <Stat
          label="Mode"
          value={providers.data ? titleCase(providers.data.mode) : "—"}
          note={providers.data?.note}
          accent="ink"
        />
        <Stat
          label="Cache"
          value={state ? compact(state.levers.cache.entries) : "—"}
          note={state ? `${state.levers.cache.hits} hits · ${state.levers.cache.misses} misses` : "admin view"}
          accent="volt"
        />
        <Stat
          label="Breaker failures"
          value={state ? Object.values(state.levers.breakers).reduce((sum, item) => sum + item.breaker.failures_in_window, 0) : "—"}
          note="across providers, rolling window"
          accent="signal"
        />
        <Stat
          label="Ledger"
          value={state?.levers.chain.ok ? "Sealed" : state ? "Broken" : "—"}
          note={state ? `${state.levers.chain.entries} entries` : "admin view"}
          accent="periwinkle"
        />
      </div>

      <div className="switch-grid">
        <div className="switch-main">
          <Panel
            kicker="Provider rail"
            title="Who is on shift"
            actions={
              providers.data ? <span className="mono-meta">fallback → {providers.data.fallback_provider ?? "none"}</span> : null
            }
          >
            {providers.error ? <ErrorNote message={providers.error} onRetry={providers.reload} /> : null}
            {providers.loading && !providers.data ? <Skeleton lines={5} /> : null}
            {providers.data ? (
              <>
                <div className="fallback-chain">
                  {providers.data.providers.map((provider, index) => (
                    <span key={provider.name} className="chain-node">
                      <span className="chain-step">{index === 0 ? "primary" : "secondary"}</span>
                      <strong>{provider.name}</strong>
                      <small>{provider.simulated ? "simulated" : provider.configured ? "key present" : "no key"}</small>
                    </span>
                  ))}
                  {providers.data.providers.length < 2 ? (
                    <span className="chain-node chain-node-empty">
                      <span className="chain-step">fallback</span>
                      <strong>none</strong>
                      <small>add a second provider key</small>
                    </span>
                  ) : null}
                </div>

                <div className="provider-grid">
                  {providers.data.providers.map((provider) => {
                    const health = providers.data?.health[provider.name];
                    const breaker = health?.breaker;
                    const last = health?.last_probe;
                    return (
                      <article key={provider.name} className="provider-card">
                        <header>
                          <div>
                            <h3>{provider.name}</h3>
                            <p className="mono-meta">{provider.kind}</p>
                          </div>
                          <div className="provider-flags">
                            {provider.name === providers.data?.primary ? <Badge tone="volt">primary</Badge> : null}
                            {provider.simulated ? <Badge tone="warn">simulated</Badge> : null}
                            <Badge tone={provider.configured ? "ok" : "muted"}>
                              {provider.configured ? "configured" : "unconfigured"}
                            </Badge>
                          </div>
                        </header>

                        <div className="provider-models">
                          {Object.entries(provider.models ?? {}).map(([tier, model]) => (
                            <div key={tier}>
                              <span>{tier}</span>
                              <code>{model}</code>
                            </div>
                          ))}
                        </div>

                        <BreakerCard breaker={breaker} />

                        <div className="provider-actions">
                          <button
                            type="button"
                            className="btn btn-small"
                            onClick={() => probe(provider.name)}
                            disabled={probing === provider.name}
                          >
                            {probing === provider.name ? "probing…" : "Probe"}
                          </button>
                          {last ? (
                            <span className={`probe-note ${last.ok ? "is-ok" : "is-bad"}`}>
                              {last.ok ? `ok ${latency(last.latency_ms ?? 1)}` : last.error}
                              {last.checked_ms ? ` · ${ago(last.checked_ms)}` : ""}
                            </span>
                          ) : (
                            <span className="probe-note">no probe on file</span>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </>
            ) : null}
          </Panel>

          <Panel kicker="Price sheet" title="Catalog & energy" className="catalog-panel">
            {providers.data ? (
              <div className="table-scroll">
                <table className="data-table catalog-table">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Rail</th>
                      <th className="num">$/M in</th>
                      <th className="num">$/M out</th>
                      <th className="num">kWh / 1k</th>
                      <th className="num">Context</th>
                      <th>Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {providers.data.catalog.map((model) => (
                      <tr key={`${model.provider}-${model.model}`}>
                        <td>
                          <span className="mono-meta">{model.model}</span>
                          <span className="cell-sub">{model.vendor}</span>
                        </td>
                        <td>
                          <Badge tone={model.tier === "prime" ? "prime" : "thrift"}>{model.tier}</Badge>
                        </td>
                        <td className="num">{money(model.input_per_m)}</td>
                        <td className="num">{money(model.output_per_m)}</td>
                        <td className="num">{model.energy_kwh_per_1k.toFixed(3)}</td>
                        <td className="num">{compact(model.context)}</td>
                        <td className="catalog-note">{model.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Skeleton lines={5} />
            )}
            <p className="table-foot">
              Prices and energy live in <code>app/gateway/cost.py</code>, one row per model. The carbon
              estimate multiplies energy by PUE and grid intensity, both configurable.
            </p>
          </Panel>
        </div>

        <div className="switch-side">
          <Panel kicker="Access" title="Admin token">
            <p className="panel-lede">
              Read-only telemetry is open. Levers and batch starts require the admin token set on the
              server (<code>ADMIN_TOKEN</code>). It never leaves this tab.
            </p>
            <label className="field">
              <span>Token</span>
              <input
                type="password"
                value={token}
                onChange={(event) => setToken(event.target.value)}
                placeholder="paste admin token"
                autoComplete="off"
              />
            </label>
            <div className="inline-actions">
              <button type="button" className="btn btn-small" onClick={applyToken}>
                Apply token
              </button>
              {admin.error ? (
                <span className="probe-note is-bad">
                  {admin.error.toLowerCase().includes("admin token") ? "token refused" : admin.error}
                </span>
              ) : state ? (
                <span className="probe-note is-ok">levers unlocked</span>
              ) : null}
            </div>
            {state?.flags.default_ledger_key ? (
              <p className="inline-warning">
                You are sealing the ledger with the development key. Set{" "}
                <code>LEDGER_KEY</code> before anyone else can see this deployment.
              </p>
            ) : null}
          </Panel>

          <Panel kicker="Lever 01" title="Simulated squall" className="lever-panel">
            <p className="panel-lede">
              Fail the next N simulated provider attempts. Use it to watch retries, breaker bookkeeping
              and the fallback rail without touching a real provider.
            </p>
            <div className="squall-board">
              <Stamp tone={state?.levers.squall.armed ? "signal" : "ink"}>
                {state?.levers.squall.armed ? `ARMED · ${state.levers.squall.armed}` : "CLEAR"}
              </Stamp>
              <span className="mono-meta">{state?.levers.squall.shape ?? "simulated provider failures"}</span>
            </div>
            <div className="lever-row">
              <label className="field field-compact">
                <span>Failures</span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={fails}
                  onChange={(event) => setFails(Math.max(1, Math.min(10, Number(event.target.value))))}
                />
              </label>
              <button type="button" className="btn btn-small" onClick={armSquall} disabled={busy === "squall"}>
                {busy === "squall" ? "arming…" : "Arm squall"}
              </button>
              <button
                type="button"
                className="btn btn-small"
                onClick={disarmSquall}
                disabled={busy === "squall" || !state?.levers.squall.armed}
              >
                Disarm
              </button>
            </div>
          </Panel>

          <Panel kicker="Lever 02" title="Response cache" className="lever-panel">
            <div className="lever-stats">
              <KeyValue label="Entries">{state?.levers.cache.entries ?? "—"}</KeyValue>
              <KeyValue label="Hits">{state?.levers.cache.hits ?? "—"}</KeyValue>
              <KeyValue label="Misses">{state?.levers.cache.misses ?? "—"}</KeyValue>
              <KeyValue label="TTL">{state ? `${Math.round(state.levers.cache.ttl_s / 60)} min` : "—"}</KeyValue>
            </div>
            <p className="panel-note">{state?.levers.cache.note ?? "Exact-match cache across tiers and providers."}</p>
            <button
              type="button"
              className="btn btn-small"
              onClick={purgeCache}
              disabled={busy === "cache"}
            >
              {busy === "cache" ? "purging…" : "Purge cache"}
            </button>
          </Panel>

          <Panel kicker="Lever 03" title="Breakers" className="lever-panel">
            {state ? (
              <ul className="breaker-list">
                {Object.entries(state.levers.breakers).map(([name, health]) => (
                  <li key={name}>
                    <span className={`breaker-lamp breaker-${health.breaker.state}`} />
                    <div>
                      <strong>{name}</strong>
                      <small>
                        {health.breaker.state} · {health.breaker.failures_in_window}/
                        {health.breaker.threshold} failures
                        {health.breaker.cooldown_left_s
                          ? ` · ${Math.ceil(health.breaker.cooldown_left_s)}s cooldown`
                          : ""}
                      </small>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="panel-note">Unlock the levers to read breaker state.</p>
            )}
            <button
              type="button"
              className="btn btn-small"
              onClick={resetBreakers}
              disabled={busy === "breaker"}
            >
              {busy === "breaker" ? "resetting…" : "Reset all breakers"}
            </button>
          </Panel>

          <Panel kicker="Guardrails" title="Today" className="lever-panel">
            {state ? (
              <>
                <BudgetGauge
                  spent={state.levers.budget.spent}
                  limit={state.levers.budget.limit}
                  remaining={state.levers.budget.remaining}
                />
                <div className="lever-stats">
                  <KeyValue label="Rate limit">{state.flags.rate_limit_rpm} rpm</KeyValue>
                  <KeyValue label="Window">{state.levers.limiter.keys_in_window} keys</KeyValue>
                  <KeyValue label="Store prompts">{state.flags.store_prompts ? "yes" : "no"}</KeyValue>
                  <KeyValue label="Carbon">{state.flags.carbon_intensity_g_per_kwh} g/kWh</KeyValue>
                  <KeyValue label="PUE">{state.flags.datacenter_pue.toFixed(2)}</KeyValue>
                </div>
              </>
            ) : (
              <Skeleton lines={4} />
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

function BreakerCard({ breaker }: { breaker?: AdminState["levers"]["breakers"][string]["breaker"] }) {
  if (!breaker) {
    return (
      <div className="breaker-card">
        <span className="mono-meta">breaker state unavailable</span>
      </div>
    );
  }
  const state = breaker.state;
  return (
    <div className={`breaker-card breaker-${state}`}>
      <div className="breaker-head">
        <span className="breaker-lamp" />
        <strong>{state}</strong>
        <span className="mono-meta">
          {breaker.failures_in_window}/{breaker.threshold}
        </span>
      </div>
      <div className="breaker-steps" aria-hidden="true">
        {["closed", "half-open", "open"].map((step) => (
          <span key={step} className={step === state ? "is-on" : ""}>
            {step}
          </span>
        ))}
      </div>
      {breaker.cooldown_left_s > 0 ? (
        <p className="cell-sub">cooldown {Math.ceil(breaker.cooldown_left_s)}s</p>
      ) : null}
    </div>
  );
}
