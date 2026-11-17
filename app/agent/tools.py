from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass


class ToolError(Exception):
    pass


TOOL_SPECS = [
    {
        "name": "calculator",
        "summary": 'Evaluate arithmetic safely. Args: {"expression": "(42 + 57) * 3"}',
    },
    {
        "name": "convert",
        "summary": (
            'Convert a measurement. Args: {"value": 12, "from_unit": "km", '
            '"to_unit": "m"} (length, mass, volume, time, speed, temperature)'
        ),
    },
    {
        "name": "lookup",
        "summary": 'Look up a stable reference fact. Args: {"query": "capital of Australia"}',
    },
]

TOOL_NAMES = [spec["name"] for spec in TOOL_SPECS]

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

_FUNCS = {
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "round": round,
    "ceil": math.ceil,
    "floor": math.floor,
}

_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def format_number(value: float) -> str:
    if math.isnan(value) or math.isinf(value):
        raise ToolError("result is not a finite number")
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6g}"


def calculate_expression(expression: str) -> str:
    expression = (expression or "").strip().rstrip("?")
    if not expression:
        raise ToolError("empty expression")
    if len(expression) > 200:
        raise ToolError("expression is too long (200 characters max)")
    if "__" in expression or ";" in expression:
        raise ToolError("that expression is not allowed")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError(f"could not parse the expression: {exc.msg}") from exc

    try:
        value = _eval_node(tree.body)
    except ZeroDivisionError as exc:
        raise ToolError("division by zero") from exc
    except (ValueError, OverflowError) as exc:
        raise ToolError(f"the calculator refused that expression: {exc}") from exc
    return format_number(float(value))


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ToolError("only numbers are allowed")
        if abs(node.value) > 1e15:
            raise ToolError("that number is too large")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ToolError("that exponent is too large")
        result = _BIN_OPS[type(node.op)](left, right)
        if isinstance(result, complex):
            raise ToolError("complex numbers are not supported")
        return result
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id not in _FUNCS:
            raise ToolError(f"function '{node.func.id}' is not on the approved list")
        if node.keywords:
            raise ToolError("keyword arguments are not supported")
        args = [_eval_node(arg) for arg in node.args]
        return _FUNCS[node.func.id](*args)
    raise ToolError("only arithmetic expressions are allowed")


_UNIT_ALIASES = {
    # length
    "m": ("length", 1.0),
    "meter": ("length", 1.0),
    "meters": ("length", 1.0),
    "metre": ("length", 1.0),
    "metres": ("length", 1.0),
    "km": ("length", 1000.0),
    "kilometer": ("length", 1000.0),
    "kilometers": ("length", 1000.0),
    "kilometre": ("length", 1000.0),
    "kilometres": ("length", 1000.0),
    "cm": ("length", 0.01),
    "centimeter": ("length", 0.01),
    "centimeters": ("length", 0.01),
    "mm": ("length", 0.001),
    "millimeter": ("length", 0.001),
    "millimeters": ("length", 0.001),
    "mi": ("length", 1609.344),
    "mile": ("length", 1609.344),
    "miles": ("length", 1609.344),
    "ft": ("length", 0.3048),
    "foot": ("length", 0.3048),
    "feet": ("length", 0.3048),
    "in": ("length", 0.0254),
    "inch": ("length", 0.0254),
    "inches": ("length", 0.0254),
    "yd": ("length", 0.9144),
    "yard": ("length", 0.9144),
    "yards": ("length", 0.9144),
    # mass
    "kg": ("mass", 1.0),
    "kilogram": ("mass", 1.0),
    "kilograms": ("mass", 1.0),
    "g": ("mass", 0.001),
    "gram": ("mass", 0.001),
    "grams": ("mass", 0.001),
    "mg": ("mass", 1e-6),
    "milligram": ("mass", 1e-6),
    "milligrams": ("mass", 1e-6),
    "lb": ("mass", 0.45359237),
    "lbs": ("mass", 0.45359237),
    "pound": ("mass", 0.45359237),
    "pounds": ("mass", 0.45359237),
    "oz": ("mass", 0.028349523125),
    "ounce": ("mass", 0.028349523125),
    "ounces": ("mass", 0.028349523125),
    "tonne": ("mass", 1000.0),
    "tonnes": ("mass", 1000.0),
    # volume
    "l": ("volume", 1.0),
    "liter": ("volume", 1.0),
    "liters": ("volume", 1.0),
    "litre": ("volume", 1.0),
    "litres": ("volume", 1.0),
    "ml": ("volume", 0.001),
    "milliliter": ("volume", 0.001),
    "milliliters": ("volume", 0.001),
    "m3": ("volume", 1000.0),
    "gallon": ("volume", 3.785411784),
    "gallons": ("volume", 3.785411784),
    "gal": ("volume", 3.785411784),
    "quart": ("volume", 0.946352946),
    "quarts": ("volume", 0.946352946),
    # time
    "s": ("time", 1.0),
    "sec": ("time", 1.0),
    "second": ("time", 1.0),
    "seconds": ("time", 1.0),
    "min": ("time", 60.0),
    "minute": ("time", 60.0),
    "minutes": ("time", 60.0),
    "h": ("time", 3600.0),
    "hr": ("time", 3600.0),
    "hour": ("time", 3600.0),
    "hours": ("time", 3600.0),
    "day": ("time", 86400.0),
    "days": ("time", 86400.0),
    "week": ("time", 604800.0),
    "weeks": ("time", 604800.0),
    # speed
    "m/s": ("speed", 1.0),
    "meter per second": ("speed", 1.0),
    "meters per second": ("speed", 1.0),
    "km/h": ("speed", 0.2777777778),
    "kilometer per hour": ("speed", 0.2777777778),
    "kilometers per hour": ("speed", 0.2777777778),
    "kph": ("speed", 0.2777777778),
    "mph": ("speed", 0.44704),
    "mile per hour": ("speed", 0.44704),
    "miles per hour": ("speed", 0.44704),
    "knot": ("speed", 0.5144444444),
    "knots": ("speed", 0.5144444444),
}

_TEMPERATURE_UNITS = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}


def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ToolError("value must be a number")
    source = str(from_unit).strip().lower().strip(".")
    target = str(to_unit).strip().lower().strip(".")
    source = re.sub(r"\s+", " ", source)
    target = re.sub(r"\s+", " ", target)

    if source in _TEMPERATURE_UNITS and target in _TEMPERATURE_UNITS:
        result = _convert_temperature(float(value), source, target)
        return {
            "value": result,
            "formatted": format_number(result),
            "from": source,
            "to": target,
            "category": "temperature",
        }

    if source not in _UNIT_ALIASES or target not in _UNIT_ALIASES:
        raise ToolError(f"unknown unit: {source if source not in _UNIT_ALIASES else target}")
    source_category, source_factor = _UNIT_ALIASES[source]
    target_category, target_factor = _UNIT_ALIASES[target]
    if source_category != target_category:
        raise ToolError(f"cannot convert {source_category} to {target_category}")
    result = float(value) * source_factor / target_factor
    return {
        "value": result,
        "formatted": format_number(result),
        "from": source,
        "to": target,
        "category": source_category,
    }


def _convert_temperature(value: float, source: str, target: str) -> float:
    if source == target:
        return value
    if source in {"c", "celsius"}:
        kelvin = value + 273.15
    elif source in {"f", "fahrenheit"}:
        kelvin = (value - 32) * 5 / 9 + 273.15
    else:
        kelvin = value
    if target in {"c", "celsius"}:
        return kelvin - 273.15
    if target in {"f", "fahrenheit"}:
        return (kelvin - 273.15) * 9 / 5 + 32
    return kelvin


@dataclass(frozen=True)
class Fact:
    keys: tuple[str, ...]
    answer: str


# Stable facts only: no prices, no "current" officeholders, nothing that expires.
FACTS: tuple[Fact, ...] = (
    Fact(("capital", "australia"), "Canberra is the capital of Australia."),
    Fact(("capital", "canada"), "Ottawa is the capital of Canada."),
    Fact(("capital", "japan"), "Tokyo is the capital of Japan."),
    Fact(("capital", "france", "paris"), "Paris is the capital of France."),
    Fact(("capital", "india"), "New Delhi is the capital of India."),
    Fact(("chemical", "symbol", "fe", "iron"), "Fe is the chemical symbol for iron."),
    Fact(("chemical", "symbol", "au", "gold"), "Au is the chemical symbol for gold."),
    Fact(("chemical", "symbol", "na", "sodium"), "Na is the chemical symbol for sodium."),
    Fact(("chemical", "symbol", "o", "oxygen"), "O is the chemical symbol for oxygen."),
    Fact(("chemical", "symbol", "h2o", "water"), "H2O is the chemical formula for water."),
    Fact(
        ("speed", "light", "vacuum"),
        "The speed of light in a vacuum is exactly 299,792,458 meters per second.",
    ),
    Fact(("author", "tempest", "shakespeare"), "William Shakespeare wrote The Tempest."),
    Fact(("author", "1984", "orwell"), "George Orwell wrote the novel 1984."),
    Fact(
        ("author", "great", "gatsby", "fitzgerald"),
        "F. Scott Fitzgerald wrote The Great Gatsby.",
    ),
    Fact(
        ("boiling", "point", "water"),
        "Water boils at 100 degrees Celsius at standard sea-level pressure.",
    ),
    Fact(
        ("freezing", "point", "water"),
        "Water freezes at 0 degrees Celsius at standard pressure.",
    ),
    Fact(("http", "404"), "HTTP 404 means Not Found."),
    Fact(("http", "500"), "HTTP 500 means Internal Server Error."),
    Fact(("http", "201"), "HTTP 201 means Created."),
    Fact(("http", "401"), "HTTP 401 means Unauthorized."),
    Fact(("http", "403"), "HTTP 403 means Forbidden."),
    Fact(("default", "port", "https"), "The default port for HTTPS is 443."),
    Fact(("default", "port", "http"), "The default port for HTTP is 80."),
    Fact(("binary", "1010"), "Binary 1010 equals decimal 10."),
    Fact(("hex", "ff"), "Hexadecimal FF equals decimal 255."),
    Fact(("square", "root", "144"), "The square root of 144 is 12."),
    Fact(("earth", "gravity"), "Earth's standard gravity is about 9.81 meters per second squared."),
    Fact(("speed", "sound", "air"), "The speed of sound in dry air at 20 C is about 343 m/s."),
    Fact(("mile", "meters"), "One mile is 1,609.344 meters."),
    Fact(("kilogram", "pounds", "lb"), "One kilogram is about 2.20462 pounds."),
    Fact(("human", "body", "temperature"), "Normal human body temperature is about 37 C."),
    Fact(("continents"), "There are seven commonly recognized continents."),
    Fact(("leap", "year", "days"), "A leap year has 366 days."),
    Fact(("hour", "seconds"), "There are 3,600 seconds in an hour."),
    Fact(
        ("munich", "conference", "1938"), "The 1938 Munich Agreement is a well-known failed appeasement pact."
    ),
    Fact(("japan", "currency"), "Japan's currency is the yen."),
    Fact(("eu", "currency", "euro"), "The euro is the official currency of the eurozone."),
    Fact(("united", "nations", "founded"), "The United Nations was founded in 1945."),
    Fact(
        ("first", "moon", "landing", "armstrong"),
        "Neil Armstrong was the first person to walk on the Moon, in 1969.",
    ),
    Fact(("telephone", "inventor"), "Alexander Graham Bell is credited with inventing the telephone."),
    Fact(("mona", "lisa", "painter"), "Leonardo da Vinci painted the Mona Lisa."),
    Fact(("largest", "planet"), "Jupiter is the largest planet in the Solar System."),
    Fact(("largest", "ocean"), "The Pacific Ocean is the largest ocean on Earth."),
    Fact(("highest", "mountain", "everest"), "Mount Everest is Earth's highest mountain above sea level."),
    Fact(("python", "creator", "guido"), "Guido van Rossum created the Python language."),
    Fact(("javascript", "creator", "eich"), "Brendan Eich created JavaScript."),
)

_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "is",
    "what",
    "which",
    "who",
    "in",
    "to",
    "for",
    "and",
    "does",
    "do",
    "was",
    "are",
    "how",
    "many",
    "tell",
    "me",
    "about",
    "please",
    "mean",
    "means",
}


def lookup_fact(query: str) -> dict | None:
    tokens = _tokens(query)
    if not tokens:
        return None
    best: tuple[int, Fact] | None = None
    for fact in FACTS:
        key_tokens = set()
        for key in fact.keys:
            key_tokens.update(_tokens(key))
        overlap = len(tokens & key_tokens)
        exact_bonus = 2 if " ".join(fact.keys) in (query or "").lower() else 0
        score = overlap + exact_bonus
        if overlap and (best is None or score > best[0]):
            best = (score, fact)
    if best is None:
        return None
    return {"answer": best[1].answer, "score": best[0]}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {word for word in words if word not in _STOPWORDS and len(word) > 1}


def run_tool(name: str, args: dict) -> str:
    if not isinstance(args, dict):
        raise ToolError("tool arguments must be a JSON object")
    if name == "calculator":
        return calculate_expression(str(args.get("expression", "")))
    if name == "convert":
        result = convert_units(
            args.get("value"), str(args.get("from_unit", "")), str(args.get("to_unit", ""))
        )
        return f"{result['formatted']} {result['to']}"
    if name == "lookup":
        result = lookup_fact(str(args.get("query", "")))
        if result is None:
            raise ToolError("no stable reference entry matched that query")
        return result["answer"]
    raise ToolError(f"unknown tool '{name}'")


def parse_conversion_prompt(prompt: str) -> dict | None:
    """Pull a conversion out of natural language, for the simulator and quick examples."""
    text = prompt.strip()
    direct = re.search(
        r"(-?\d+(?:\.\d+)?)\s*([a-zA-Z/ ]+?)\s+(?:to|into|as)\s+([a-zA-Z/ ]+)",
        text,
        re.IGNORECASE,
    )
    if direct:
        return {
            "value": float(direct.group(1)),
            "from_unit": _clean_unit(direct.group(2)),
            "to_unit": _clean_unit(direct.group(3)),
        }
    natural = re.search(
        r"(-?\d+(?:\.\d+)?)\s*([a-zA-Z/ ]+?)\s+in\s+([a-zA-Z/ ]+?)"
        r"(?:\s+(?:is|equals?|approximately|approx)\b.*)?[.?!]?$",
        text,
        re.IGNORECASE,
    )
    if natural:
        return {
            "value": float(natural.group(1)),
            "from_unit": _clean_unit(natural.group(2)),
            "to_unit": _clean_unit(natural.group(3)),
        }
    inverse = re.search(
        r"how many\s+([a-zA-Z/ ]+?)\s+(?:are\s+)?in\s+(-?\d+(?:\.\d+)?)\s*([a-zA-Z/ ]+)",
        text,
        re.IGNORECASE,
    )
    if inverse:
        return {
            "value": float(inverse.group(2)),
            "from_unit": _clean_unit(inverse.group(3)),
            "to_unit": _clean_unit(inverse.group(1)),
        }
    return None


def _clean_unit(raw: str) -> str:
    cleaned = raw.strip().lower().strip(".,?!")
    cleaned = re.sub(r"\b(degrees?|degree)\b", "", cleaned).strip()
    cleaned = re.sub(r"\b(are|is|the|a|an)\b", "", cleaned).strip()
    return cleaned
