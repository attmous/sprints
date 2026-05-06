"""Actor prompt rendering."""

from __future__ import annotations

import json
import re
from typing import Any

from sprints.core.contracts import ActorPolicy


def build_actor_prompt(*, actor_policy: ActorPolicy, variables: dict[str, Any]) -> str:
    return render_prompt_template(
        prompt_template=actor_policy.body,
        variables=variables,
    )


def render_prompt_template(
    *,
    prompt_template: str,
    variables: dict[str, Any],
    default_template: str = "",
) -> str:
    template = str(prompt_template or "").strip()
    if not template:
        template = default_template
    if "{%" in template or "%}" in template:
        raise RuntimeError("template_parse_error: control blocks are not supported")
    if template.count("{{") != template.count("}}"):
        raise RuntimeError("template_parse_error: unbalanced template delimiters")

    def replace(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        if "|" in expr:
            raise RuntimeError(f"template_render_error: unsupported filter in {expr!r}")
        value = _resolve_variable(expr, variables)
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return str(value)

    rendered = re.sub(r"{{\s*([^{}]+?)\s*}}", replace, template)
    return rendered.strip() + "\n"


def _resolve_variable(expr: str, variables: dict[str, Any]) -> Any:
    parts = expr.split(".")
    value: Any = variables
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            raise RuntimeError(f"template_render_error: unknown variable {expr!r}")
        value = value[part]
    return value
