from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32_000)


class ChatCompletionRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=40)
    model: str = Field(default="auto", max_length=80)
    temperature: float | None = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    cache: bool | None = None


class DispatchRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    policy: str = Field(default="auto", max_length=24)
    use_tools: bool = False
    max_steps: int = Field(default=4, ge=1, le=8)


class EvalBatchRequest(BaseModel):
    policies: list[str] = Field(
        default_factory=lambda: ["thrift", "prime", "yardmaster"], min_length=1, max_length=3
    )
    label: str = Field(default="", max_length=120)
    task_ids: list[str] | None = None


class SquallRequest(BaseModel):
    fails: int = Field(default=1, ge=1, le=10)
