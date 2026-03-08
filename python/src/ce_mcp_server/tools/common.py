from __future__ import annotations

from typing import Any

from ..context import RuntimeModule, ToolContext
from ..registration import ParameterSpec, ToolSpec

SESSION_PARAMETER = ParameterSpec("session_id", str | None, None)
LIMIT_PARAMETER = ParameterSpec("limit", int, 256)


def native_tool(ctx: ToolContext,
                *,
                name: str,
                description: str,
                bridge_tool: str,
                parameters: list[ParameterSpec] | tuple[ParameterSpec, ...] = (),
                payload_builder=None) -> ToolSpec:
    def handler(**kwargs):
        session_id = kwargs.pop("session_id", None)
        payload = payload_builder(**kwargs) if payload_builder is not None else dict(kwargs)
        payload = {key: value for key, value in payload.items() if value is not None}
        return ctx.native_call_safe(bridge_tool, payload=payload or None, session_id=session_id)

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
                      result_field: str = "value") -> ToolSpec:
    def handler(**kwargs):
        session_id = kwargs.pop("session_id", None)
        args = arg_builder(**kwargs) if arg_builder is not None else [kwargs[param.name] for param in parameters]
        return ctx.call_lua_function(function_name, args=args, session_id=session_id, result_field=result_field)

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
                 arg_builder=None) -> ToolSpec:
    def handler(**kwargs):
        session_id = kwargs.pop("session_id", None)
        args = arg_builder(**kwargs) if arg_builder is not None else [kwargs[param.name] for param in parameters]
        return ctx.call_runtime_function(runtime, function_name, args=args, session_id=session_id)

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
