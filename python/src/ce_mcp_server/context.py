from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

from .bridge import BridgeError, CheatEngineBridge, NoSessionError


@dataclass(frozen=True, slots=True)
class RuntimeModule:
    name: str
    version: str
    script: str


CORE_RUNTIME = RuntimeModule(
    name="core",
    version="2026.03.08.1",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.core = root.core or {}
local M = root.core

local unpack_fn = table.unpack or unpack

function M.call_global(function_name, args, result_field)
  local normalized_name = tostring(function_name or '')
  local fn = rawget(_G, normalized_name)
  if type(fn) ~= 'function' then
    error('missing_lua_function:' .. normalized_name)
  end

  local normalized_result_field = tostring(result_field or 'value')
  return {
    [normalized_result_field] = fn(unpack_fn(args or {}))
  }
end

function M.call_runtime(module_name, function_name, args)
  local normalized_module = tostring(module_name or '')
  local normalized_function = tostring(function_name or '')

  local module = root[normalized_module]
  if type(module) ~= 'table' then
    error('ce_mcp_runtime_module_missing:' .. normalized_module)
  end

  local fn = module[normalized_function]
  if type(fn) ~= 'function' then
    error('ce_mcp_runtime_function_missing:' .. normalized_module .. '.' .. normalized_function)
  end

  return fn(unpack_fn(args or {}))
end

_G.__ce_mcp_modules["core"] = "2026.03.08.1"
return {ok = true, module = "core", version = "2026.03.08.1"}
''',
)


class ToolContext:
    def __init__(self, bridge_getter: Callable[[], CheatEngineBridge]) -> None:
        self._bridge_getter = bridge_getter
        self._runtime_lock = threading.Lock()
        self._loaded_runtime_modules: dict[str, set[str]] = {}

    def get_bridge(self) -> CheatEngineBridge:
        return self._bridge_getter()

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.get_bridge().list_sessions()

    def resolve_session_id(self, session_id: str | None = None) -> str:
        if session_id:
            return session_id

        sessions = self.list_sessions()
        if not sessions:
            raise NoSessionError("no active Cheat Engine sessions are connected")
        return str(sessions[0]["session_id"])

    def invalidate_runtime_cache(self, session_id: str | None = None) -> None:
        with self._runtime_lock:
            if session_id is None:
                self._loaded_runtime_modules.clear()
            else:
                self._loaded_runtime_modules.pop(session_id, None)

    def native_call(self,
                    tool_name: str,
                    payload: dict[str, Any] | None = None,
                    session_id: str | None = None,
                    timeout_seconds: float = 30.0) -> dict[str, Any]:
        return self.get_bridge().call_tool(tool_name, payload=payload, session_id=session_id, timeout_seconds=timeout_seconds)

    def native_call_safe(self,
                         tool_name: str,
                         payload: dict[str, Any] | None = None,
                         session_id: str | None = None,
                         timeout_seconds: float = 30.0) -> dict[str, Any]:
        try:
            return self.native_call(tool_name, payload=payload, session_id=session_id, timeout_seconds=timeout_seconds)
        except BridgeError as exc:
            if session_id is not None:
                self.invalidate_runtime_cache(session_id)
            return {"ok": False, "error": str(exc)}

    def native_call_strict(self,
                           tool_name: str,
                           payload: dict[str, Any] | None = None,
                           session_id: str | None = None,
                           timeout_seconds: float = 30.0) -> dict[str, Any]:
        result = self.native_call(tool_name, payload=payload, session_id=session_id, timeout_seconds=timeout_seconds)
        if result.get("ok") is not True:
            raise BridgeError(str(result.get("error", f"{tool_name} failed")))
        return result

    def lua_eval(self,
                 script: str,
                 session_id: str | None = None,
                 timeout_seconds: float = 30.0) -> dict[str, Any]:
        return self.native_call_safe("ce.lua_eval", payload={"script": script}, session_id=session_id, timeout_seconds=timeout_seconds)

    def lua_exec(self,
                 script: str,
                 session_id: str | None = None,
                 timeout_seconds: float = 30.0) -> dict[str, Any]:
        return self.native_call_safe("ce.lua_exec", payload={"script": script}, session_id=session_id, timeout_seconds=timeout_seconds)

    def auto_assemble(self,
                      script: str,
                      session_id: str | None = None,
                      timeout_seconds: float = 30.0) -> dict[str, Any]:
        return self.native_call_safe("ce.auto_assemble", payload={"script": script}, session_id=session_id, timeout_seconds=timeout_seconds)

    def call_lua_function(self,
                          function_name: str,
                          args: list[Any] | tuple[Any, ...] | None = None,
                          session_id: str | None = None,
                          result_field: str = "value",
                          timeout_seconds: float = 30.0) -> dict[str, Any]:
        resolved_session = self.resolve_session_id(session_id)
        try:
            self.ensure_runtime_module(CORE_RUNTIME, resolved_session)
        except BridgeError as exc:
            return {"ok": False, "error": str(exc), "session_id": resolved_session}

        script = (
            f"return __ce_mcp.core.call_global("
            f"{self.to_lua_literal(function_name)}, "
            f"{self.to_lua_literal(list(args or []))}, "
            f"{self.to_lua_literal(result_field)})"
        )
        return self.lua_exec(script, session_id=resolved_session, timeout_seconds=timeout_seconds)

    def call_runtime_function(self,
                              runtime: RuntimeModule,
                              function_name: str,
                              args: list[Any] | tuple[Any, ...] | None = None,
                              session_id: str | None = None,
                              timeout_seconds: float = 30.0) -> dict[str, Any]:
        resolved_session = self.resolve_session_id(session_id)
        try:
            self.ensure_runtime_module(CORE_RUNTIME, resolved_session)
            if runtime.name != CORE_RUNTIME.name:
                self.ensure_runtime_module(runtime, resolved_session)
        except BridgeError as exc:
            return {"ok": False, "error": str(exc), "session_id": resolved_session}

        script = (
            f"return __ce_mcp.core.call_runtime("
            f"{self.to_lua_literal(runtime.name)}, "
            f"{self.to_lua_literal(function_name)}, "
            f"{self.to_lua_literal(list(args or []))})"
        )
        return self.lua_exec(script, session_id=resolved_session, timeout_seconds=timeout_seconds)

    def ensure_runtime_module(self, runtime: RuntimeModule, session_id: str) -> None:
        with self._runtime_lock:
            loaded = self._loaded_runtime_modules.setdefault(session_id, set())
            if runtime.name in loaded:
                return

        probe = self.native_call_strict(
            "ce.lua_exec",
            payload={
                "script": (
                    "local __mods = rawget(_G, '__ce_mcp_modules')\n"
                    f"return {{loaded = type(__mods) == 'table' and __mods[{self.to_lua_literal(runtime.name)}] == {self.to_lua_literal(runtime.version)}}}"
                )
            },
            session_id=session_id,
        )
        if probe.get("loaded") is True:
            with self._runtime_lock:
                self._loaded_runtime_modules.setdefault(session_id, set()).add(runtime.name)
            return

        self.native_call_strict("ce.lua_exec", payload={"script": runtime.script}, session_id=session_id, timeout_seconds=30.0)
        with self._runtime_lock:
            self._loaded_runtime_modules.setdefault(session_id, set()).add(runtime.name)

    def to_lua_literal(self, value: Any) -> str:
        if value is None:
            return "nil"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if value != value:
                raise ValueError("NaN is not supported in Lua literals")
            if value in (float("inf"), float("-inf")):
                raise ValueError("infinite floats are not supported in Lua literals")
            return repr(value)
        if isinstance(value, str):
            escaped = (
                value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t")
            )
            return f'"{escaped}"'
        if isinstance(value, (list, tuple)):
            return "{" + ", ".join(self.to_lua_literal(item) for item in value) + "}"
        if isinstance(value, dict):
            parts: list[str] = []
            for key, item in value.items():
                parts.append(f"[{self.to_lua_literal(key)}] = {self.to_lua_literal(item)}")
            return "{" + ", ".join(parts) + "}"
        raise TypeError(f"unsupported Lua literal type: {type(value)!r}")
