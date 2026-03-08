from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, register_specs
from ..runtime.table_runtime import TABLE_RUNTIME
from .common import runtime_tool


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
        runtime_tool(ctx, name="ce.table_record_count", description="Return the number of records in the current cheat table.", runtime=TABLE_RUNTIME, function_name="table_record_count", parameters=()),
        runtime_tool(ctx, name="ce.table_refresh", description="Refresh the Cheat Engine address list UI state.", runtime=TABLE_RUNTIME, function_name="table_refresh", parameters=()),
        runtime_tool(ctx, name="ce.table_rebuild_description_cache", description="Rebuild the address-list description cache.", runtime=TABLE_RUNTIME, function_name="table_rebuild_description_cache", parameters=()),
        runtime_tool(ctx, name="ce.table_disable_all_without_execute", description="Disable all active records without executing scripts.", runtime=TABLE_RUNTIME, function_name="table_disable_all_without_execute", parameters=()),
        runtime_tool(ctx, name="ce.table_load", description="Load a cheat table from disk.", runtime=TABLE_RUNTIME, function_name="table_load", parameters=(ParameterSpec("path", str),)),
        runtime_tool(ctx, name="ce.table_save", description="Save the current cheat table to disk.", runtime=TABLE_RUNTIME, function_name="table_save", parameters=(ParameterSpec("path", str),)),
        runtime_tool(ctx, name="ce.table_create_file", description="Create a named table file inside the current cheat table.", runtime=TABLE_RUNTIME, function_name="table_create_file", parameters=(ParameterSpec("name", str),)),
        runtime_tool(ctx, name="ce.table_find_file", description="Find a named table file inside the current cheat table.", runtime=TABLE_RUNTIME, function_name="table_find_file", parameters=(ParameterSpec("name", str),)),
        runtime_tool(ctx, name="ce.table_export_file", description="Export a named table file to disk.", runtime=TABLE_RUNTIME, function_name="table_export_file", parameters=(ParameterSpec("name", str), ParameterSpec("path", str))),
        runtime_tool(ctx, name="ce.table_get_selected_record", description="Return the currently selected cheat table record.", runtime=TABLE_RUNTIME, function_name="get_selected_record", parameters=(ParameterSpec("include_script", bool, False),)),
        runtime_tool(ctx, name="ce.table_set_selected_record", description="Select a cheat table record by ID.", runtime=TABLE_RUNTIME, function_name="set_selected_record", parameters=(ParameterSpec("record_id", int),)),
    ]
    register_specs(server, specs)
