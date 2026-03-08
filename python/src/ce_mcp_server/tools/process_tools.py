from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, register_specs
from ..runtime.process_runtime import PROCESS_RUNTIME
from .common import lua_function_tool, runtime_tool


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
        runtime_tool(ctx, name="ce.get_ce_version", description="Return the Cheat Engine version number.", runtime=PROCESS_RUNTIME, function_name="get_ce_version", parameters=()),
        runtime_tool(ctx, name="ce.get_cheat_engine_dir", description="Return the Cheat Engine installation directory.", runtime=PROCESS_RUNTIME, function_name="get_cheat_engine_dir", parameters=()),
        runtime_tool(ctx, name="ce.get_process_id_from_name", description="Resolve a process image name to a PID.", runtime=PROCESS_RUNTIME, function_name="get_process_id_from_name", parameters=(ParameterSpec("process_name", str),)),
        runtime_tool(ctx, name="ce.get_foreground_process", description="Return the PID of the current foreground window process.", runtime=PROCESS_RUNTIME, function_name="get_foreground_process", parameters=()),
        runtime_tool(ctx, name="ce.get_cpu_count", description="Return the host CPU count seen by Cheat Engine.", runtime=PROCESS_RUNTIME, function_name="get_cpu_count", parameters=()),
        runtime_tool(ctx, name="ce.target_is_64bit", description="Return whether the attached target process is 64-bit.", runtime=PROCESS_RUNTIME, function_name="target_is_64bit", parameters=()),
        runtime_tool(ctx, name="ce.get_window_list", description="Return the window list as Cheat Engine sees it.", runtime=PROCESS_RUNTIME, function_name="get_window_list", parameters=()),
        runtime_tool(ctx, name="ce.get_common_module_list", description="Return the common module list Cheat Engine tracks.", runtime=PROCESS_RUNTIME, function_name="get_common_module_list", parameters=()),
        runtime_tool(ctx, name="ce.get_auto_attach_list", description="Return Cheat Engine's auto-attach target list.", runtime=PROCESS_RUNTIME, function_name="get_auto_attach_list", parameters=()),
        runtime_tool(ctx, name="ce.set_auto_attach_list", description="Replace Cheat Engine's auto-attach target list.", runtime=PROCESS_RUNTIME, function_name="set_auto_attach_list", parameters=(ParameterSpec("entries", list[str]),)),
        runtime_tool(ctx, name="ce.clear_auto_attach_list", description="Clear Cheat Engine's auto-attach target list.", runtime=PROCESS_RUNTIME, function_name="clear_auto_attach_list", parameters=()),
        runtime_tool(ctx, name="ce.add_auto_attach_target", description="Add one entry to Cheat Engine's auto-attach target list.", runtime=PROCESS_RUNTIME, function_name="add_auto_attach_target", parameters=(ParameterSpec("entry", str),)),
        runtime_tool(ctx, name="ce.remove_auto_attach_target", description="Remove one entry from Cheat Engine's auto-attach target list.", runtime=PROCESS_RUNTIME, function_name="remove_auto_attach_target", parameters=(ParameterSpec("entry", str),)),
        lua_function_tool(ctx, name="ce.pause_process", description="Pause the currently attached process via Cheat Engine.", function_name="pause", parameters=()),
        lua_function_tool(ctx, name="ce.unpause_process", description="Resume the currently attached process via Cheat Engine.", function_name="unpause", parameters=()),
    ]
    register_specs(server, specs)
