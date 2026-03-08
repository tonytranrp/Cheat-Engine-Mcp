from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..bridge import BridgeError
from ..context import ToolContext
from ..errors import ToolUsageError
from ..registration import ParameterSpec, ToolSpec, register_specs
from ..runtime.process_runtime import PROCESS_RUNTIME
from .common import native_tool


def _parse_integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 0)
        except ValueError:
            return None
    return None


def _runtime_call_strict(ctx: ToolContext,
                         function_name: str,
                         *,
                         args: list[Any] | tuple[Any, ...] | None = None,
                         session_id: str,
                         timeout_seconds: float = 30.0) -> dict[str, Any]:
    result = ctx.call_runtime_function(
        PROCESS_RUNTIME,
        function_name,
        args=args,
        session_id=session_id,
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok") is not True:
        raise BridgeError(str(result.get("error", f"process runtime '{function_name}' failed")))
    return result


def _resolve_address_expression(ctx: ToolContext, session_id: str, value: int | str) -> tuple[int, str]:
    parsed = _parse_integer(value)
    if parsed is not None:
        return parsed, "integer"

    if not isinstance(value, str):
        raise ToolUsageError(
            "address must be an integer or Cheat Engine address expression",
            code="invalid_address_expression",
            hint="Pass an integer address or a CE expression such as game.exe+1234.",
            details={"received_type": type(value).__name__},
        )

    resolved = ctx.call_lua_function(
        "getAddressSafe",
        args=[value],
        session_id=session_id,
        result_field="address",
        timeout_seconds=30.0,
    )
    if resolved.get("ok") is not True:
        raise BridgeError(str(resolved.get("error", "address resolution failed")))

    parsed = _parse_integer(resolved.get("address"))
    if parsed is None:
        raise ToolUsageError(
            f"could not resolve address expression: {value}",
            code="address_resolution_failed",
            hint="The expression did not resolve to a concrete address in the attached process.",
            details={"expression": value},
        )
    return parsed, "ce_expression"


def _module_matches(entry: dict[str, Any], requested_name: str) -> bool:
    requested = requested_name.casefold()
    module_name = str(entry.get("module_name", ""))
    module_path = str(entry.get("module_path", ""))
    return (
        module_name.casefold() == requested or
        module_path.casefold() == requested or
        Path(module_path).name.casefold() == requested
    )


def _normalize_address_handler(ctx: ToolContext, *, address: int | str, session_id: str | None = None) -> dict[str, Any]:
    resolved_session = ctx.resolve_session_id(session_id)
    resolved_address, resolved_via = _resolve_address_expression(ctx, resolved_session, address)

    result: dict[str, Any] = {
        "session_id": resolved_session,
        "input": address,
        "address": resolved_address,
        "address_hex": hex(resolved_address),
        "resolved_via": resolved_via,
    }

    symbol = ctx.native_call_safe(
        "ce.resolve_symbol",
        payload={"address": resolved_address},
        session_id=resolved_session,
        timeout_seconds=30.0,
    )
    if symbol.get("ok") is True:
        result["symbol"] = symbol.get("symbol", "")
        result["symbol_resolved_via"] = symbol.get("resolved_via", "")

    return result


def _verify_target_handler(ctx: ToolContext, *, session_id: str | None = None) -> dict[str, Any]:
    resolved_session = ctx.resolve_session_id(session_id)
    attached = ctx.native_call_strict("ce.get_attached_process", session_id=resolved_session, timeout_seconds=30.0)
    native_tools = ctx.native_call_strict("ce.list_tools", session_id=resolved_session, timeout_seconds=30.0)

    result: dict[str, Any] = {
        "session_id": resolved_session,
        "ready": False,
        "attached": bool(attached.get("attached", False)),
        "process_id": int(attached.get("process_id", 0) or 0),
        "process_name": str(attached.get("process_name", "")),
        "image_path": str(attached.get("image_path", "")),
        "native_bridge_tool_count": len(native_tools.get("items", [])),
        "native_bridge_tools": list(native_tools.get("items", [])),
    }

    if not result["attached"] or result["process_id"] == 0:
        return result

    is64 = _runtime_call_strict(ctx, "target_is_64bit", args=[], session_id=resolved_session, timeout_seconds=30.0)
    modules = ctx.native_call_strict("ce.list_modules_full", session_id=resolved_session, timeout_seconds=30.0)
    result["is_64bit"] = bool(is64.get("is64", False))
    result["module_count"] = int(modules.get("total_count", len(modules.get("modules", []))))

    requested_names = [name for name in (result["process_name"], result["image_path"]) if name]
    main_module: dict[str, Any] | None = None
    for entry in modules.get("modules", []):
        if not isinstance(entry, dict):
            continue
        if any(_module_matches(entry, requested_name) for requested_name in requested_names):
            main_module = dict(entry)
            break
    if main_module is None and modules.get("modules"):
        first_entry = modules["modules"][0]
        if isinstance(first_entry, dict):
            main_module = dict(first_entry)
    if main_module is not None:
        result["main_module"] = main_module

    result["ready"] = True
    return result


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
        ToolSpec(
            name="ce.bridge_status",
            description="Show backend bridge status and connected Cheat Engine sessions.",
            parameters=(ParameterSpec("session_id", str | None, None),),
            handler=lambda session_id=None: ctx.get_bridge().status(),
        ),
        ToolSpec(
            name="ce.list_sessions",
            description="List Cheat Engine sessions currently connected to the MCP backend.",
            parameters=(ParameterSpec("session_id", str | None, None),),
            handler=lambda session_id=None: {"sessions": ctx.list_sessions()},
        ),
        ToolSpec(
            name="ce.normalize_address",
            description="Resolve a CE expression or symbol to an address.",
            parameters=(ParameterSpec("address", int | str), ParameterSpec("session_id", str | None, None)),
            handler=lambda address, session_id=None: _normalize_address_handler(ctx, address=address, session_id=session_id),
        ),
        ToolSpec(
            name="ce.verify_target",
            description="Return a quick target-health summary for the current attached process.",
            parameters=(ParameterSpec("session_id", str | None, None),),
            handler=lambda session_id=None: _verify_target_handler(ctx, session_id=session_id),
        ),
        native_tool(ctx, name="ce.list_tools", description="List native bridge tools advertised by the connected Cheat Engine plugin.", bridge_tool="ce.list_tools"),
        native_tool(ctx, name="ce.get_attached_process", description="Return the current process Cheat Engine is attached to.", bridge_tool="ce.get_attached_process"),
        native_tool(
            ctx,
            name="ce.attach_process",
            description="Attach Cheat Engine to a process by PID or process name.",
            bridge_tool="ce.attach_process",
            parameters=(ParameterSpec("process_id", int | None, None), ParameterSpec("process_name", str | None, None)),
        ),
        native_tool(ctx, name="ce.detach_process", description="Detach Cheat Engine from the current target process.", bridge_tool="ce.detach_process"),
        native_tool(ctx, name="ce.get_process_list", description="Enumerate processes visible from the connected Cheat Engine host.", bridge_tool="ce.get_process_list", parameters=(ParameterSpec("limit", int, 64),)),
        native_tool(ctx, name="ce.list_modules", description="List modules from the currently attached process.", bridge_tool="ce.list_modules", parameters=(ParameterSpec("limit", int, 256),), timeout_seconds=30.0),
        native_tool(ctx, name="ce.list_modules_full", description="Return the full module list from the currently attached process.", bridge_tool="ce.list_modules_full", timeout_seconds=30.0),
        native_tool(ctx, name="ce.query_memory", description="Inspect the memory region that contains the given address.", bridge_tool="ce.query_memory", parameters=(ParameterSpec("address", int | str),)),
        native_tool(
            ctx,
            name="ce.query_memory_map",
            description="Enumerate memory regions from the currently attached process.",
            bridge_tool="ce.query_memory_map",
            parameters=(
                ParameterSpec("limit", int, 256),
                ParameterSpec("start_address", int | str | None, None),
                ParameterSpec("end_address", int | str | None, None),
                ParameterSpec("include_free", bool, False),
            ),
            timeout_seconds=30.0,
        ),
        native_tool(
            ctx,
            name="ce.resolve_symbol",
            description="Resolve a symbol to an address, or an address back to a symbol-like name.",
            bridge_tool="ce.resolve_symbol",
            parameters=(ParameterSpec("symbol", str | None, None), ParameterSpec("address", int | str | None, None)),
            timeout_seconds=30.0,
        ),
        native_tool(
            ctx,
            name="ce.aob_scan",
            description="Scan the attached process for an AOB pattern like '48 8B ?? ?? FF'.",
            bridge_tool="ce.aob_scan",
            parameters=(
                ParameterSpec("pattern", str),
                ParameterSpec("module_name", str | None, None),
                ParameterSpec("start_address", int | str | None, None),
                ParameterSpec("end_address", int | str | None, None),
                ParameterSpec("max_results", int, 32),
            ),
            timeout_seconds=180.0,
        ),
        native_tool(ctx, name="ce.read_memory", description="Read raw bytes from the currently attached process.", bridge_tool="ce.read_memory", parameters=(ParameterSpec("address", int | str), ParameterSpec("size", int))),
        native_tool(ctx, name="ce.write_memory", description="Write raw hex bytes into the currently attached process.", bridge_tool="ce.write_memory", parameters=(ParameterSpec("address", int | str), ParameterSpec("bytes_hex", str))),
        native_tool(ctx, name="ce.exported.list", description="List fields from Cheat Engine's copied ExportedFunctions block.", bridge_tool="ce.exported.list", parameters=(ParameterSpec("available_only", bool, False), ParameterSpec("limit", int, 159))),
        native_tool(ctx, name="ce.exported.get", description="Inspect a specific field from Cheat Engine's copied ExportedFunctions block.", bridge_tool="ce.exported.get", parameters=(ParameterSpec("field_name", str),)),
    ]

    register_specs(server, specs)
