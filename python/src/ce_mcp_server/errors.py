from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .bridge import BridgeError, NoSessionError, SessionDisconnectedError, ToolTimeoutError


@dataclass(slots=True)
class McpToolError(Exception):
    message: str
    code: str = "tool_error"
    category: str = "usage"
    hint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    next_steps: list[str] = field(default_factory=list)
    required_order: list[str] = field(default_factory=list)
    example: str | None = None
    risk: str | None = None

    def __post_init__(self) -> None:
        super().__init__(self.message)


class ToolUsageError(McpToolError):
    def __init__(self,
                 message: str,
                 *,
                 code: str = "invalid_usage",
                 hint: str | None = None,
                 details: dict[str, Any] | None = None,
                 next_steps: list[str] | None = None,
                 required_order: list[str] | None = None,
                 example: str | None = None,
                 risk: str | None = None) -> None:
        super().__init__(
            message=message,
            code=code,
            category="usage",
            hint=hint,
            details=details or {},
            next_steps=next_steps or [],
            required_order=required_order or [],
            example=example,
            risk=risk,
        )


class ToolStateError(McpToolError):
    def __init__(self,
                 message: str,
                 *,
                 code: str = "invalid_state",
                 hint: str | None = None,
                 details: dict[str, Any] | None = None,
                 next_steps: list[str] | None = None,
                 required_order: list[str] | None = None,
                 example: str | None = None,
                 risk: str | None = None) -> None:
        super().__init__(
            message=message,
            code=code,
            category="state",
            hint=hint,
            details=details or {},
            next_steps=next_steps or [],
            required_order=required_order or [],
            example=example,
            risk=risk,
        )


def error_payload(tool_name: str, exc: Exception) -> dict[str, Any]:
    if isinstance(exc, McpToolError):
        return _payload_from_mcp_error(tool_name, exc)

    if isinstance(exc, NoSessionError):
        return _payload_from_mcp_error(
            tool_name,
            ToolStateError(
                str(exc),
                code="no_session",
                hint="Start Cheat Engine with the CE MCP loader enabled, then retry after the bridge reconnects.",
                next_steps=[
                    "Launch Cheat Engine with the CE MCP loader plugin enabled.",
                    "Wait for a live session to appear in ce.bridge_status or ce.list_sessions.",
                    "Retry the original tool call.",
                ],
            ),
        )

    if isinstance(exc, ToolTimeoutError):
        return _payload_from_mcp_error(
            tool_name,
            ToolStateError(
                str(exc),
                code="tool_timeout",
                hint="The target operation did not finish before the current tool timeout. Narrow the scope or use a staged call order.",
                next_steps=[
                    "Reduce the scan/module/range size.",
                    "Prefer module_name or explicit address bounds over whole-process scans.",
                    "Retry after the current long-running operation finishes.",
                ],
            ),
        )

    if isinstance(exc, SessionDisconnectedError):
        return _payload_from_mcp_error(
            tool_name,
            ToolStateError(
                str(exc),
                code="session_disconnected",
                hint="The live Cheat Engine bridge session dropped during the request.",
                next_steps=[
                    "Check ce.bridge_status or ce.list_sessions for a reconnect.",
                    "If the session does not return, restart Cheat Engine.",
                    "Retry the tool after the bridge reconnects.",
                ],
            ),
        )

    if isinstance(exc, BridgeError):
        return _payload_from_mcp_error(
            tool_name,
            ToolStateError(
                str(exc),
                code="bridge_error",
                hint="The CE bridge rejected or lost the request. Check the live session and retry.",
            ),
        )

    return _payload_from_mcp_error(tool_name, _annotate_generic_error(tool_name, exc))


def normalize_tool_result(tool_name: str, result: Any) -> Any:
    if not isinstance(result, dict):
        return result

    if result.get("ok") is not False or "error" not in result:
        return result

    if result.get("error_code") and result.get("error_category"):
        return result

    annotated = _annotate_message(tool_name, str(result.get("error", "tool_error")))
    payload = _payload_from_mcp_error(tool_name, annotated)
    normalized = dict(result)
    normalized.update(payload)
    return normalized


def _payload_from_mcp_error(tool_name: str, exc: McpToolError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": exc.message,
        "error_code": exc.code,
        "error_category": exc.category,
        "tool_name": tool_name,
    }
    if exc.hint:
        payload["hint"] = exc.hint
    if exc.details:
        payload["details"] = dict(exc.details)
    if exc.next_steps:
        payload["next_steps"] = list(exc.next_steps)
    if exc.required_order:
        payload["required_order"] = list(exc.required_order)
    if exc.example:
        payload["example"] = exc.example
    if exc.risk:
        payload["risk"] = exc.risk
    return payload


def _annotate_generic_error(tool_name: str, exc: Exception) -> McpToolError:
    return _annotate_message(tool_name, str(exc))


def _annotate_message(tool_name: str, message: str) -> McpToolError:
    scan_order = [
        "ce.scan_create_session",
        "ce.scan_new or ce.scan_first_ex",
        "ce.scan_wait",
        "ce.scan_collect or ce.scan_get_results",
        "ce.scan_next_ex for refinements",
    ]

    if message == "missing_process_selector":
        return ToolUsageError(
            "Attach requires either process_id or process_name.",
            code="missing_process_selector",
            hint="Pass exactly one process selector.",
            next_steps=[
                "Use ce.get_process_list to discover a PID.",
                "Call ce.attach_process(process_id=...) for exact targeting.",
                "Use process_name only when duplicates are acceptable.",
            ],
            example='ce.attach_process(process_id=1234)',
        )

    if message == "process_not_found":
        return ToolUsageError(
            "The requested process was not found.",
            code="process_not_found",
            hint="The process may not be running, or the name may not match the executable image name exactly.",
            next_steps=[
                "Use ce.get_process_list to confirm the current process list.",
                "Retry with process_id for an exact match.",
                "If the target restarted, refresh the PID and attach again.",
            ],
            example='ce.attach_process(process_name="Minecraft.Windows.exe")',
        )

    if tool_name in {"ce.scan_next", "ce.scan_next_ex"} and (
        "disconnected while waiting" in message or "timed out" in message
    ):
        return ToolStateError(
            "This follow-up scan was issued against a scan session that is not in a safe continuation state.",
            code="scan_session_order_invalid",
            hint="ce.scan_next / ce.scan_next_ex must follow a completed first scan on the same scan_session_id.",
            next_steps=[
                "Order: ce.scan_create_session -> ce.scan_new or ce.scan_first_ex -> ce.scan_wait.",
                "Ensure the first scan actually produced results before using changed/unchanged style next scans.",
                "Then change the target value and call ce.scan_next or ce.scan_next_ex.",
            ],
            required_order=scan_order,
            example='ce.scan_next_ex(scan_session_id="scan-1", scan_option="changed")',
            risk="Calling follow-up scans on an empty or unfinished session can destabilize the live CE scan state.",
        )

    if tool_name.startswith("ce.debug_watch_") and "debug_setBreakpoint_failed" in message:
        return ToolStateError(
            "Cheat Engine rejected the requested breakpoint/watch operation.",
            code="debug_breakpoint_rejected",
            hint="Access/write watches depend on debugger interface, target support, and address type.",
            next_steps=[
                "Call ce.debug_start first and confirm ce.debug_status reports debugging is active.",
                "Prefer debugger_interface=2 (VEH) or 1 (Windows) for user-mode targets.",
                "Use ce.debug_watch_execute_start as the baseline breakpoint path when data breakpoints are rejected.",
            ],
            required_order=[
                "ce.attach_process",
                "ce.debug_start",
                "ce.debug_status",
                "ce.debug_watch_execute_start or ce.debug_watch_accesses_start",
            ],
            example='ce.debug_watch_execute_start(address="game.exe+1234", debugger_interface=2)',
            risk="Data breakpoint support is target- and debugger-dependent; a rejected watch does not mean the whole debugger stack is unavailable.",
        )

    if tool_name in {"ce.structure_fill_from_dotnet"} and "structure_not_found" in message:
        return ToolUsageError(
            "The target structure does not exist yet.",
            code="structure_missing",
            hint="Create the structure first, then fill it from the .NET object address.",
            next_steps=[
                "Call ce.structure_create(name=...).",
                "Attach to the managed target process.",
                "Call ce.structure_fill_from_dotnet(address=..., name=...).",
            ],
            example='ce.structure_fill_from_dotnet(name="Player", address=140737488355328)',
        )

    if message.startswith("scan_session_not_found:"):
        scan_session_id = message.partition(":")[2] or "<unknown>"
        return ToolStateError(
            "The requested scan_session_id does not exist in the active Cheat Engine session.",
            code="scan_session_not_found",
            hint="Create a new scan session or reuse a live one returned by ce.scan_list_sessions.",
            details={"scan_session_id": scan_session_id},
            next_steps=[
                "Call ce.scan_create_session.",
                "Run ce.scan_first_ex or ce.scan_first on that scan_session_id.",
                "Reuse the same scan_session_id for wait/collect/next operations.",
            ],
            required_order=scan_order,
            example='ce.scan_create_session()',
        )

    if message.startswith("scan_sequence_error:"):
        reason = message.partition(":")[2]
        return _scan_sequence_error(reason)

    if message.startswith("invalid_enum:"):
        invalid_value = message.partition(":")[2]
        return ToolUsageError(
            "The requested Cheat Engine scan enum value is not valid.",
            code="invalid_scan_enum",
            hint="Use ce.scan_list_enums to discover the supported enum names for the current CE runtime.",
            details={"value": invalid_value},
            next_steps=[
                "Call ce.scan_list_enums.",
                "Pick a scan_option, value_type, rounding_type, or alignment_type from that result.",
                "Retry the scan with a valid enum name.",
            ],
            example='ce.scan_first_ex(scan_session_id="scan-1", scan_option="exact", value_type="dword", value=100)',
        )

    if message.startswith("invalid_breakpoint_trigger:"):
        invalid_value = message.partition(":")[2]
        return ToolUsageError(
            "The requested breakpoint trigger is not valid.",
            code="invalid_breakpoint_trigger",
            hint="Use one of: execute, access, write.",
            details={"value": invalid_value},
            next_steps=[
                "Use execute for instruction breakpoints.",
                "Use access or write only when the target/debugger supports data breakpoints.",
            ],
            example='ce.debug_watch_execute_start(address="game.exe+1234")',
        )

    if message.startswith("invalid_breakpoint_method:"):
        invalid_value = message.partition(":")[2]
        return ToolUsageError(
            "The requested breakpoint method is not valid.",
            code="invalid_breakpoint_method",
            hint="Use int3, debug_register, exception, or omit method for the CE default.",
            details={"value": invalid_value},
            next_steps=[
                "Use debugger_interface=2 with the default method first.",
                "Only force a breakpoint method when you know the target supports it.",
            ],
            example='ce.debug_watch_execute_start(address="game.exe+1234", method="int3")',
        )

    if message.startswith("invalid_continue_option:"):
        invalid_value = message.partition(":")[2]
        return ToolUsageError(
            "The requested debugger continue option is not valid.",
            code="invalid_continue_option",
            hint="Use run, step_into, or step_over.",
            details={"value": invalid_value},
            example='ce.debug_continue(continue_option="run")',
        )

    if message == "debug_address_not_found":
        return ToolUsageError(
            "Cheat Engine could not resolve the requested debug address.",
            code="debug_address_not_found",
            hint="Pass an integer address or a valid Cheat Engine symbol expression.",
            next_steps=[
                "Use ce.resolve_symbol to validate the symbol first.",
                "Prefer module+offset expressions such as game.exe+1234.",
                "Retry the watch or breakpoint operation after the address resolves cleanly.",
            ],
            example='ce.resolve_symbol(symbol="Minecraft.Windows.exe+1234")',
        )

    if message == "debugger_start_failed":
        return ToolStateError(
            "Cheat Engine failed to enter debugging mode for the attached target.",
            code="debugger_start_failed",
            hint="The target may not be attached, the debugger interface may be unsupported, or the process may reject the chosen method.",
            next_steps=[
                "Confirm ce.get_attached_process reports the intended target.",
                "Retry ce.debug_start with debugger_interface=2 first.",
                "If debugging still fails, try debugger_interface=1 or attach to a simpler user-mode target.",
            ],
            required_order=["ce.attach_process", "ce.debug_start", "ce.debug_status"],
            example='ce.debug_start(debugger_interface=2)',
        )

    if message.startswith("debug_watch_not_found:"):
        watch_id = message.partition(":")[2] or "<unknown>"
        return ToolStateError(
            "The requested debugger watch session does not exist anymore.",
            code="debug_watch_not_found",
            hint="The watch may have been stopped, cleared, or lost when the debugger reset.",
            details={"watch_id": watch_id},
            next_steps=[
                "Use ce.debug_status to inspect active watches.",
                "Create a new watch with ce.debug_watch_execute_start or ce.debug_watch_accesses_start.",
            ],
        )

    return ToolUsageError(message or f"{tool_name} failed")


def _scan_sequence_error(reason: str) -> McpToolError:
    common_order = [
        "ce.scan_create_session",
        "ce.scan_new or ce.scan_first_ex",
        "ce.scan_wait",
        "ce.scan_collect or ce.scan_get_results",
        "ce.scan_next_ex for refinements",
    ]

    if reason == "first_scan_required":
        return ToolStateError(
            "A follow-up scan requires a completed first scan on the same scan_session_id.",
            code="scan_first_scan_required",
            hint="You cannot call a next-scan until the session has completed an initial scan.",
            next_steps=[
                "Call ce.scan_first_ex or ce.scan_first on the same scan_session_id.",
                "Call ce.scan_wait and wait for completion.",
                "Then run ce.scan_next_ex or ce.scan_next.",
            ],
            required_order=common_order,
            example='ce.scan_first_ex(scan_session_id="scan-1", scan_option="exact", value_type="dword", value=100)',
            risk="Skipping the first scan leaves the session without a baseline result set to refine.",
        )

    if reason == "wait_required":
        return ToolStateError(
            "The scan session already has an active scan in progress.",
            code="scan_wait_required",
            hint="Wait for the current scan to finish before starting another scan phase.",
            next_steps=[
                "Call ce.scan_wait on the same scan_session_id.",
                "Optionally inspect ce.scan_get_progress while waiting.",
                "Retry the next operation after the scan completes.",
            ],
            required_order=common_order,
            example='ce.scan_wait(scan_session_id="scan-1")',
            risk="Issuing overlapping scan operations can invalidate results or destabilize the live CE scan session.",
        )

    if reason == "wait_required_before_results":
        return ToolStateError(
            "Result collection is not safe while the scan is still running.",
            code="scan_results_wait_required",
            hint="Wait for the scan to finish before attaching a FoundList or reading results.",
            next_steps=[
                "Call ce.scan_wait on the same scan_session_id.",
                "Then call ce.scan_collect, ce.scan_get_result_count, or ce.scan_get_results.",
            ],
            required_order=common_order,
            example='ce.scan_collect(scan_session_id="scan-1", limit=128)',
            risk="Reading FoundList results too early can return inconsistent state and may disconnect long-running scan sessions.",
        )

    if reason == "no_active_scan":
        return ToolStateError(
            "There is no active or completed scan on this session yet.",
            code="scan_no_active_scan",
            hint="The scan session must be initialized with a first scan before wait or refinement operations make sense.",
            next_steps=[
                "Call ce.scan_first_ex or ce.scan_first.",
                "Then call ce.scan_wait.",
            ],
            required_order=common_order,
        )

    return ToolStateError(
        "The scan session is not in a valid state for that operation.",
        code="scan_invalid_state",
        hint="Check the scan order and reuse the same scan_session_id for the whole workflow.",
        required_order=common_order,
    )
