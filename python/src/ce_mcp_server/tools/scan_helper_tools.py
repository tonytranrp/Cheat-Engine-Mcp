from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..bridge import BridgeError
from ..context import ToolContext
from ..errors import ToolStateError, ToolUsageError
from ..registration import ParameterSpec, ToolSpec, register_specs
from ..runtime.scan_runtime import SCAN_RUNTIME

DEFAULT_PROTECTION_FLAGS = "*X*C*W"
DEFAULT_START_ADDRESS = 0
DEFAULT_END_ADDRESS = 0x7FFFFFFFFFFFFFFF
DEFAULT_RESULT_LIMIT = 128
MAX_RESULT_LIMIT = 4096

SCAN_SESSION_PARAMETER = ParameterSpec("scan_session_id", str)
SCAN_OPTION_PARAMETER = ParameterSpec("scan_option", str, "exact")
VALUE_TYPE_PARAMETER = ParameterSpec("value_type", str, "dword")
VALUE_PARAMETER = ParameterSpec("value", object | None, None)
VALUE2_PARAMETER = ParameterSpec("value2", object | None, None)
MODULE_NAME_PARAMETER = ParameterSpec("module_name", str | None, None)
START_ADDRESS_PARAMETER = ParameterSpec("start_address", int | str | None, None)
END_ADDRESS_PARAMETER = ParameterSpec("end_address", int | str | None, None)
LIMIT_PARAMETER = ParameterSpec("limit", int, DEFAULT_RESULT_LIMIT)
ROUNDING_PARAMETER = ParameterSpec("rounding_type", str, "rounded")
PROTECTION_PARAMETER = ParameterSpec("protection_flags", str, DEFAULT_PROTECTION_FLAGS)
ALIGNMENT_TYPE_PARAMETER = ParameterSpec("alignment_type", str, "not_aligned")
ALIGNMENT_PARAMETER = ParameterSpec("alignment_param", str, "1")
HEX_INPUT_PARAMETER = ParameterSpec("is_hexadecimal_input", bool, False)
NOT_BINARY_PARAMETER = ParameterSpec("is_not_binary_string", bool, False)
UNICODE_PARAMETER = ParameterSpec("is_unicode_scan", bool, False)
CASE_PARAMETER = ParameterSpec("is_case_sensitive", bool, False)
PERCENTAGE_PARAMETER = ParameterSpec("is_percentage_scan", bool, False)
SAVED_RESULT_PARAMETER = ParameterSpec("saved_result_name", str | None, None)


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


def _normalize_limit(limit: int) -> int:
    if limit <= 0 or limit > MAX_RESULT_LIMIT:
        raise ToolUsageError(
            f"limit must be between 1 and {MAX_RESULT_LIMIT}",
            code="invalid_limit",
            hint="Use a positive result limit within the supported range.",
            details={"minimum": 1, "maximum": MAX_RESULT_LIMIT, "received": limit},
        )
    return int(limit)


def _runtime_call_strict(ctx: ToolContext,
                         function_name: str,
                         *,
                         args: list[Any] | tuple[Any, ...] | None = None,
                         session_id: str,
                         timeout_seconds: float) -> dict[str, Any]:
    result = ctx.call_runtime_function(
        SCAN_RUNTIME,
        function_name,
        args=args,
        session_id=session_id,
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok") is not True:
        raise BridgeError(str(result.get("error", f"scan runtime '{function_name}' failed")))
    return result


def _destroy_scan_session_quietly(ctx: ToolContext, ce_session_id: str, scan_session_id: str) -> None:
    try:
        _runtime_call_strict(
            ctx,
            "destroy_session",
            args=[scan_session_id],
            session_id=ce_session_id,
            timeout_seconds=30.0,
        )
    except BridgeError:
        pass


def _module_matches(entry: dict[str, Any], requested_name: str) -> bool:
    requested = requested_name.casefold()
    module_name = str(entry.get("module_name", ""))
    module_path = str(entry.get("module_path", ""))
    return (
        module_name.casefold() == requested or
        module_path.casefold() == requested or
        Path(module_path).name.casefold() == requested
    )


def _resolve_module_bounds(ctx: ToolContext, ce_session_id: str, module_name: str) -> tuple[int, int, dict[str, Any]]:
    modules = ctx.native_call_strict(
        "ce.list_modules_full",
        session_id=ce_session_id,
        timeout_seconds=30.0,
    )
    for entry in modules.get("modules", []):
        if isinstance(entry, dict) and _module_matches(entry, module_name):
            base_address = _parse_integer(entry.get("base_address"))
            size = _parse_integer(entry.get("size"))
            if base_address is None or size is None or size <= 0:
                raise ToolStateError(
                    f"module '{module_name}' returned an invalid base/size",
                    code="invalid_module_bounds",
                    hint="The target module metadata is incomplete, so the scan range cannot be derived safely.",
                    details={"module_name": module_name},
                )
            return base_address, base_address + size, entry
    raise ToolUsageError(
        f"module '{module_name}' was not found in the attached process",
        code="module_not_found",
        hint="Use ce.list_modules or ce.list_modules_full to inspect loaded module names first.",
        details={"module_name": module_name},
        next_steps=[
            "Call ce.list_modules or ce.list_modules_full.",
            "Retry the scan with the exact module_name returned by Cheat Engine.",
        ],
    )


def _resolve_address_expression(ctx: ToolContext, ce_session_id: str, value: int | str | None, field_name: str) -> int | None:
    if value is None:
        return None

    parsed = _parse_integer(value)
    if parsed is not None:
        return parsed

    if not isinstance(value, str):
        raise ToolUsageError(
            f"{field_name} must be an integer or CE address expression",
            code="invalid_address_expression",
            hint="Pass an integer address or a Cheat Engine address expression such as module.exe+1234.",
            details={"field_name": field_name, "received_type": type(value).__name__},
        )

    resolved = ctx.call_lua_function(
        "getAddressSafe",
        args=[value],
        session_id=ce_session_id,
        result_field="address",
        timeout_seconds=30.0,
    )
    if resolved.get("ok") is not True:
        raise BridgeError(str(resolved.get("error", f"failed to resolve {field_name}")))

    parsed = _parse_integer(resolved.get("address"))
    if parsed is None:
        raise ToolUsageError(
            f"could not resolve {field_name}: {value}",
            code="address_resolution_failed",
            hint="The expression did not resolve to a concrete address in the attached process.",
            details={"field_name": field_name, "expression": value},
        )
    return parsed


def _resolve_scope(ctx: ToolContext,
                   ce_session_id: str,
                   *,
                   module_name: str | None,
                   start_address: int | str | None,
                   end_address: int | str | None) -> tuple[int | None, int | None, dict[str, Any]]:
    if module_name and (start_address is not None or end_address is not None):
        raise ToolUsageError(
            "use either module_name or explicit start/end addresses, not both",
            code="conflicting_scan_scope",
            hint="Choose one scan scope style: module_name or explicit start/end bounds.",
            next_steps=[
                "Use module_name when the target is expected inside one loaded module.",
                "Use start_address/end_address when you need an explicit range.",
            ],
        )

    if module_name:
        start, end, entry = _resolve_module_bounds(ctx, ce_session_id, module_name)
        return start, end, {
            "module_name": str(entry.get("module_name", module_name)),
            "module_path": str(entry.get("module_path", "")),
            "start_address": start,
            "end_address": end,
        }

    resolved_start = _resolve_address_expression(ctx, ce_session_id, start_address, "start_address")
    resolved_end = _resolve_address_expression(ctx, ce_session_id, end_address, "end_address")
    return resolved_start, resolved_end, {
        "start_address": resolved_start,
        "end_address": resolved_end,
    }


def _normalize_result_entry(entry: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    if "index" in entry:
        normalized["index"] = entry["index"]

    raw_address = entry.get("address")
    parsed_address = _parse_integer(raw_address)
    if parsed_address is not None:
        normalized["address"] = parsed_address
        normalized["address_hex"] = hex(parsed_address)
    else:
        normalized["address"] = raw_address

    normalized["value"] = entry.get("value")
    return normalized


def _normalize_results_payload(results: dict[str, Any]) -> dict[str, Any]:
    normalized_results = [
        _normalize_result_entry(entry)
        for entry in results.get("results", [])
        if isinstance(entry, dict)
    ]
    count = _parse_integer(results.get("count"))
    returned_count = _parse_integer(results.get("returned_count"))
    return {
        "count": count if count is not None else len(normalized_results),
        "returned_count": returned_count if returned_count is not None else len(normalized_results),
        "truncated": bool(results.get("truncated", False)),
        "results": normalized_results,
    }


def _build_first_scan_options(*,
                              scan_option: str,
                              value_type: str,
                              value: Any = None,
                              value2: Any = None,
                              rounding_type: str = "rounded",
                              start_address: int | None = None,
                              end_address: int | None = None,
                              protection_flags: str = DEFAULT_PROTECTION_FLAGS,
                              alignment_type: str = "not_aligned",
                              alignment_param: str = "1",
                              is_hexadecimal_input: bool = False,
                              is_not_binary_string: bool = False,
                              is_unicode_scan: bool = False,
                              is_case_sensitive: bool = False) -> dict[str, Any]:
    return {
        "scan_option": scan_option,
        "value_type": value_type,
        "rounding_type": rounding_type,
        "input1": "" if value is None else str(value),
        "input2": "" if value2 is None else str(value2),
        "start_address": DEFAULT_START_ADDRESS if start_address is None else start_address,
        "stop_address": DEFAULT_END_ADDRESS if end_address is None else end_address,
        "protection_flags": protection_flags,
        "alignment_type": alignment_type,
        "alignment_param": alignment_param,
        "is_hexadecimal_input": bool(is_hexadecimal_input),
        "is_not_binary_string": bool(is_not_binary_string),
        "is_unicode_scan": bool(is_unicode_scan),
        "is_case_sensitive": bool(is_case_sensitive),
    }


def _build_next_scan_options(*,
                             scan_option: str,
                             value: Any = None,
                             value2: Any = None,
                             rounding_type: str = "rounded",
                             is_hexadecimal_input: bool = False,
                             is_not_binary_string: bool = False,
                             is_unicode_scan: bool = False,
                             is_case_sensitive: bool = False,
                             is_percentage_scan: bool = False,
                             saved_result_name: str | None = None) -> dict[str, Any]:
    return {
        "scan_option": scan_option,
        "rounding_type": rounding_type,
        "input1": "" if value is None else str(value),
        "input2": "" if value2 is None else str(value2),
        "is_hexadecimal_input": bool(is_hexadecimal_input),
        "is_not_binary_string": bool(is_not_binary_string),
        "is_unicode_scan": bool(is_unicode_scan),
        "is_case_sensitive": bool(is_case_sensitive),
        "is_percentage_scan": bool(is_percentage_scan),
        "saved_result_name": "" if saved_result_name is None else saved_result_name,
    }


def _collect_scan_results(ctx: ToolContext, ce_session_id: str, scan_session_id: str, limit: int) -> dict[str, Any]:
    _runtime_call_strict(
        ctx,
        "attach_foundlist",
        args=[scan_session_id],
        session_id=ce_session_id,
        timeout_seconds=30.0,
    )
    results = _runtime_call_strict(
        ctx,
        "get_results",
        args=[scan_session_id, _normalize_limit(limit)],
        session_id=ce_session_id,
        timeout_seconds=30.0,
    )
    payload = _normalize_results_payload(results)
    payload["scan_session_id"] = scan_session_id
    return payload


def _get_scan_session_state(ctx: ToolContext, ce_session_id: str, scan_session_id: str) -> dict[str, Any]:
    result = _runtime_call_strict(
        ctx,
        "get_session_state",
        args=[scan_session_id],
        session_id=ce_session_id,
        timeout_seconds=30.0,
    )
    return {
        "session_id": str(result.get("session_id", scan_session_id)),
        "state": str(result.get("state", "unknown")),
        "scan_in_progress": bool(result.get("scan_in_progress", False)),
        "has_completed_scan": bool(result.get("has_completed_scan", False)),
        "last_scan_kind": result.get("last_scan_kind"),
        "last_result_count": _parse_integer(result.get("last_result_count")) or 0,
    }


def _run_one_shot_scan(ctx: ToolContext,
                       *,
                       session_id: str | None,
                       options: dict[str, Any],
                       limit: int) -> dict[str, Any]:
    ce_session_id = ctx.resolve_session_id(session_id)
    created = _runtime_call_strict(
        ctx,
        "create_session",
        session_id=ce_session_id,
        timeout_seconds=30.0,
    )
    scan_session_id = str(created.get("session_id"))

    try:
        _runtime_call_strict(
            ctx,
            "first_scan",
            args=[scan_session_id, options],
            session_id=ce_session_id,
            timeout_seconds=120.0,
        )
        _runtime_call_strict(
            ctx,
            "wait",
            args=[scan_session_id],
            session_id=ce_session_id,
            timeout_seconds=180.0,
        )
        payload = _collect_scan_results(ctx, ce_session_id, scan_session_id, limit)
        payload["ce_session_id"] = ce_session_id
        return payload
    finally:
        _destroy_scan_session_quietly(ctx, ce_session_id, scan_session_id)


def _first_scan_handler(ctx: ToolContext,
                        *,
                        scan_session_id: str,
                        scan_option: str = "exact",
                        value_type: str = "dword",
                        value: Any = None,
                        value2: Any = None,
                        module_name: str | None = None,
                        start_address: int | str | None = None,
                        end_address: int | str | None = None,
                        rounding_type: str = "rounded",
                        protection_flags: str = DEFAULT_PROTECTION_FLAGS,
                        alignment_type: str = "not_aligned",
                        alignment_param: str = "1",
                        is_hexadecimal_input: bool = False,
                        is_not_binary_string: bool = False,
                        is_unicode_scan: bool = False,
                        is_case_sensitive: bool = False,
                        session_id: str | None = None) -> dict[str, Any]:
    ce_session_id = ctx.resolve_session_id(session_id)
    resolved_start, resolved_end, scope = _resolve_scope(
        ctx,
        ce_session_id,
        module_name=module_name,
        start_address=start_address,
        end_address=end_address,
    )
    options = _build_first_scan_options(
        scan_option=scan_option,
        value_type=value_type,
        value=value,
        value2=value2,
        rounding_type=rounding_type,
        start_address=resolved_start,
        end_address=resolved_end,
        protection_flags=protection_flags,
        alignment_type=alignment_type,
        alignment_param=alignment_param,
        is_hexadecimal_input=is_hexadecimal_input,
        is_not_binary_string=is_not_binary_string,
        is_unicode_scan=is_unicode_scan,
        is_case_sensitive=is_case_sensitive,
    )
    result = _runtime_call_strict(
        ctx,
        "first_scan",
        args=[scan_session_id, options],
        session_id=ce_session_id,
        timeout_seconds=120.0,
    )
    return {
        "ok": True,
        "ce_session_id": ce_session_id,
        "scan_session_id": scan_session_id,
        "started": bool(result.get("started", False)),
        "scan_option": scan_option,
        "value_type": value_type,
        "value": None if value is None else str(value),
        "value2": None if value2 is None else str(value2),
        "scope": scope,
    }


def _next_scan_handler(ctx: ToolContext,
                       *,
                       scan_session_id: str,
                       scan_option: str = "exact",
                       value: Any = None,
                       value2: Any = None,
                       rounding_type: str = "rounded",
                       is_hexadecimal_input: bool = False,
                       is_not_binary_string: bool = False,
                       is_unicode_scan: bool = False,
                       is_case_sensitive: bool = False,
                       is_percentage_scan: bool = False,
                       saved_result_name: str | None = None,
                       session_id: str | None = None) -> dict[str, Any]:
    ce_session_id = ctx.resolve_session_id(session_id)
    state = _get_scan_session_state(ctx, ce_session_id, scan_session_id)
    if state["scan_in_progress"]:
        raise ToolStateError(
            "This scan session already has an active scan in progress.",
            code="scan_wait_required",
            hint="Wait for the current scan to finish before starting a follow-up scan.",
            details={"scan_session_id": scan_session_id, "state": state["state"]},
            next_steps=[
                "Call ce.scan_wait(scan_session_id=...).",
                "Optionally inspect ce.scan_get_progress(scan_session_id=...).",
                "Retry ce.scan_next_ex after the wait completes.",
            ],
            required_order=[
                "ce.scan_create_session",
                "ce.scan_first_ex",
                "ce.scan_wait",
                "ce.scan_next_ex",
            ],
        )
    if not state["has_completed_scan"]:
        raise ToolStateError(
            "A completed first scan is required before this follow-up scan.",
            code="scan_first_scan_required",
            hint="ce.scan_next_ex refines an existing result set; it does not create the initial one.",
            details={"scan_session_id": scan_session_id, "state": state["state"]},
            next_steps=[
                "Call ce.scan_first_ex or ce.scan_first on the same scan_session_id.",
                "Call ce.scan_wait.",
                "Then retry ce.scan_next_ex.",
            ],
            required_order=[
                "ce.scan_create_session",
                "ce.scan_first_ex",
                "ce.scan_wait",
                "ce.scan_next_ex",
            ],
            example='ce.scan_first_ex(scan_session_id="scan-1", scan_option="exact", value_type="dword", value=100)',
        )
    options = _build_next_scan_options(
        scan_option=scan_option,
        value=value,
        value2=value2,
        rounding_type=rounding_type,
        is_hexadecimal_input=is_hexadecimal_input,
        is_not_binary_string=is_not_binary_string,
        is_unicode_scan=is_unicode_scan,
        is_case_sensitive=is_case_sensitive,
        is_percentage_scan=is_percentage_scan,
        saved_result_name=saved_result_name,
    )
    result = _runtime_call_strict(
        ctx,
        "next_scan",
        args=[scan_session_id, options],
        session_id=ce_session_id,
        timeout_seconds=120.0,
    )
    return {
        "ok": True,
        "ce_session_id": ce_session_id,
        "scan_session_id": scan_session_id,
        "started": bool(result.get("started", False)),
        "scan_option": scan_option,
        "value": None if value is None else str(value),
        "value2": None if value2 is None else str(value2),
        "saved_result_name": saved_result_name,
    }


def _scan_collect_handler(ctx: ToolContext,
                          *,
                          scan_session_id: str,
                          limit: int = DEFAULT_RESULT_LIMIT,
                          session_id: str | None = None) -> dict[str, Any]:
    ce_session_id = ctx.resolve_session_id(session_id)
    state = _get_scan_session_state(ctx, ce_session_id, scan_session_id)
    if state["scan_in_progress"]:
        raise ToolStateError(
            "Results are not ready while the scan is still running.",
            code="scan_results_wait_required",
            hint="Wait for the scan to finish before collecting FoundList results.",
            details={"scan_session_id": scan_session_id, "state": state["state"]},
            next_steps=[
                "Call ce.scan_wait(scan_session_id=...).",
                "Then call ce.scan_collect(scan_session_id=...).",
            ],
            required_order=[
                "ce.scan_create_session",
                "ce.scan_first_ex",
                "ce.scan_wait",
                "ce.scan_collect",
            ],
        )
    payload = _collect_scan_results(ctx, ce_session_id, scan_session_id, limit)
    payload["ok"] = True
    payload["ce_session_id"] = ce_session_id
    return payload


def _scan_once_handler(ctx: ToolContext,
                       *,
                       scan_option: str = "exact",
                       value_type: str = "dword",
                       value: Any = None,
                       value2: Any = None,
                       module_name: str | None = None,
                       start_address: int | str | None = None,
                       end_address: int | str | None = None,
                       limit: int = DEFAULT_RESULT_LIMIT,
                       rounding_type: str = "rounded",
                       protection_flags: str = DEFAULT_PROTECTION_FLAGS,
                       alignment_type: str = "not_aligned",
                       alignment_param: str = "1",
                       is_hexadecimal_input: bool = False,
                       is_not_binary_string: bool = False,
                       is_unicode_scan: bool = False,
                       is_case_sensitive: bool = False,
                       session_id: str | None = None) -> dict[str, Any]:
    ce_session_id = ctx.resolve_session_id(session_id)
    resolved_start, resolved_end, scope = _resolve_scope(
        ctx,
        ce_session_id,
        module_name=module_name,
        start_address=start_address,
        end_address=end_address,
    )
    options = _build_first_scan_options(
        scan_option=scan_option,
        value_type=value_type,
        value=value,
        value2=value2,
        rounding_type=rounding_type,
        start_address=resolved_start,
        end_address=resolved_end,
        protection_flags=protection_flags,
        alignment_type=alignment_type,
        alignment_param=alignment_param,
        is_hexadecimal_input=is_hexadecimal_input,
        is_not_binary_string=is_not_binary_string,
        is_unicode_scan=is_unicode_scan,
        is_case_sensitive=is_case_sensitive,
    )
    payload = _run_one_shot_scan(ctx, session_id=ce_session_id, options=options, limit=limit)
    payload.update(
        {
            "ok": True,
            "scan_option": scan_option,
            "value_type": value_type,
            "value": None if value is None else str(value),
            "value2": None if value2 is None else str(value2),
            "scope": scope,
        }
    )
    return payload


def _scan_value_handler(ctx: ToolContext,
                        *,
                        value: Any = None,
                        value_type: str = "dword",
                        scan_option: str = "exact",
                        value2: Any = None,
                        module_name: str | None = None,
                        start_address: int | str | None = None,
                        end_address: int | str | None = None,
                        limit: int = DEFAULT_RESULT_LIMIT,
                        rounding_type: str = "rounded",
                        protection_flags: str = DEFAULT_PROTECTION_FLAGS,
                        alignment_type: str = "not_aligned",
                        alignment_param: str = "1",
                        is_hexadecimal_input: bool = False,
                        is_not_binary_string: bool = False,
                        is_unicode_scan: bool = False,
                        is_case_sensitive: bool = False,
                        session_id: str | None = None) -> dict[str, Any]:
    return _scan_once_handler(
        ctx,
        scan_option=scan_option,
        value_type=value_type,
        value=value,
        value2=value2,
        module_name=module_name,
        start_address=start_address,
        end_address=end_address,
        limit=limit,
        rounding_type=rounding_type,
        protection_flags=protection_flags,
        alignment_type=alignment_type,
        alignment_param=alignment_param,
        is_hexadecimal_input=is_hexadecimal_input,
        is_not_binary_string=is_not_binary_string,
        is_unicode_scan=is_unicode_scan,
        is_case_sensitive=is_case_sensitive,
        session_id=session_id,
    )


def _merge_string_scan_results(payloads: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    total_count = 0
    truncated = False
    ce_session_id = ""

    for payload in payloads:
        total_count += int(payload.get("count", 0))
        truncated = truncated or bool(payload.get("truncated", False))
        ce_session_id = str(payload.get("ce_session_id", ce_session_id))
        for entry in payload.get("results", []):
            if not isinstance(entry, dict):
                continue
            key = (entry.get("address"), entry.get("encoding"))
            if key in seen:
                continue
            seen.add(key)
            if len(merged) >= limit:
                truncated = True
                continue
            merged.append(entry)

    return {
        "ok": True,
        "ce_session_id": ce_session_id,
        "count": total_count,
        "returned_count": len(merged),
        "truncated": truncated,
        "results": merged,
    }


def _scan_string_single(ctx: ToolContext,
                        *,
                        text: str,
                        encoding: str,
                        case_sensitive: bool,
                        module_name: str | None,
                        start_address: int | str | None,
                        end_address: int | str | None,
                        limit: int,
                        protection_flags: str,
                        session_id: str | None) -> dict[str, Any]:
    payload = _scan_once_handler(
        ctx,
        scan_option="exact",
        value_type="string",
        value=text,
        module_name=module_name,
        start_address=start_address,
        end_address=end_address,
        limit=limit,
        rounding_type="rounded",
        protection_flags=protection_flags,
        alignment_type="not_aligned",
        alignment_param="1",
        is_hexadecimal_input=False,
        is_not_binary_string=False,
        is_unicode_scan=(encoding == "utf16"),
        is_case_sensitive=case_sensitive,
        session_id=session_id,
    )
    for entry in payload.get("results", []):
        if isinstance(entry, dict):
            entry["encoding"] = encoding
            entry["text"] = entry.get("value")
    return payload


def _scan_string_handler(ctx: ToolContext,
                         *,
                         text: str,
                         encoding: str = "both",
                         case_sensitive: bool = False,
                         module_name: str | None = None,
                         start_address: int | str | None = None,
                         end_address: int | str | None = None,
                         limit: int = DEFAULT_RESULT_LIMIT,
                         protection_flags: str = DEFAULT_PROTECTION_FLAGS,
                         session_id: str | None = None) -> dict[str, Any]:
    normalized_encoding = encoding.strip().casefold()
    if normalized_encoding not in {"ascii", "ansi", "utf16", "utf-16", "wide", "unicode", "both"}:
        raise ToolUsageError(
            "encoding must be one of: ascii, utf16, wide, unicode, both",
            code="invalid_scan_encoding",
            hint="Use ascii for single-byte strings, utf16 for wide strings, or both to search both encodings.",
            details={"encoding": encoding},
            example='ce.scan_string(text="inventory", encoding="both", module_name="Minecraft.Windows.exe")',
        )

    limit = _normalize_limit(limit)
    encodings: list[str]
    if normalized_encoding in {"ascii", "ansi"}:
        encodings = ["ascii"]
    elif normalized_encoding in {"utf16", "utf-16", "wide", "unicode"}:
        encodings = ["utf16"]
    else:
        encodings = ["ascii", "utf16"]

    payloads = [
        _scan_string_single(
            ctx,
            text=text,
            encoding=current,
            case_sensitive=case_sensitive,
            module_name=module_name,
            start_address=start_address,
            end_address=end_address,
            limit=limit,
            protection_flags=protection_flags,
            session_id=session_id,
        )
        for current in encodings
    ]
    merged = _merge_string_scan_results(payloads, limit)
    merged["text"] = text
    merged["encodings"] = encodings
    return merged


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
        ToolSpec(
            name="ce.scan_first_ex",
            description="Start a CE memscan first-scan using simple named parameters instead of a raw options object.",
            parameters=(
                SCAN_SESSION_PARAMETER,
                SCAN_OPTION_PARAMETER,
                VALUE_TYPE_PARAMETER,
                VALUE_PARAMETER,
                VALUE2_PARAMETER,
                MODULE_NAME_PARAMETER,
                START_ADDRESS_PARAMETER,
                END_ADDRESS_PARAMETER,
                ROUNDING_PARAMETER,
                PROTECTION_PARAMETER,
                ALIGNMENT_TYPE_PARAMETER,
                ALIGNMENT_PARAMETER,
                HEX_INPUT_PARAMETER,
                NOT_BINARY_PARAMETER,
                UNICODE_PARAMETER,
                CASE_PARAMETER,
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda **kwargs: _first_scan_handler(ctx, **kwargs),
        ),
        ToolSpec(
            name="ce.scan_next_ex",
            description="Start a CE memscan next-scan using simple named parameters instead of a raw options object.",
            parameters=(
                SCAN_SESSION_PARAMETER,
                SCAN_OPTION_PARAMETER,
                VALUE_PARAMETER,
                VALUE2_PARAMETER,
                ROUNDING_PARAMETER,
                HEX_INPUT_PARAMETER,
                NOT_BINARY_PARAMETER,
                UNICODE_PARAMETER,
                CASE_PARAMETER,
                PERCENTAGE_PARAMETER,
                SAVED_RESULT_PARAMETER,
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda **kwargs: _next_scan_handler(ctx, **kwargs),
        ),
        ToolSpec(
            name="ce.scan_collect",
            description="Attach a FoundList to an existing CE memscan session and return normalized results.",
            parameters=(
                SCAN_SESSION_PARAMETER,
                LIMIT_PARAMETER,
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda **kwargs: _scan_collect_handler(ctx, **kwargs),
        ),
        ToolSpec(
            name="ce.scan_once",
            description="Run a full CE first-scan, wait for completion, collect results, and destroy the temporary scan session.",
            parameters=(
                SCAN_OPTION_PARAMETER,
                VALUE_TYPE_PARAMETER,
                VALUE_PARAMETER,
                VALUE2_PARAMETER,
                MODULE_NAME_PARAMETER,
                START_ADDRESS_PARAMETER,
                END_ADDRESS_PARAMETER,
                LIMIT_PARAMETER,
                ROUNDING_PARAMETER,
                PROTECTION_PARAMETER,
                ALIGNMENT_TYPE_PARAMETER,
                ALIGNMENT_PARAMETER,
                HEX_INPUT_PARAMETER,
                NOT_BINARY_PARAMETER,
                UNICODE_PARAMETER,
                CASE_PARAMETER,
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda **kwargs: _scan_once_handler(ctx, **kwargs),
        ),
        ToolSpec(
            name="ce.scan_value",
            description="Convenience wrapper for CE memscan exact/between/changed-style value scans across numeric, pointer, bytearray, binary, or string value types.",
            parameters=(
                VALUE_PARAMETER,
                VALUE_TYPE_PARAMETER,
                SCAN_OPTION_PARAMETER,
                VALUE2_PARAMETER,
                MODULE_NAME_PARAMETER,
                START_ADDRESS_PARAMETER,
                END_ADDRESS_PARAMETER,
                LIMIT_PARAMETER,
                ROUNDING_PARAMETER,
                PROTECTION_PARAMETER,
                ALIGNMENT_TYPE_PARAMETER,
                ALIGNMENT_PARAMETER,
                HEX_INPUT_PARAMETER,
                NOT_BINARY_PARAMETER,
                UNICODE_PARAMETER,
                CASE_PARAMETER,
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda **kwargs: _scan_value_handler(ctx, **kwargs),
        ),
        ToolSpec(
            name="ce.scan_string",
            description="Search for a text string using CE memscan semantics, with ASCII, UTF-16, or both encodings.",
            parameters=(
                ParameterSpec("text", str),
                ParameterSpec("encoding", str, "both"),
                ParameterSpec("case_sensitive", bool, False),
                MODULE_NAME_PARAMETER,
                START_ADDRESS_PARAMETER,
                END_ADDRESS_PARAMETER,
                LIMIT_PARAMETER,
                PROTECTION_PARAMETER,
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda **kwargs: _scan_string_handler(ctx, **kwargs),
        ),
    ]
    register_specs(server, specs)
