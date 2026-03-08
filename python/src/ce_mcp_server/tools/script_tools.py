from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, ToolSpec, register_specs
from ..runtime.lua_runtime import LUA_RUNTIME


def _wrap_lua_with_globals(ctx: ToolContext, script: str, globals_map: dict[str, object] | None, *, as_expression: bool) -> str:
    globals_literal = ctx.to_lua_literal(globals_map or {})
    if as_expression:
        body = f"return ({script})"
    else:
        body = script

    return (
        f"local __ce_mcp_globals = {globals_literal}\n"
        "local __ce_mcp_saved = {}\n"
        "for __k, __v in pairs(__ce_mcp_globals) do\n"
        "  __ce_mcp_saved[__k] = rawget(_G, __k)\n"
        "  rawset(_G, __k, __v)\n"
        "end\n"
        "local function __ce_mcp_restore()\n"
        "  for __k in pairs(__ce_mcp_globals) do\n"
        "    rawset(_G, __k, __ce_mcp_saved[__k])\n"
        "  end\n"
        "end\n"
        "local __ok, __result = xpcall(function()\n"
        f"{body}\n"
        "end, function(__err)\n"
        "  return __err\n"
        "end)\n"
        "__ce_mcp_restore()\n"
        "if not __ok then error(__result) end\n"
        "return __result"
    )


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
            name="ce.lua_eval_with_globals",
            description="Evaluate a Lua expression inside Cheat Engine with temporary globals injected for this call only.",
            parameters=(
                ParameterSpec("script", str),
                ParameterSpec("globals", dict[str, object], {}),
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda script, globals=None, session_id=None: ctx.lua_exec(
                _wrap_lua_with_globals(ctx, script, globals or {}, as_expression=True),
                session_id=session_id,
            ),
        ),
        ToolSpec(
            name="ce.lua_exec_with_globals",
            description="Execute a Lua chunk inside Cheat Engine with temporary globals injected for this call only.",
            parameters=(
                ParameterSpec("script", str),
                ParameterSpec("globals", dict[str, object], {}),
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda script, globals=None, session_id=None: ctx.lua_exec(
                _wrap_lua_with_globals(ctx, script, globals or {}, as_expression=False),
                session_id=session_id,
            ),
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
