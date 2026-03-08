from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, ToolSpec, register_specs
from ..runtime.lua_runtime import LUA_RUNTIME
from .common import runtime_tool


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
        runtime_tool(
            ctx,
            name="ce.lua_get_package_paths",
            description="Return Lua package.path and package.cpath as seen inside Cheat Engine.",
            runtime=LUA_RUNTIME,
            function_name="get_package_paths",
            parameters=(),
        ),
        runtime_tool(
            ctx,
            name="ce.lua_add_package_path",
            description="Append or prepend one Lua package.path entry inside Cheat Engine.",
            runtime=LUA_RUNTIME,
            function_name="add_package_path",
            parameters=(ParameterSpec("path", str), ParameterSpec("prepend", bool, False)),
            arg_builder=lambda path, prepend=False: [str(Path(path)), prepend],
        ),
        runtime_tool(
            ctx,
            name="ce.lua_add_package_cpath",
            description="Append or prepend one Lua package.cpath entry inside Cheat Engine.",
            runtime=LUA_RUNTIME,
            function_name="add_package_cpath",
            parameters=(ParameterSpec("path", str), ParameterSpec("prepend", bool, False)),
            arg_builder=lambda path, prepend=False: [str(Path(path)), prepend],
        ),
        runtime_tool(
            ctx,
            name="ce.lua_add_library_root",
            description="Register a library root so external Lua modules under root/?.lua, root/?/init.lua, and root/?.dll can be required from Cheat Engine.",
            runtime=LUA_RUNTIME,
            function_name="add_library_root",
            parameters=(ParameterSpec("path", str), ParameterSpec("prepend", bool, False)),
            arg_builder=lambda path, prepend=False: [str(Path(path)), prepend],
        ),
        runtime_tool(
            ctx,
            name="ce.lua_require_module",
            description="Require a Lua module inside Cheat Engine, optionally forcing a reload through package.loaded.",
            runtime=LUA_RUNTIME,
            function_name="require_module",
            parameters=(ParameterSpec("module_name", str), ParameterSpec("force_reload", bool, False)),
            arg_builder=lambda module_name, force_reload=False: [module_name, force_reload],
        ),
        runtime_tool(
            ctx,
            name="ce.lua_unload_module",
            description="Drop a Lua module from package.loaded inside Cheat Engine so the next require reloads it.",
            runtime=LUA_RUNTIME,
            function_name="unload_module",
            parameters=(ParameterSpec("module_name", str),),
            arg_builder=lambda module_name: [module_name],
        ),
        runtime_tool(
            ctx,
            name="ce.lua_call_module_function",
            description="Require a Lua module table and call one exported function with positional arguments inside Cheat Engine.",
            runtime=LUA_RUNTIME,
            function_name="call_module_function",
            parameters=(
                ParameterSpec("module_name", str),
                ParameterSpec("function_name", str),
                ParameterSpec("args", list[object], []),
                ParameterSpec("force_reload", bool, False),
            ),
            arg_builder=lambda module_name, function_name, args=None, force_reload=False: [module_name, function_name, args or [], force_reload],
        ),
        ToolSpec(
            name="ce.lua_run_file",
            description="Execute a Lua file directly from disk inside Cheat Engine using loadfile, preserving external require() semantics.",
            parameters=(ParameterSpec("path", str), ParameterSpec("session_id", str | None, None)),
            handler=lambda path, session_id=None: ctx.call_runtime_function(
                LUA_RUNTIME,
                "run_file",
                args=[str(Path(path))],
                session_id=session_id,
            ),
        ),
    ]

    register_specs(server, specs)
