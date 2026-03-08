from __future__ import annotations

from pathlib import Path
import struct
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..bridge import BridgeError
from ..context import ToolContext
from ..errors import ToolUsageError
from ..registration import ParameterSpec, ToolSpec, register_specs
from ..runtime.process_runtime import PROCESS_RUNTIME
from .common import native_tool

AOB_SCAN_TIMEOUT_PARAMETER = ParameterSpec("timeout_seconds", float, 300.0)
NATIVE_TIMEOUT_PARAMETER = ParameterSpec("timeout_seconds", float, 30.0)


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


def _resolve_module_entry(ctx: ToolContext, session_id: str, module_name: str) -> dict[str, Any]:
    modules = ctx.native_call_strict("ce.list_modules_full", session_id=session_id, timeout_seconds=30.0)
    for entry in modules.get("modules", []):
        if isinstance(entry, dict) and _module_matches(entry, module_name):
            return dict(entry)
    raise ToolUsageError(
        "module was not found in the attached target",
        code="module_not_found",
        hint="Refresh the module list and confirm the target is still attached to the expected process.",
        details={"module_name": module_name},
    )


def _read_remote_bytes(ctx: ToolContext, session_id: str, address: int, size: int) -> bytes:
    result = ctx.native_call_strict(
        "ce.read_memory",
        payload={"address": address, "size": size},
        session_id=session_id,
        timeout_seconds=30.0,
    )
    try:
        return bytes.fromhex(str(result.get("bytes_hex", "")))
    except ValueError as exc:  # pragma: no cover - defensive against malformed bridge data
        raise BridgeError("read_memory returned malformed hex bytes") from exc


def _resolve_pe_section_bounds(ctx: ToolContext, session_id: str, module_name: str, section_name: str) -> tuple[int, int]:
    module = _resolve_module_entry(ctx, session_id, module_name)
    module_base = int(module.get("base_address", 0) or 0)
    if module_base <= 0:
        raise ToolUsageError(
            "module base address is invalid",
            code="invalid_module_base",
            details={"module_name": module_name, "base_address": module.get("base_address")},
        )

    headers = _read_remote_bytes(ctx, session_id, module_base, 0x4000)
    if len(headers) < 0x100:
        raise BridgeError("module header read was too small to resolve PE sections")

    e_lfanew = struct.unpack_from("<I", headers, 0x3C)[0]
    if e_lfanew + 24 > len(headers) or headers[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        raise BridgeError("module PE headers could not be parsed")

    file_header_offset = e_lfanew + 4
    number_of_sections = struct.unpack_from("<H", headers, file_header_offset + 2)[0]
    size_of_optional_header = struct.unpack_from("<H", headers, file_header_offset + 16)[0]
    section_table_offset = file_header_offset + 20 + size_of_optional_header
    normalized_requested = section_name.casefold().lstrip(".")

    for index in range(number_of_sections):
        entry_offset = section_table_offset + index * 40
        if entry_offset + 40 > len(headers):
            break

        raw_name = headers[entry_offset:entry_offset + 8].split(b"\x00", 1)[0].decode("ascii", errors="ignore")
        if raw_name.casefold().lstrip(".") != normalized_requested:
            continue

        virtual_size = struct.unpack_from("<I", headers, entry_offset + 8)[0]
        virtual_address = struct.unpack_from("<I", headers, entry_offset + 12)[0]
        if virtual_size == 0:
            virtual_size = struct.unpack_from("<I", headers, entry_offset + 16)[0]
        if virtual_size <= 0:
            break
        start_address = module_base + virtual_address
        return start_address, start_address + virtual_size

    raise ToolUsageError(
        "section was not found in the module PE headers",
        code="section_not_found",
        hint="Use ce.list_modules_full to confirm the module name, or omit section_name to scan the full module.",
        details={"module_name": module_name, "section_name": section_name},
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


def _aob_scan_handler(ctx: ToolContext,
                      *,
                      pattern: str,
                      module_name: str | None = None,
                      section_name: str | None = None,
                      start_address: int | str | None = None,
                      end_address: int | str | None = None,
                      scan_alignment: str = "x1",
                      scan_hint: str = "none",
                      max_results: int = 32,
                      timeout_seconds: float = 300.0,
                      session_id: str | None = None) -> dict[str, Any]:
    normalized_timeout = float(timeout_seconds)
    if normalized_timeout <= 0.0:
        raise ToolUsageError(
            "timeout_seconds must be greater than zero",
            code="invalid_timeout_seconds",
            hint="Use a positive timeout in seconds for large-module AOB scans.",
            details={"received": timeout_seconds},
        )

    if section_name is not None and module_name is None:
        raise ToolUsageError(
            "section_name requires module_name",
            code="missing_module_name",
            hint="Pass module_name when limiting a libhat scan to a PE section such as .text or .rdata.",
            details={"section_name": section_name},
        )

    if module_name is not None and (start_address is not None or end_address is not None):
        raise ToolUsageError(
            "module_name cannot be combined with start_address or end_address",
            code="invalid_scan_scope",
            hint="Use either module_name/section_name or an explicit address range for the scan scope.",
            details={"module_name": module_name, "start_address": start_address, "end_address": end_address},
        )

    resolved_session = ctx.resolve_session_id(session_id)
    payload = {
        "pattern": pattern,
        "module_name": module_name,
        "section_name": section_name,
        "start_address": start_address,
        "end_address": end_address,
        "scan_alignment": scan_alignment,
        "scan_hint": scan_hint,
        "max_results": max_results,
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    return ctx.native_call_safe(
        "ce.aob_scan",
        payload=payload or None,
        session_id=resolved_session,
        timeout_seconds=normalized_timeout,
    ) if section_name is None else _aob_scan_with_section_fallback(
        ctx,
        resolved_session=resolved_session,
        payload=payload,
        module_name=module_name,
        section_name=section_name,
        timeout_seconds=normalized_timeout,
    )


def _aob_scan_with_section_fallback(ctx: ToolContext,
                                    *,
                                    resolved_session: str,
                                    payload: dict[str, Any],
                                    module_name: str | None,
                                    section_name: str,
                                    timeout_seconds: float) -> dict[str, Any]:
    result = ctx.native_call_safe(
        "ce.aob_scan",
        payload=payload,
        session_id=resolved_session,
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok") is True or int(result.get("win32_error", 0) or 0) != 1168 or module_name is None:
        return result

    start_address, end_address = _resolve_pe_section_bounds(ctx, resolved_session, module_name, section_name)
    fallback_payload = dict(payload)
    fallback_payload.pop("module_name", None)
    fallback_payload.pop("section_name", None)
    fallback_payload["start_address"] = start_address
    fallback_payload["end_address"] = end_address
    fallback_result = ctx.native_call_safe(
        "ce.aob_scan",
        payload=fallback_payload,
        session_id=resolved_session,
        timeout_seconds=timeout_seconds,
    )
    if fallback_result.get("ok") is True:
        fallback_result = dict(fallback_result)
        fallback_result["module_name"] = module_name
        fallback_result["section_name"] = section_name
        fallback_result["resolved_scope"] = "pe_section_range"
        fallback_result.setdefault("start_address", start_address)
        fallback_result.setdefault("end_address", end_address)
    return fallback_result


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
                NATIVE_TIMEOUT_PARAMETER,
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
        ToolSpec(
            name="ce.aob_scan",
            description="Scan the attached process for an AOB pattern like '48 8B ?? ?? FF'.",
            parameters=(
                ParameterSpec("pattern", str),
                ParameterSpec("module_name", str | None, None),
                ParameterSpec("section_name", str | None, None),
                ParameterSpec("start_address", int | str | None, None),
                ParameterSpec("end_address", int | str | None, None),
                ParameterSpec("scan_alignment", str, "x1"),
                ParameterSpec("scan_hint", str, "none"),
                ParameterSpec("max_results", int, 32),
                AOB_SCAN_TIMEOUT_PARAMETER,
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda **kwargs: _aob_scan_handler(ctx, **kwargs),
        ),
        native_tool(ctx, name="ce.read_memory", description="Read raw bytes from the currently attached process.", bridge_tool="ce.read_memory", parameters=(ParameterSpec("address", int | str), ParameterSpec("size", int))),
        native_tool(ctx, name="ce.write_memory", description="Write raw hex bytes into the currently attached process.", bridge_tool="ce.write_memory", parameters=(ParameterSpec("address", int | str), ParameterSpec("bytes_hex", str))),
        native_tool(ctx, name="ce.exported.list", description="List fields from Cheat Engine's copied ExportedFunctions block.", bridge_tool="ce.exported.list", parameters=(ParameterSpec("available_only", bool, False), ParameterSpec("limit", int, 159))),
        native_tool(ctx, name="ce.exported.get", description="Inspect a specific field from Cheat Engine's copied ExportedFunctions block.", bridge_tool="ce.exported.get", parameters=(ParameterSpec("field_name", str),)),
    ]

    register_specs(server, specs)
