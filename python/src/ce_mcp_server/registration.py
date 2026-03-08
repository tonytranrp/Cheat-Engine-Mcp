from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from .errors import error_payload, normalize_tool_result


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    name: str
    annotation: Any
    default: Any = inspect.Signature.empty


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: tuple[ParameterSpec, ...] = field(default_factory=tuple)
    return_annotation: Any = dict[str, Any]
    handler: Callable[..., dict[str, Any]] | None = None


def register_specs(server: FastMCP, specs: list[ToolSpec] | tuple[ToolSpec, ...]) -> None:
    for spec in specs:
        register_tool(server, spec)


def register_tool(server: FastMCP, spec: ToolSpec) -> None:
    if spec.handler is None:
        raise ValueError(f"tool '{spec.name}' is missing a handler")

    def impl(**kwargs):
        try:
            return normalize_tool_result(spec.name, spec.handler(**kwargs))
        except Exception as exc:  # pragma: no cover - defensive boundary for MCP tools
            return error_payload(spec.name, exc)

    impl.__name__ = spec.name.replace('.', '_').replace('-', '_')
    impl.__doc__ = spec.description
    impl.__annotations__ = {parameter.name: parameter.annotation for parameter in spec.parameters}
    impl.__annotations__["return"] = spec.return_annotation
    impl.__signature__ = inspect.Signature(
        parameters=[
            inspect.Parameter(
                parameter.name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=parameter.default,
                annotation=parameter.annotation,
            )
            if parameter.default is not inspect.Signature.empty
            else inspect.Parameter(
                parameter.name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=parameter.annotation,
            )
            for parameter in spec.parameters
        ]
    )
    server.tool(name=spec.name, description=spec.description)(impl)
