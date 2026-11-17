from __future__ import annotations

import pytest

from app.agent.tools import (
    ToolError,
    calculate_expression,
    convert_units,
    lookup_fact,
    parse_conversion_prompt,
    run_tool,
)


def test_calculator_handles_each_eval_expression():
    assert calculate_expression("42 + 57 + 31") == "130"
    assert calculate_expression("(250 - 38) * 3 + 44") == "680"
    assert calculate_expression("480 - (480 * 3 / 8)") == "300"


def test_calculator_supports_approved_functions():
    assert calculate_expression("sqrt(144)") == "12"
    assert calculate_expression("log10(1000)") == "3"
    assert calculate_expression("abs(-7)") == "7"
    assert calculate_expression("round(2.567, 2)") == "2.57"
    assert calculate_expression("2 * pi").startswith("6.2831")


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "open('secrets.txt')",
        "1; 2",
        "x = 1",
        "2 ** 2000",
        "1 / 0",
        "1e16",
        "sqrt(-1)",
        "",
    ],
)
def test_calculator_refuses_dangerous_or_invalid_input(expression):
    with pytest.raises(ToolError):
        calculate_expression(expression)


def test_convert_length_mass_and_speed():
    miles = convert_units(12, "kilometers", "miles")
    assert miles["value"] == pytest.approx(7.4564543, abs=1e-6)
    assert miles["formatted"] == "7.45645"
    assert miles["category"] == "length"

    grams = convert_units(2.75, "kilograms", "grams")
    assert grams["value"] == pytest.approx(2750)
    assert grams["category"] == "mass"

    speed = convert_units(90, "kilometers per hour", "meters per second")
    assert speed["value"] == pytest.approx(25, abs=1e-6)


def test_convert_temperature():
    assert convert_units(98.6, "fahrenheit", "celsius")["value"] == pytest.approx(37)
    assert convert_units(37, "celsius", "fahrenheit")["value"] == pytest.approx(98.6)


def test_convert_rejects_cross_category_units():
    with pytest.raises(ToolError, match="cannot convert"):
        convert_units(1, "kilometers", "kilograms")
    with pytest.raises(ToolError, match="unknown unit"):
        convert_units(1, "furlongs", "meters")
    with pytest.raises(ToolError, match="value must be a number"):
        convert_units(True, "kg", "g")


def test_lookup_returns_stable_facts_only():
    assert lookup_fact("capital of Australia")["answer"].startswith("Canberra")
    assert lookup_fact("http 404")["answer"] == "HTTP 404 means Not Found."
    assert lookup_fact("speed of light in vacuum")["score"] >= 2
    assert lookup_fact("xyzzy plugh") is None


@pytest.mark.parametrize(
    ("prompt", "value", "source", "target"),
    [
        ("Convert 12 kilometers to meters.", 12.0, "kilometers", "meters"),
        ("How many grams are in 2.75 kilograms?", 2.75, "kilograms", "grams"),
        ("98.6 degrees Fahrenheit in Celsius", 98.6, "fahrenheit", "celsius"),
        ("12 km into miles", 12.0, "km", "miles"),
    ],
)
def test_parse_conversion_prompt(prompt, value, source, target):
    parsed = parse_conversion_prompt(prompt)
    assert parsed is not None
    assert parsed["value"] == pytest.approx(value)
    assert parsed["from_unit"] == source
    assert parsed["to_unit"] == target


def test_parse_conversion_prompt_declines_non_conversions():
    assert parse_conversion_prompt("What is the capital of Canada?") is None
    assert parse_conversion_prompt("") is None


def test_run_tool_routes_to_the_right_hand():
    assert run_tool("calculator", {"expression": "6 * 7"}) == "42"
    assert run_tool("convert", {"value": 12, "from_unit": "km", "to_unit": "miles"}) == "7.45645 miles"
    assert "Canberra" in run_tool("lookup", {"query": "capital of Australia"})

    with pytest.raises(ToolError, match="unknown tool"):
        run_tool("shell", {"command": "rm -rf /"})
    with pytest.raises(ToolError, match="JSON object"):
        run_tool("calculator", "2 + 2")
