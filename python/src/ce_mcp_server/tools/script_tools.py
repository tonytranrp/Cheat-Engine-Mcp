from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, ToolSpec, register_specs
from ..runtime.lua_runtime import LUA_RUNTIME


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
        ToolSpec(
            name="ce.lua_eval",
            description="Evaluate a Lua expression inside Cheat Engine and JSON-encode the result.",
            parameters=(ParameterSpec("script", str), ParameterSpec("session_id", str | None, None)),
            handler=lambda script, session_id=None: ctx.lua_eval(script, session_id=session_id),
        ),
        ToolSpec(
            name="ce.lua_exec",
            description="Execute a Lua chunk inside Cheat Engine and JSON-encode its returned value.",
            parameters=(ParameterSpec("script", str), ParameterSpec("session_id", str | None, None)),
            handler=lambda script, session_id=None: ctx.lua_exec(script, session_id=session_id),
        ),
        ToolSpec(
            name="ce.auto_assemble",
            description="Run a raw Cheat Engine Auto Assemble script.",
            parameters=(ParameterSpec("script", str), ParameterSpec("session_id", str | None, None)),
            handler=lambda script, session_id=None: ctx.auto_assemble(script, session_id=session_id),
        ),
        ToolSpec(
            name="ce.lua_call",
            description="Call a global Cheat Engine Lua function by name with positional arguments.",
            parameters=(
                ParameterSpec("function_name", str),
                ParameterSpec("args", list[object], []),
                ParameterSpec("result_field", str, "value"),
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda function_name, args=None, result_field="value", session_id=None: ctx.call_lua_function(function_name, args=args or [], session_id=session_id, result_field=result_field),
        ),
        ToolSpec(
            name="ce.lua_get_global",
            description="Read a global Lua value from Cheat Engine by variable name.",
            parameters=(ParameterSpec("variable_name", str), ParameterSpec("session_id", str | None, None)),
            handler=lambda variable_name, session_id=None: ctx.lua_exec(
                f"return {{name = {ctx.to_lua_literal(variable_name)}, value = rawget(_G, {ctx.to_lua_literal(variable_name)})}}",
                session_id=session_id,
            ),
        ),
        ToolSpec(
            name="ce.lua_set_global",
            description="Set a global Lua variable inside Cheat Engine.",
            parameters=(ParameterSpec("variable_name", str), ParameterSpec("value", object), ParameterSpec("session_id", str | None, None)),
            handler=lambda variable_name, value, session_id=None: ctx.lua_exec(
                f"rawset(_G, {ctx.to_lua_literal(variable_name)}, {ctx.to_lua_literal(value)})\nreturn {{name = {ctx.to_lua_literal(variable_name)}, value = rawget(_G, {ctx.to_lua_literal(variable_name)})}}",
                session_id=session_id,
            ),
        ),
        ToolSpec(
            name="ce.run_script_file",
            description="Load a local Lua script file from disk and execute it inside Cheat Engine using loadfile.",
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
