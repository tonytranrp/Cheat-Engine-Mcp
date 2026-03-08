from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, register_specs
from ..runtime.scan_runtime import SCAN_RUNTIME
from .common import runtime_tool

SCAN_OPTIONS_PARAMETER = ParameterSpec("options", dict[str, object], {})
SCAN_SESSION_PARAMETER = ParameterSpec("scan_session_id", str)


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
        runtime_tool(ctx, name="ce.scan_list_enums", description="Return CE scan enum names for scan options, value types, rounding types, and alignment types.", runtime=SCAN_RUNTIME, function_name="list_enums", parameters=()),
        runtime_tool(ctx, name="ce.scan_create_session", description="Create a persistent Cheat Engine memscan session.", runtime=SCAN_RUNTIME, function_name="create_session", parameters=()),
        runtime_tool(ctx, name="ce.scan_destroy_session", description="Destroy a persistent Cheat Engine memscan session.", runtime=SCAN_RUNTIME, function_name="destroy_session", parameters=(SCAN_SESSION_PARAMETER,)),
        runtime_tool(ctx, name="ce.scan_destroy_all_sessions", description="Destroy all persistent Cheat Engine memscan sessions.", runtime=SCAN_RUNTIME, function_name="destroy_all_sessions", parameters=()),
        runtime_tool(ctx, name="ce.scan_list_sessions", description="List active persistent Cheat Engine memscan sessions.", runtime=SCAN_RUNTIME, function_name="list_sessions", parameters=()),
        runtime_tool(ctx, name="ce.scan_new", description="Reset an existing Cheat Engine memscan session for a new scan.", runtime=SCAN_RUNTIME, function_name="new_scan", parameters=(SCAN_SESSION_PARAMETER,)),
        runtime_tool(ctx, name="ce.scan_first", description="Start a first scan using Cheat Engine scan semantics.", runtime=SCAN_RUNTIME, function_name="first_scan", parameters=(SCAN_SESSION_PARAMETER, SCAN_OPTIONS_PARAMETER)),
        runtime_tool(ctx, name="ce.scan_next", description="Start a next scan using Cheat Engine scan semantics.", runtime=SCAN_RUNTIME, function_name="next_scan", parameters=(SCAN_SESSION_PARAMETER, SCAN_OPTIONS_PARAMETER)),
        runtime_tool(ctx, name="ce.scan_wait", description="Wait for an active scan to finish.", runtime=SCAN_RUNTIME, function_name="wait", parameters=(SCAN_SESSION_PARAMETER,)),
        runtime_tool(ctx, name="ce.scan_get_progress", description="Get scan progress for a persistent memscan session.", runtime=SCAN_RUNTIME, function_name="get_progress", parameters=(SCAN_SESSION_PARAMETER,)),
        runtime_tool(ctx, name="ce.scan_attach_foundlist", description="Attach a FoundList to a memscan session so results can be read.", runtime=SCAN_RUNTIME, function_name="attach_foundlist", parameters=(SCAN_SESSION_PARAMETER,)),
        runtime_tool(ctx, name="ce.scan_detach_foundlist", description="Detach and destroy the FoundList for a memscan session.", runtime=SCAN_RUNTIME, function_name="detach_foundlist", parameters=(SCAN_SESSION_PARAMETER,)),
        runtime_tool(ctx, name="ce.scan_get_result_count", description="Return the current result count for a memscan session.", runtime=SCAN_RUNTIME, function_name="get_result_count", parameters=(SCAN_SESSION_PARAMETER,)),
        runtime_tool(ctx, name="ce.scan_get_results", description="Return FoundList results from a memscan session.", runtime=SCAN_RUNTIME, function_name="get_results", parameters=(SCAN_SESSION_PARAMETER, ParameterSpec("limit", int, 128))),
        runtime_tool(ctx, name="ce.scan_save_results", description="Save the current memscan results under a CE saved-result name.", runtime=SCAN_RUNTIME, function_name="save_results", parameters=(SCAN_SESSION_PARAMETER, ParameterSpec("saved_result_name", str))),
        runtime_tool(ctx, name="ce.scan_set_only_one_result", description="Toggle the OnlyOneResult mode on a memscan session.", runtime=SCAN_RUNTIME, function_name="set_only_one_result", parameters=(SCAN_SESSION_PARAMETER, ParameterSpec("enabled", bool, True))),
        runtime_tool(ctx, name="ce.scan_get_only_result", description="Return the single result address from a memscan session in OnlyOneResult mode.", runtime=SCAN_RUNTIME, function_name="get_only_result", parameters=(SCAN_SESSION_PARAMETER,)),
    ]
    register_specs(server, specs)
