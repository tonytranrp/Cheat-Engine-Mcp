from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, register_specs
from .common import lua_function_tool


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
        lua_function_tool(ctx, name="ce.aob_scan_unique", description="Run Cheat Engine's AOBScanUnique helper and return one matching address.", function_name="AOBScanUnique", parameters=(ParameterSpec("pattern", str),), result_field="address"),
        lua_function_tool(ctx, name="ce.aob_scan_module_unique", description="Run Cheat Engine's AOBScanModuleUnique helper on a module and return one matching address.", function_name="AOBScanModuleUnique", parameters=(ParameterSpec("module_name", str), ParameterSpec("pattern", str)), result_field="address"),
    ]
    register_specs(server, specs)
