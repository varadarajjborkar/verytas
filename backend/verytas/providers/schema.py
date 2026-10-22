from __future__ import annotations

import copy
import json
import re
from typing import Any

from pydantic import BaseModel


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema reshaped for structured outputs: refs inlined,
    every object closed (additionalProperties false) with all fields required."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]]))
            node = {k: walk(v) for k, v in node.items() if k not in ("title", "default")}
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            return node
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json_object(text: str) -> str:
    """Pull the first top-level JSON object out of a model reply.

    Open models sometimes wrap JSON in fences or a sentence of preamble even
    when told not to. Brace matching respects strings, so a '}' inside a quoted
    value doesn't end the object early.
    """
    text = _FENCE.sub("", text.strip())
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in reply")
    depth, in_str, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                json.loads(candidate)  # raise early on malformed JSON
                return candidate
    raise ValueError("unterminated JSON object in reply")
