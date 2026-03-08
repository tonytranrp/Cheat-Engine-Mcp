from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, register_specs
from ..runtime.debug_runtime import DEBUG_RUNTIME
from .common import runtime_tool


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
        runtime_tool(
            ctx,
            name="ce.debug_status",
            description="Return Cheat Engine debugger state, breakpoint list, and active CE MCP watch sessions.",
            runtime=DEBUG_RUNTIME,
            function_name="status",
            parameters=(),
        ),
        runtime_tool(
            ctx,
            name="ce.debug_start",
            description="Start Cheat Engine debugging on the attached process using the requested debugger interface.",
            runtime=DEBUG_RUNTIME,
            function_name="start",
            parameters=(ParameterSpec("debugger_interface", int, 0),),
        ),
        runtime_tool(
            ctx,
            name="ce.debug_continue",
            description="Continue from the current breakpoint using run, step_into, or step_over.",
            runtime=DEBUG_RUNTIME,
            function_name="continue_execution",
            parameters=(ParameterSpec("continue_option", str, "run"),),
        ),
        runtime_tool(
            ctx,
            name="ce.debug_list_breakpoints",
            description="List Cheat Engine breakpoints currently registered in the debugger.",
            runtime=DEBUG_RUNTIME,
            function_name="list_breakpoints",
            parameters=(),
        ),
        runtime_tool(
            ctx,
            name="ce.debug_watch_accesses_start",
            description="Start a watch session equivalent to Cheat Engine's 'find out what accesses this address'.",
            runtime=DEBUG_RUNTIME,
            function_name="watch_start",
            parameters=(
                ParameterSpec("address", int | str),
                ParameterSpec("size", int, 1),
                ParameterSpec("method", str | int | None, None),
                ParameterSpec("max_hits", int, 32),
                ParameterSpec("auto_continue", bool, True),
                ParameterSpec("debugger_interface", int, 0),
            ),
            arg_builder=lambda address, size=1, method=None, max_hits=32, auto_continue=True, debugger_interface=0: [
                address,
                size,
                "access",
                method,
                max_hits,
                auto_continue,
                debugger_interface,
            ],
            timeout_seconds=120.0,
        ),
        runtime_tool(
            ctx,
            name="ce.debug_watch_writes_start",
            description="Start a watch session equivalent to Cheat Engine's 'find out what writes to this address'.",
            runtime=DEBUG_RUNTIME,
            function_name="watch_start",
            parameters=(
                ParameterSpec("address", int | str),
                ParameterSpec("size", int, 1),
                ParameterSpec("method", str | int | None, None),
                ParameterSpec("max_hits", int, 32),
                ParameterSpec("auto_continue", bool, True),
                ParameterSpec("debugger_interface", int, 0),
            ),
            arg_builder=lambda address, size=1, method=None, max_hits=32, auto_continue=True, debugger_interface=0: [
                address,
                size,
                "write",
                method,
                max_hits,
                auto_continue,
                debugger_interface,
            ],
            timeout_seconds=120.0,
        ),
        runtime_tool(
            ctx,
            name="ce.debug_watch_execute_start",
            description="Start an execution-breakpoint watch session on an address.",
            runtime=DEBUG_RUNTIME,
            function_name="watch_start",
            parameters=(
                ParameterSpec("address", int | str),
                ParameterSpec("size", int, 1),
                ParameterSpec("method", str | int | None, None),
                ParameterSpec("max_hits", int, 32),
                ParameterSpec("auto_continue", bool, True),
                ParameterSpec("debugger_interface", int, 0),
            ),
            arg_builder=lambda address, size=1, method=None, max_hits=32, auto_continue=True, debugger_interface=0: [
                address,
                size,
                "execute",
                method,
                max_hits,
                auto_continue,
                debugger_interface,
            ],
            timeout_seconds=120.0,
        ),
        runtime_tool(
            ctx,
            name="ce.debug_watch_get_hits",
            description="Return recorded hits from a CE MCP debugger watch session.",
            runtime=DEBUG_RUNTIME,
            function_name="watch_get_hits",
            parameters=(ParameterSpec("watch_id", str), ParameterSpec("limit", int, 128)),
            timeout_seconds=30.0,
        ),
        runtime_tool(
            ctx,
            name="ce.debug_watch_stop",
            description="Stop one CE MCP debugger watch session and remove its breakpoint.",
            runtime=DEBUG_RUNTIME,
            function_name="watch_stop",
            parameters=(ParameterSpec("watch_id", str),),
            timeout_seconds=30.0,
        ),
        runtime_tool(
            ctx,
            name="ce.debug_watch_stop_all",
            description="Stop all CE MCP debugger watch sessions and remove their breakpoints.",
            runtime=DEBUG_RUNTIME,
            function_name="watch_stop_all",
            parameters=(),
            timeout_seconds=30.0,
        ),
    ]
    register_specs(server, specs)
