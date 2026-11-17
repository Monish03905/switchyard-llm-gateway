from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GatewayRequest(Base):
    __tablename__ = "gateway_requests"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    created_at: Mapped[str] = mapped_column(String(32))
    created_ms: Mapped[int] = mapped_column(BigInteger, index=True)

    source: Mapped[str] = mapped_column(String(16), default="api", index=True)
    policy: Mapped[str] = mapped_column(String(16), default="auto")
    requested_model: Mapped[str] = mapped_column(String(64), default="auto")
    tier: Mapped[str] = mapped_column(String(16), default="thrift")
    provider: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(16), default="ok", index=True)

    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    baseline_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    saved_usd: Mapped[float] = mapped_column(Float, default=0.0)
    energy_wh: Mapped[float] = mapped_column(Float, default=0.0)
    baseline_energy_wh: Mapped[float] = mapped_column(Float, default=0.0)
    co2e_g: Mapped[float] = mapped_column(Float, default=0.0)
    baseline_co2e_g: Mapped[float] = mapped_column(Float, default=0.0)
    saved_co2e_g: Mapped[float] = mapped_column(Float, default=0.0)

    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    route_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    route_reason: Mapped[str] = mapped_column(Text, default="")
    features_json: Mapped[str] = mapped_column(Text, default="{}")
    attempts_json: Mapped[str] = mapped_column(Text, default="[]")

    prompt_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    prompt_preview: Mapped[str] = mapped_column(Text, default="")
    prompt_text: Mapped[str] = mapped_column(Text, nullable=True)
    response_preview: Mapped[str] = mapped_column(Text, default="")
    response_text: Mapped[str] = mapped_column(Text, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    client: Mapped[str] = mapped_column(String(64), default="")

    batch_id: Mapped[str] = mapped_column(String(48), nullable=True, index=True)
    run_id: Mapped[str] = mapped_column(String(48), nullable=True, index=True)
    task_id: Mapped[str] = mapped_column(String(48), nullable=True, index=True)

    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    entry_hash: Mapped[str] = mapped_column(String(64), default="", index=True)

    __table_args__ = (
        Index("ix_requests_source_created", "source", "created_ms"),
        Index("ix_requests_batch_task", "batch_id", "task_id"),
    )


class EvalBatch(Base):
    __tablename__ = "eval_batches"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(32))
    created_ms: Mapped[int] = mapped_column(BigInteger, index=True)
    completed_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    mode: Mapped[str] = mapped_column(String(16), default="simulated")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    policies_json: Mapped[str] = mapped_column(Text, default="[]")
    tasks_total: Mapped[int] = mapped_column(Integer, default=0)
    tasks_done: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, nullable=True)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(48), index=True)
    policy: Mapped[str] = mapped_column(String(16), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="simulated")
    provider: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    tasks_total: Mapped[int] = mapped_column(Integer, default=0)
    tasks_done: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0)
    tool_rate: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_co2e_g: Mapped[float] = mapped_column(Float, default=0.0)
    total_energy_wh: Mapped[float] = mapped_column(Float, default=0.0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    p95_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    avg_steps: Mapped[float] = mapped_column(Float, default=0.0)
    started_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    completed_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(48), index=True)
    task_id: Mapped[str] = mapped_column(String(48))
    category: Mapped[str] = mapped_column(String(32))
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    answer_score: Mapped[float] = mapped_column(Float, default=0.0)
    tool_score: Mapped[float] = mapped_column(Float, default=0.0)
    step_score: Mapped[float] = mapped_column(Float, default=0.0)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    answer: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[str] = mapped_column(Text, default="")
    steps_json: Mapped[str] = mapped_column(Text, default="[]")
    request_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    steps_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    created_ms: Mapped[int] = mapped_column(BigInteger, index=True)
