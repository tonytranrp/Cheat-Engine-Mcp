from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, ToolSpec, register_specs
from .common import native_tool


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
        native_tool(ctx, name="ce.list_modules", description="List modules from the currently attached process.", bridge_tool="ce.list_modules", parameters=(ParameterSpec("limit", int, 256),)),
        native_tool(ctx, name="ce.list_modules_full", description="Return the full module list from the currently attached process.", bridge_tool="ce.list_modules_full"),
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
        ),
        native_tool(
            ctx,
            name="ce.resolve_symbol",
            description="Resolve a symbol to an address, or an address back to a symbol-like name.",
            bridge_tool="ce.resolve_symbol",
            parameters=(ParameterSpec("symbol", str | None, None), ParameterSpec("address", int | str | None, None)),
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
        ),
        native_tool(ctx, name="ce.read_memory", description="Read raw bytes from the currently attached process.", bridge_tool="ce.read_memory", parameters=(ParameterSpec("address", int | str), ParameterSpec("size", int))),
        native_tool(ctx, name="ce.write_memory", description="Write raw hex bytes into the currently attached process.", bridge_tool="ce.write_memory", parameters=(ParameterSpec("address", int | str), ParameterSpec("bytes_hex", str))),
        native_tool(ctx, name="ce.exported.list", description="List fields from Cheat Engine's copied ExportedFunctions block.", bridge_tool="ce.exported.list", parameters=(ParameterSpec("available_only", bool, False), ParameterSpec("limit", int, 159))),
        native_tool(ctx, name="ce.exported.get", description="Inspect a specific field from Cheat Engine's copied ExportedFunctions block.", bridge_tool="ce.exported.get", parameters=(ParameterSpec("field_name", str),)),
    ]

    register_specs(server, specs)
