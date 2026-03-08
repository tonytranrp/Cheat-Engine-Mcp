from __future__ import annotations

from typing import Any

from ..context import RuntimeModule, ToolContext
from ..registration import ParameterSpec, ToolSpec

SESSION_PARAMETER = ParameterSpec("session_id", str | None, None)
LIMIT_PARAMETER = ParameterSpec("limit", int, 256)
TIMEOUT_PARAMETER_NAME = "timeout_seconds"


def _resolve_timeout_seconds(kwargs: dict[str, Any], default: float) -> float:
    raw_timeout = kwargs.pop(TIMEOUT_PARAMETER_NAME, default)
    return float(raw_timeout)


def native_tool(ctx: ToolContext,
                *,
                name: str,
                description: str,
                bridge_tool: str,
                parameters: list[ParameterSpec] | tuple[ParameterSpec, ...] = (),
                payload_builder=None,
                timeout_seconds: float = 30.0) -> ToolSpec:
    default_timeout_seconds = timeout_seconds

    def handler(**kwargs):
        session_id = kwargs.pop("session_id", None)
        resolved_timeout_seconds = _resolve_timeout_seconds(kwargs, default_timeout_seconds)
        payload = payload_builder(**kwargs) if payload_builder is not None else dict(kwargs)
        payload = {key: value for key, value in payload.items() if value is not None}
        return ctx.native_call_safe(bridge_tool, payload=payload or None, session_id=session_id, timeout_seconds=resolved_timeout_seconds)

    return ToolSpec(
        name=name,
        description=description,
        parameters=tuple(parameters) + (SESSION_PARAMETER,),
        handler=handler,
    )


def lua_function_tool(ctx: ToolContext,
                      *,
                      name: str,
                      description: str,
                      function_name: str,
                      parameters: list[ParameterSpec] | tuple[ParameterSpec, ...],
                      arg_builder=None,
                      result_field: str = "value",
                      timeout_seconds: float = 30.0) -> ToolSpec:
    default_timeout_seconds = timeout_seconds

    def handler(**kwargs):
        session_id = kwargs.pop("session_id", None)
        resolved_timeout_seconds = _resolve_timeout_seconds(kwargs, default_timeout_seconds)
        args = arg_builder(**kwargs) if arg_builder is not None else [kwargs[param.name] for param in parameters]
        return ctx.call_lua_function(function_name, args=args, session_id=session_id, result_field=result_field, timeout_seconds=resolved_timeout_seconds)

    return ToolSpec(
        name=name,
        description=description,
        parameters=tuple(parameters) + (SESSION_PARAMETER,),
        handler=handler,
    )


def runtime_tool(ctx: ToolContext,
                 *,
                 name: str,
                 description: str,
                 runtime: RuntimeModule,
                 function_name: str,
                 parameters: list[ParameterSpec] | tuple[ParameterSpec, ...],
                 arg_builder=None,
                 timeout_seconds: float = 30.0) -> ToolSpec:
    default_timeout_seconds = timeout_seconds

    def handler(**kwargs):
        session_id = kwargs.pop("session_id", None)
        resolved_timeout_seconds = _resolve_timeout_seconds(kwargs, default_timeout_seconds)
        args = arg_builder(**kwargs) if arg_builder is not None else [kwargs[param.name] for param in parameters]
        return ctx.call_runtime_function(runtime, function_name, args=args, session_id=session_id, timeout_seconds=resolved_timeout_seconds)

    return ToolSpec(
        name=name,
        description=description,
        parameters=tuple(parameters) + (SESSION_PARAMETER,),
        handler=handler,
    )


def passthrough_tool(*, name: str, description: str, parameters: list[ParameterSpec] | tuple[ParameterSpec, ...], handler) -> ToolSpec:
    return ToolSpec(name=name, description=description, parameters=tuple(parameters), handler=handler)


def bool_payload(value: bool) -> bool:
    return bool(value)


def list_payload(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return list(values)
