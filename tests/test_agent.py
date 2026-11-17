from __future__ import annotations

from app.agent.runner import extract_action
from tests.conftest import build_yard, make_settings
from tests.test_pipeline import FakeProvider, FakeRegistry


async def test_agent_uses_the_calculator_then_answers(db):
    yard = await build_yard(db, make_settings())

    outcome = await yard.agent.run("What is 84 * 19?", source="test")

    assert outcome.error is None
    assert outcome.stopped_reason == "answered"
    assert outcome.answer == "1596"
    assert len(outcome.request_ids) == 2
    assert [step["type"] for step in outcome.trace] == ["tool", "answer"]
    tool_step = outcome.trace[0]
    assert tool_step["tool"] == "calculator"
    assert tool_step["ok"] is True
    assert tool_step["result"] == "1596"
    assert tool_step["route"]["tier"] in {"thrift", "prime"}
    assert outcome.trace[1]["answer"] == "1596"
    assert outcome.cost_usd > 0


async def test_agent_converts_units_with_the_convert_tool(db):
    yard = await build_yard(db, make_settings())

    outcome = await yard.agent.run("What is 12 kilometers in miles?", source="test")

    assert outcome.error is None
    assert outcome.trace[0]["tool"] == "convert"
    assert outcome.trace[0]["result"].startswith("7.45645")
    assert "7.45645" in outcome.answer
    assert "miles" in outcome.answer


async def test_agent_looks_up_a_stable_fact(db):
    yard = await build_yard(db, make_settings())

    outcome = await yard.agent.run("What is the capital of Canada?", source="test")

    assert outcome.error is None
    assert outcome.trace[0]["tool"] == "lookup"
    assert "Ottawa" in outcome.answer


async def test_agent_stops_when_the_step_budget_runs_out(db):
    yard = await build_yard(db, make_settings())

    outcome = await yard.agent.run("What is 84 * 19?", max_steps=1, source="test")

    assert outcome.stopped_reason == "max_steps"
    assert outcome.answer == ""
    assert "step budget of 1 exhausted" in (outcome.error or "")
    assert outcome.trace[-1]["type"] == "stop"
    assert outcome.trace[0]["type"] == "tool"


async def test_agent_accepts_a_non_json_provider_reply(db):
    chatty = FakeProvider("chatty-rail", text="Plain prose, no JSON here.")
    yard = await build_yard(db, make_settings(), registry=FakeRegistry([chatty]))

    outcome = await yard.agent.run("hello", source="test")

    assert outcome.stopped_reason == "non_json_answer"
    assert outcome.answer == "Plain prose, no JSON here."
    assert outcome.trace[-1]["note"].startswith("reply was not JSON")


async def test_agent_reports_gateway_failure_instead_of_crashing(db):
    dead = FakeProvider("dead-rail", fail_times=99)
    yard = await build_yard(
        db,
        make_settings(max_retries=0),
        registry=FakeRegistry([dead]),
    )

    outcome = await yard.agent.run("hello", source="test")

    assert outcome.stopped_reason == "gateway_error"
    assert outcome.error
    assert outcome.trace[0]["type"] == "gateway_error"
    assert outcome.request_ids == []


def test_extract_action_tolerates_prose_and_fences():
    action = extract_action('Sure: {"tool": "calculator", "args": {"expression": "2+2"}}')
    assert action == {"tool": "calculator", "args": {"expression": "2+2"}}

    fenced = '```json\n{"answer": "use {braces} carefully"}\n```'
    assert extract_action(fenced) == {"answer": "use {braces} carefully"}

    assert extract_action("no json at all") is None
    assert extract_action("") is None
    assert extract_action('{"unrelated": true}') is None
