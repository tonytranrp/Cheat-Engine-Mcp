from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..errors import ToolUsageError
from ..registration import ParameterSpec, ToolSpec, register_specs
from .common import lua_function_tool
from .native_tools import _aob_scan_handler


AOB_SCAN_TIMEOUT_PARAMETER = ParameterSpec("timeout_seconds", float, 300.0)


def _normalize_match_list(result: dict[str, Any]) -> list[int]:
    return [match for match in result.get("matches", []) if isinstance(match, int)]


def _run_aob_unique(ctx: ToolContext,
                    *,
                    pattern: str,
                    module_name: str | None = None,
                    section_name: str | None = None,
                    start_address: int | str | None = None,
                    end_address: int | str | None = None,
                    scan_alignment: str = "x1",
                    scan_hint: str = "none",
                    timeout_seconds: float = 300.0,
                    session_id: str | None = None) -> dict[str, Any]:
    if section_name is not None and module_name is None:
        raise ToolUsageError(
            "section_name requires module_name",
            code="missing_module_name",
            hint="Pass module_name when limiting a libhat scan to a PE section.",
            details={"section_name": section_name},
        )

    if module_name is not None and (start_address is not None or end_address is not None):
        raise ToolUsageError(
            "module_name cannot be combined with start_address or end_address",
            code="invalid_scan_scope",
            hint="Use module_name/section_name or an explicit address range, not both.",
            details={"module_name": module_name, "start_address": start_address, "end_address": end_address},
        )

    resolved_session = ctx.resolve_session_id(session_id)
    result = _aob_scan_handler(
        ctx,
        pattern=pattern,
        module_name=module_name,
        section_name=section_name,
        start_address=start_address,
        end_address=end_address,
        scan_alignment=scan_alignment,
        scan_hint=scan_hint,
        max_results=2,
        timeout_seconds=float(timeout_seconds),
        session_id=resolved_session,
    )
    if result.get("ok") is not True:
        return result

    matches = _normalize_match_list(result)
    unique = len(matches) == 1 and not bool(result.get("truncated", False))
    response: dict[str, Any] = {
        "ok": True,
        "session_id": str(result.get("session_id", resolved_session)),
        "pattern": pattern,
        "match_count": len(matches),
        "unique": unique,
        "truncated": bool(result.get("truncated", False)),
        "matches": matches,
        "scan_alignment": scan_alignment,
        "scan_hint": scan_hint,
    }
    if module_name is not None:
        response["module_name"] = module_name
    if section_name is not None:
        response["section_name"] = section_name
    if start_address is not None:
        response["start_address"] = start_address
    if end_address is not None:
        response["end_address"] = end_address
    if unique:
        response["address"] = matches[0]
        response["address_hex"] = hex(matches[0])
    return response


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
        lua_function_tool(ctx, name="ce.get_address", description="Resolve a CE expression or symbol to an address.", function_name="getAddress", parameters=(ParameterSpec("expression", str),), result_field="address"),
        lua_function_tool(ctx, name="ce.get_address_safe", description="Safely resolve a CE expression or symbol to an address, returning nil on failure.", function_name="getAddressSafe", parameters=(ParameterSpec("expression", str),), result_field="address"),
        lua_function_tool(ctx, name="ce.get_name_from_address", description="Convert an address back into a CE symbol-like name.", function_name="getNameFromAddress", parameters=(ParameterSpec("address", int | str),), result_field="name"),
        lua_function_tool(ctx, name="ce.register_symbol", description="Register a named symbol in Cheat Engine.", function_name="registerSymbol", parameters=(ParameterSpec("name", str), ParameterSpec("address", int | str), ParameterSpec("donotsave", bool, False))),
        lua_function_tool(ctx, name="ce.unregister_symbol", description="Unregister a named symbol from Cheat Engine.", function_name="unregisterSymbol", parameters=(ParameterSpec("name", str),)),
        lua_function_tool(ctx, name="ce.reinitialize_symbolhandler", description="Reinitialize Cheat Engine's symbol handler.", function_name="reinitializeSymbolhandler", parameters=()),
        lua_function_tool(ctx, name="ce.in_module", description="Return whether an address falls inside a loaded module according to CE.", function_name="inModule", parameters=(ParameterSpec("address", int | str),), result_field="value"),
        lua_function_tool(ctx, name="ce.in_system_module", description="Return whether an address falls inside a system module according to CE.", function_name="inSystemModule", parameters=(ParameterSpec("address", int | str),), result_field="value"),
        ToolSpec(
            name="ce.aob_scan_unique",
            description="Run a unique libhat-backed AOB scan and return one matching address when the result set is unique.",
            parameters=(
                ParameterSpec("pattern", str),
                ParameterSpec("module_name", str | None, None),
                ParameterSpec("section_name", str | None, None),
                ParameterSpec("start_address", int | str | None, None),
                ParameterSpec("end_address", int | str | None, None),
                ParameterSpec("scan_alignment", str, "x1"),
                ParameterSpec("scan_hint", str, "none"),
                AOB_SCAN_TIMEOUT_PARAMETER,
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda **kwargs: _run_aob_unique(ctx, **kwargs),
        ),
        ToolSpec(
            name="ce.aob_scan_module_unique",
            description="Run a unique libhat-backed AOB scan against one module and return one matching address when the result set is unique.",
            parameters=(
                ParameterSpec("module_name", str),
                ParameterSpec("pattern", str),
                ParameterSpec("section_name", str | None, None),
                ParameterSpec("scan_alignment", str, "x1"),
                ParameterSpec("scan_hint", str, "none"),
                AOB_SCAN_TIMEOUT_PARAMETER,
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda module_name, pattern, section_name=None, scan_alignment="x1", scan_hint="none", timeout_seconds=300.0, session_id=None: _run_aob_unique(
                ctx,
                pattern=pattern,
                module_name=module_name,
                section_name=section_name,
                scan_alignment=scan_alignment,
                scan_hint=scan_hint,
                timeout_seconds=timeout_seconds,
                session_id=session_id,
            ),
        ),
    ]
    register_specs(server, specs)
