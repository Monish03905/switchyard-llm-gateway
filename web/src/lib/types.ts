export type Tier = "thrift" | "prime";
export type Policy = "auto" | "thrift" | "prime";
export type RunPolicy = "thrift" | "prime" | "yardmaster";

export interface Reason {
  label: string;
  weight: number;
}

export interface Route {
  policy: string;
  tier: Tier;
  confidence: number;
  score: number;
  summary: string;
  reasons: Reason[];
  features: Record<string, unknown>;
  pinned_model: string | null;
}

export interface Attempt {
  provider: string;
  model: string;
  tier: string;
  status: string;
  error?: string;
  status_code?: number;
  retryable?: boolean;
  retry?: number;
  latency_ms?: number;
}

export interface Completion {
  request_id: string;
  text: string;
  policy: string;
  tier: Tier;
  provider: string;
  model: string;
  status: string;
  cache_hit: boolean;
  fallback_used: boolean;
  attempts: Attempt[];
  usage: { input_tokens: number; output_tokens: number; total_tokens: number };
  cost_usd: number;
  baseline_cost_usd: number;
  saved_usd: number;
  energy_wh: number;
  co2e_g: number;
  saved_co2e_g: number;
  latency_ms: number;
  created_at: string;
  route: Route;
  error: string | null;
}

export interface AgentStep {
  n: number;
  type: "tool" | "answer" | "stop" | "gateway_error";
  ok: boolean;
  tool?: string;
  args?: Record<string, unknown>;
  result?: string;
  answer?: string;
  error?: string;
  latency_ms?: number;
  request_id?: string;
  model?: string;
  tier?: string;
  route?: Route;
  note?: string;
}

export interface AgentOutcome {
  answer: string;
  steps: AgentStep[];
  steps_count: number;
  request_ids: string[];
  usage: { input_tokens: number; output_tokens: number; total_tokens: number };
  cost_usd: number;
  co2e_g: number;
  energy_wh: number;
  latency_ms: number;
  error: string | null;
  stopped_reason: string;
  model: string;
  provider: string;
  tier: string;
}

export interface DispatchResponse {
  mode: string;
  completion?: Completion;
  agent?: AgentOutcome;
}

export interface Budget {
  limit: number;
  spent: number;
  remaining: number;
  start_ms: number;
}

export interface BreakerSnapshot {
  state: "closed" | "open" | "half-open";
  failures_in_window: number;
  threshold: number;
  cooldown_left_s: number;
}

export interface ProbeResult {
  ok: boolean;
  provider: string;
  latency_ms?: number;
  sample?: string;
  error?: string;
  checked_ms?: number;
}

export interface ProviderHealth {
  breaker: BreakerSnapshot;
  last_probe: ProbeResult | null;
}

export interface ChainState {
  ok: boolean;
  entries: number;
  checked_ms: number;
  broken_at: string | null;
  broken_seq?: number;
  detail: string;
}

export interface CacheStats {
  entries: number;
  hits: number;
  misses: number;
  ttl_s: number;
  note: string;
}

export interface WindowStats {
  requests: number;
  ok: number;
  errors: number;
  blocked: number;
  success_rate: number;
  cache_hits: number;
  cache_hit_rate: number;
  fallbacks: number;
  tokens: number;
  cost_usd: number;
  baseline_cost_usd: number;
  saved_usd: number;
  saved_pct: number;
  co2e_g: number;
  saved_co2e_g: number;
  latency_avg_ms: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
}

export interface TimelinePoint {
  t: number;
  label: string;
  requests: number;
  cost_usd: number;
}

export interface ProviderModel {
  provider: string;
  model: string;
  tier: Tier;
  name: string;
  vendor: string;
  input_per_m: number;
  output_per_m: number;
  energy_kwh_per_1k: number;
  context: number;
  note: string;
}

export interface ProviderInfo {
  name: string;
  kind: string;
  configured?: boolean;
  simulated?: boolean;
  models?: Record<string, string>;
}

export interface RegistryInfo {
  mode: "live" | "simulated";
  simulated: boolean;
  note: string;
  primary: string;
  secondary: string | null;
  providers: ProviderInfo[];
  catalog: ProviderModel[];
}

export interface RequestSummary {
  id: string;
  created_at: string;
  created_ms: number;
  source: string;
  policy: string;
  tier: Tier;
  provider: string;
  model: string;
  status: string;
  cache_hit: boolean;
  fallback_used: boolean;
  attempts: number;
  tokens: number;
  cost_usd: number;
  saved_usd: number;
  co2e_g: number;
  saved_co2e_g: number;
  latency_ms: number;
  route_confidence: number;
  route_reason: string;
  prompt_preview: string;
  response_preview: string;
  error: string | null;
  batch_id: string | null;
  run_id: string | null;
  task_id: string | null;
}

export interface RequestDetail extends RequestSummary {
  requested_model: string;
  input_tokens: number;
  output_tokens: number;
  baseline_cost_usd: number;
  energy_wh: number;
  baseline_energy_wh: number;
  baseline_co2e_g: number;
  features: {
    contributions?: Reason[];
    threshold?: number;
    chars?: number;
    approx_tokens?: number;
    words?: number;
    numbers?: number;
    [key: string]: unknown;
  };
  attempts_detail: Attempt[];
  prompt_hash: string;
  prompt_text: string | null;
  response_text: string | null;
  prev_hash: string;
  entry_hash: string;
  seq: number;
  client: string;
}

export interface EvalRun {
  id: string;
  batch_id: string;
  policy: RunPolicy;
  mode: string;
  provider: string;
  model: string;
  status: string;
  tasks_total: number;
  tasks_done: number;
  passed: number;
  pass_rate: number;
  avg_score: number;
  tool_rate: number;
  total_cost_usd: number;
  total_co2e_g: number;
  total_energy_wh: number;
  total_tokens: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  avg_steps: number;
  started_ms: number;
  completed_ms: number | null;
  error: string | null;
  progress: number;
}

export interface Comparison {
  yardmaster_vs_prime?: {
    cost_saved_pct: number;
    pass_delta_pts: number;
    tool_delta_pts: number;
    co2_saved_pct: number;
    latency_delta_ms: number;
  };
  thrift_vs_prime?: { cost_saved_pct: number; pass_delta_pts: number };
  yardmaster_vs_thrift?: { pass_delta_pts: number; cost_delta_pct: number };
}

export interface EvalBatch {
  id: string;
  created_at: string;
  created_ms: number;
  completed_ms: number | null;
  label: string;
  mode: string;
  status: string;
  policies: string[];
  tasks_total: number;
  tasks_done: number;
  progress: number;
  error: string | null;
  runs?: EvalRun[];
  comparison?: Comparison;
}

export interface EvalResult {
  id: number;
  run_id: string;
  task_id: string;
  category: string;
  difficulty: number;
  passed: boolean;
  answer_score: number;
  tool_score: number;
  step_score: number;
  total_score: number;
  answer: string;
  expected: string;
  steps: AgentStep[];
  request_ids: string[];
  cost_usd: number;
  latency_ms: number;
  steps_count: number;
  error: string | null;
  policy: RunPolicy | null;
}

export interface BatchResults {
  batch: EvalBatch;
  runs: EvalRun[];
  results: EvalResult[];
  total: number;
}

export interface EvalTask {
  id: string;
  category: string;
  difficulty: number;
  prompt: string;
  expected: string;
  answer_type: string;
  required_tools: string[];
  strict_tools: boolean;
  max_steps: number;
}

export interface EvalTaskDetail extends EvalTask {
  note: string;
  route: Route;
}

export interface TaskBoard {
  tasks: EvalTask[];
  categories: string[];
  policies: string[];
  policy_titles: Record<string, string>;
  total: number;
}

export interface RouteMapTask {
  task_id: string;
  category: string;
  difficulty: number;
  prompt: string;
  tier: Tier;
  score: number;
  threshold: number;
  confidence: number;
  summary: string;
  reasons: Reason[];
}

export interface RouteMap {
  policy: string;
  threshold: number;
  counts: { thrift: number; prime: number };
  tasks: RouteMapTask[];
  note: string;
}

export interface BatchList {
  items: EvalBatch[];
  active_batch: string | null;
  running: boolean;
  policies: string[];
  policy_titles: Record<string, string>;
}

export interface Guardrails {
  budget: Budget;
  cache: CacheStats;
  breakers: Record<string, ProviderHealth>;
  squall: { armed: number; armed_at: number | null; shape: string };
  limiter: { rpm: number; keys_in_window: number };
  chain: ChainState;
}

export interface Overview {
  meta: {
    generated_ms: number;
    window_hours: number;
    mode: string;
    simulated: boolean;
    mode_note: string;
    version: string;
    environment: string;
    uptime_s: number;
    privacy: { store_prompts: boolean; default_ledger_key: boolean };
    auth: { gateway_key_required: boolean; admin_token_required: boolean };
    rate_limit_rpm: number;
  };
  stats: WindowStats;
  lifetime: {
    requests: number;
    cost_usd: number;
    saved_usd: number;
    saved_co2e_g: number;
    tokens: number;
    first_ms: number | null;
  };
  timeline: { bins: number; points: TimelinePoint[] };
  route_mix: { thrift?: number; prime?: number; cache?: number; total: number };
  source_mix: { source: string; count: number }[];
  guardrails: Guardrails;
  providers: RegistryInfo;
  recent: RequestSummary[];
  last_batch: EvalBatch | null;
}

export interface RequestPage {
  items: RequestSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminState {
  mode: string;
  simulated: boolean;
  version: string;
  levers: {
    cache: CacheStats;
    squall: { armed: number; armed_at: number | null; shape: string };
    limiter: { rpm: number; keys_in_window: number };
    budget: Budget;
    breakers: Record<string, ProviderHealth>;
    chain: ChainState;
  };
  flags: {
    store_prompts: boolean;
    default_ledger_key: boolean;
    gateway_key_required: boolean;
    admin_token_required: boolean;
    daily_budget_usd: number;
    rate_limit_rpm: number;
    carbon_intensity_g_per_kwh: number;
    datacenter_pue: number;
  };
  batch: {
    active_batch: string | null;
    jobs: string[];
    latest: EvalBatch | null;
  };
}

export interface ProviderPage extends RegistryInfo {
  health: Record<string, ProviderHealth>;
  fallback_provider: string | null;
  chaos: { armed: number; armed_at: number | null; shape: string };
}

export interface Health {
  status: string;
  version: string;
  environment: string;
  mode: string;
  simulated: boolean;
  uptime_s: number;
  checks: Record<string, string>;
}
