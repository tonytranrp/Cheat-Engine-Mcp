from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, register_specs
from ..runtime.table_runtime import TABLE_RUNTIME
from .common import runtime_tool


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
        runtime_tool(ctx, name="ce.record_list", description="List cheat table records from the current address list.", runtime=TABLE_RUNTIME, function_name="list_records", parameters=(ParameterSpec("include_script", bool, False),)),
        runtime_tool(ctx, name="ce.record_get_by_id", description="Fetch one cheat table record by ID.", runtime=TABLE_RUNTIME, function_name="get_record_by_id", parameters=(ParameterSpec("record_id", int), ParameterSpec("include_script", bool, False))),
        runtime_tool(ctx, name="ce.record_get_by_description", description="Fetch one cheat table record by description.", runtime=TABLE_RUNTIME, function_name="get_record_by_description", parameters=(ParameterSpec("description", str), ParameterSpec("include_script", bool, False))),
        runtime_tool(ctx, name="ce.record_find_all_by_description", description="Find all cheat table records that share a description.", runtime=TABLE_RUNTIME, function_name="find_records_by_description", parameters=(ParameterSpec("description", str),)),
        runtime_tool(ctx, name="ce.record_create", description="Create a new top-level cheat table record.", runtime=TABLE_RUNTIME, function_name="create_record", parameters=(ParameterSpec("options", dict[str, object], {}),)),
        runtime_tool(ctx, name="ce.record_delete", description="Delete a cheat table record by ID.", runtime=TABLE_RUNTIME, function_name="delete_record", parameters=(ParameterSpec("record_id", int),)),
        runtime_tool(ctx, name="ce.record_set_description", description="Set a cheat table record description.", runtime=TABLE_RUNTIME, function_name="set_description", parameters=(ParameterSpec("record_id", int), ParameterSpec("description", str))),
        runtime_tool(ctx, name="ce.record_set_address", description="Set a cheat table record address expression.", runtime=TABLE_RUNTIME, function_name="set_address", parameters=(ParameterSpec("record_id", int), ParameterSpec("address", str))),
        runtime_tool(ctx, name="ce.record_set_type", description="Set a cheat table record value type.", runtime=TABLE_RUNTIME, function_name="set_type", parameters=(ParameterSpec("record_id", int), ParameterSpec("value_type", str | int))),
        runtime_tool(ctx, name="ce.record_set_value", description="Set a cheat table record value string.", runtime=TABLE_RUNTIME, function_name="set_value", parameters=(ParameterSpec("record_id", int), ParameterSpec("value", str | int | float))),
        runtime_tool(ctx, name="ce.record_set_active", description="Toggle a cheat table record active state.", runtime=TABLE_RUNTIME, function_name="set_active", parameters=(ParameterSpec("record_id", int), ParameterSpec("active", bool))),
        runtime_tool(ctx, name="ce.record_get_offsets", description="Return pointer offsets for a cheat table record.", runtime=TABLE_RUNTIME, function_name="get_offsets", parameters=(ParameterSpec("record_id", int),)),
        runtime_tool(ctx, name="ce.record_set_offsets", description="Replace pointer offsets on a cheat table record.", runtime=TABLE_RUNTIME, function_name="set_offsets", parameters=(ParameterSpec("record_id", int), ParameterSpec("offsets", list[int]))),
        runtime_tool(ctx, name="ce.record_get_script", description="Return the Auto Assemble script on a cheat table record.", runtime=TABLE_RUNTIME, function_name="get_script", parameters=(ParameterSpec("record_id", int),)),
        runtime_tool(ctx, name="ce.record_set_script", description="Set the Auto Assemble script on a cheat table record.", runtime=TABLE_RUNTIME, function_name="set_script", parameters=(ParameterSpec("record_id", int), ParameterSpec("script", str))),
    ]
    register_specs(server, specs)
