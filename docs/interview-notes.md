# Field notes for the interview

This file is the "why" behind the repo — the parts that don't fit in a README and
that are worth saying out loud.

## The 60-second pitch

"Switchyard is an LLM gateway where routing is visible and auditable. One OpenAI-
compatible endpoint sends each request to a cheap or a strong model using a
weighted, explainable rule set, then prices the result against what the strong
model would have cost. Retries, cross-provider fallback, a circuit breaker, an
exact-match cache, and a daily budget guard keep it honest under failure. Every
receipt is chained with HMAC-SHA256 so cost claims can't be quietly edited. On a
36-task, 9-category agent exam, the router keeps 94.4% of the strong model's
100% pass rate while spending 25.2% less; the cheap model alone gets 41.7%. The
same exam runs in CI and fails the build if routing regresses."

## Resume bullets that are defensible

* Built an async FastAPI LLM gateway with one OpenAI-compatible endpoint,
  per-request cost/carbon accounting, retries with jittered backoff,
  cross-provider fallback, half-open circuit breaking, and an exact-match cache.
* Designed a deterministic, explainable router (weighted signals, 0.33 threshold,
  confidence from distance) and proved it with a paired 36-task × 3-policy eval:
  94.4% pass rate at 25.2% lower spend than always-strong, versus 41.7% for
  always-cheap.
* Preserved an HMAC-SHA256 hash-chained ledger of every request; added chain
  verification, CSV export, a React cockpit with three themes, Prometheus
  metrics, and a CI eval gate that blocks regressions without provider keys.
* Wrote 92 tests covering the pipeline, agent loop, OpenAI-compatibility layer,
  router, tools, scorers, cache/breaker, ledger, and HTTP surface; lint and
  format are enforced in CI.

## Why a rule router and not a classifier

Three reasons, in order:

1. **Explainability is the product.** The cockpit shows the three largest
   contributions and a confidence. "Why prime?" should not be "the model said so."
2. **Bootstrap cost.** A learned router needs labelled difficulty and a training
   loop. Hand weights plus a scored exam got a useful system on day one.
3. **Failure is asymmetric.** Routing up wastes money; routing down fails tasks.
   A conservative threshold with explicit negative signals (greetings, single
   lookups) is easier to reason about than a probability.

The honest next step is a learned scorer with the rule router as a guardrail and
the exam as the regression test. I would not remove the threshold until the
learned model beats it on the paired eval, not on a held-out accuracy number.

## Why the exam is paired

Comparing "router pass rate" to "cheap pass rate" across different runs is
meaningless: tasks and temperatures drift. The gauntlet runs the **same tasks,
same order, same mock/simulator** under thrift, prime, and router, then reports
deltas. That is why 94.4% vs 100% (−5.6 pts) and 25.2% saved is a defensible
statement, and why the CI gate checks all three arms rather than a single score.

36 tasks is small. It is enough to catch a broken router, not enough to claim a
general result. I say that before an interviewer does.

## Trade-offs I'd defend

| Decision | Cost | Why it's worth it |
|---|---|---|
| Exact-match cache | misses paraphrases | every hit is provably the same request; no false "free" answers |
| One worker | no horizontal scale | cache/breaker/limiter/chaos are in-process; the ledger chain stays simple |
| SQLite default | writer contention | zero-setup demo; Postgres is one env var |
| Rule router | manual weights | explainable, testable, no training data needed |
| HMAC chaining | key rotation invalidates history | cost claims become tamper-evident; rotation is documented, not silent |
| Simulator by default | numbers are a rehearsal | the project is runnable and testable before spending a cent; the UI says so everywhere |

## Three bugs worth telling

**Half-open breaker admitted everyone.** The breaker's `allow()` treated
`half-open` as "go", so every concurrent caller became a probe and a recovering
provider got stampeded. Fix: one probe per half-open window, held in a set, with
the rest waiting for the verdict.

**Ledger verification failed for its own error receipts.** The hash was computed
while tokens were `None`, but the database stored `0` defaults, so replaying the
payload produced a different digest. Fix: write zeros before hashing. The lesson:
a hash chain verifies *serialization*, not just values.

**Windows served `index.html` for unknown `/api` routes.** Starlette passed a
backslashed path to the SPA fallback, so the reserved-prefix check missed and a
404 became a 200 HTML page. Fix: normalise separators and leading slashes before
deciding whether a request is API or cockpit. Also added immutable caching for
hashed assets.

Bonus, from the test harness: httpx 0.28 cannot parse a bracketed `[::1]` in
`NO_PROXY`, which broke the mocked-provider tests until the proxy env was
neutralised. Real-world "works on my machine" energy.

## Likely questions

**Is the saving real?** The simulation is deterministic and the prices are an
editable sheet. In live mode the same pipeline calls Groq/OpenAI and records
actual usage from the provider response; the saving is then computed against the
strong model's list price. The simulator exists so CI can gate routing logic
without a bill, not to inflate a number.

**What happens when every provider fails?** The pipeline exhausts the candidate
list, records a receipt with `status=error`, returns 502 with the request id, and
the ledger still verifies. The cockpit shows the attempts and errors. No silent
success.

**What about prompt injection?** The agent has three allowlisted tools; the
calculator parses a restricted AST (no attribute access, no imports), and the
lookup table is static. Model output is treated as a proposed action, not
executable code. Tool arguments are validated per tool.

**How would you scale it?** Redis cache, Postgres advisory lock for ledger
appends, shared limiter/chaos state, background workers for eval batches, then
multiple replicas. I'd add tenant-scoped keys and budgets at the same time.

**How do you know the scorer is fair?** It combines numeric tolerance, keyword
coverage, a refusal/leak check, and a strict tools gate; tasks declare what they
require. It is still a heuristic — an LLM judge or human spot-check would be the
next layer. The point today is consistency across the three policies.

**Why save 25% instead of 80%?** Because routing down is gated by the exam. The
cheap model misses units, multi-step arithmetic, and safety framing; the router
sends exactly those uphill. An 80% saving with a 40-point pass-rate drop is not a
win. The threshold is the dial, and the eval is the brake.

## Five-minute demo script

1. Open `/` → point at the mode chip ("simulated") and the savings/carbon tiles.
2. `/dispatch` → send "What is 84 * 19?" with tools on. Show the trace: calculator
   call, answer, two receipts, route reasons.
3. Send "Design a retry policy for a payment webhook and explain the trade-offs
   step by step." Show the router choosing prime (0.58) and the two reasons that
   pushed it there.
4. `/switchboard` → arm Squall for 3 failures, resend the cheap question in
   `/dispatch`, show retry → fallback → success, then disarm.
5. `/ledger` → open a receipt drawer, show the attempt trail and cost breakdown,
   copy the receipt id, hit `/api/ledger/verify`, show `ok: true`.
6. `/gauntlet` → run all three policies (or open the last batch) and read the
   comparison: 41.7% / 94.4% / 100%, 25.2% saved, −5.6 pts.
7. Close on `docs/architecture.md` and the CI eval gate.

## What I'd build next

* Streaming responses (SSE) with usage reconciliation at stream end.
* Semantic cache behind a strict similarity threshold, with the same audit trail.
* A learned router with the rule set as a safety envelope, validated on the
  paired exam.
* Per-tenant keys, budgets, and rate limits; cost anomaly alerts.
* Postgres advisory locks + queue-backed eval batches for true multi-replica.
