from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from typing import Any, get_args, get_origin


class FakeBridge:
    def status(self) -> dict[str, Any]:
        return {
            "host": "127.0.0.1",
            "port": 5556,
            "session_count": 1,
            "sessions": [{"session_id": "ce-test"}],
        }

    def resolve_session_id(self, session_id: str | None = None) -> str:
        return session_id or "ce-test"


class FakeToolContext:
    def __init__(self) -> None:
        self.bridge = FakeBridge()
        self.native_calls: list[tuple[str, dict[str, Any] | None, str | None, float]] = []
        self.runtime_calls: list[tuple[str, str, list[Any] | tuple[Any, ...] | None, str | None, float]] = []
        self.lua_calls: list[tuple[str, str, list[Any] | tuple[Any, ...] | None, str | None, str, float]] = []
        self.script_calls: list[tuple[str, str, str | None, float]] = []

    def get_bridge(self) -> FakeBridge:
        return self.bridge

    def list_sessions(self) -> list[dict[str, Any]]:
        return [
            {
                "session_id": "ce-test",
                "peer": "127.0.0.1:5556",
                "connected_at": 0.0,
                "plugin": "MCP Bridge Plugin",
                "plugin_id": 1,
                "sdk_version": 6,
                "ce_process_id": 1234,
                "tools": [],
            }
        ]

    def resolve_session_id(self, session_id: str | None = None) -> str:
        return session_id or "ce-test"

    def invalidate_runtime_cache(self, session_id: str | None = None) -> None:
        return None

    def native_call_safe(self,
                         tool_name: str,
                         payload: dict[str, Any] | None = None,
                         session_id: str | None = None,
                         timeout_seconds: float = 30.0) -> dict[str, Any]:
        self.native_calls.append((tool_name, payload, session_id, timeout_seconds))
        if tool_name == "ce.exported.list":
            fields = [
                {"name": "ShowMessage", "type_name": "CEP_SHOWMESSAGE", "kind": "typed_function"},
                {"name": "GetLuaState", "type_name": "CEP_GETLUASTATE", "kind": "typed_function"},
                {"name": "mainform", "type_name": "PVOID", "kind": "pointer"},
            ]
            return {"ok": True, "fields": fields}
        if tool_name == "ce.exported.get":
            field_name = (payload or {}).get("field_name", "ShowMessage")
            return {"ok": True, "field": {"name": field_name, "type_name": "PVOID", "kind": "pointer"}}
        if tool_name == "ce.list_modules_full":
            return {
                "ok": True,
                "process_id": 4321,
                "total_count": 1,
                "returned_count": 1,
                "truncated": False,
                "modules": [
                    {
                        "base_address": 0x140000000,
                        "size": 0x100000,
                        "module_name": "game.exe",
                        "module_path": r"C:\Game\game.exe",
                    }
                ],
            }
        if tool_name == "ce.list_modules":
            return self.native_call_safe("ce.list_modules_full", payload=payload, session_id=session_id, timeout_seconds=timeout_seconds)
        if tool_name == "ce.get_attached_process":
            return {
                "ok": True,
                "attached": True,
                "process_id": 4321,
                "process_name": "game.exe",
                "image_path": r"C:\Game\game.exe",
            }
        if tool_name == "ce.list_tools":
            return {"ok": True, "items": ["ce.get_attached_process", "ce.read_memory"]}
        if tool_name == "ce.get_process_list":
            return {
                "ok": True,
                "total_count": 1,
                "returned_count": 1,
                "truncated": False,
                "processes": [{"process_id": 4321, "parent_process_id": 4, "attached": True, "process_name": "game.exe"}],
            }
        if tool_name == "ce.read_memory":
            return {"ok": True, "address": 0x140000000, "bytes_read": 16, "bytes_hex": "4D5A9000"}
        if tool_name == "ce.write_memory":
            return {"ok": True, "address": 0x140000000, "bytes_written": 1, "bytes_hex": "90"}
        if tool_name == "ce.query_memory_map":
            raw_start_address = (payload or {}).get("start_address", 0x140000000) or 0x140000000
            raw_end_address = (payload or {}).get("end_address", 0x140010000) or 0x140010000
            if isinstance(raw_start_address, str):
                start_address = 0x140000000 if raw_start_address == "game.exe+0" else 0x140000100
            else:
                start_address = int(raw_start_address)
            if isinstance(raw_end_address, str):
                end_address = 0x140001000 if raw_end_address == "game.exe+0x1000" else 0x140010000
            else:
                end_address = int(raw_end_address)
            return {
                "ok": True,
                "process_id": 4321,
                "start_address": start_address,
                "end_address": end_address,
                "include_free": bool((payload or {}).get("include_free", False)),
                "total_count": 3,
                "returned_count": 3,
                "truncated": False,
                "timed_out": False,
                "regions": [
                    {
                        "base_address": 0x140000000,
                        "allocation_base": 0x140000000,
                        "region_size": 0x1000,
                        "state": 0x1000,
                        "protect": 0x02,
                        "allocation_protect": 0x02,
                        "type": 0x20000,
                        "readable": True,
                        "writable": False,
                        "executable": False,
                        "guarded": False,
                    },
                    {
                        "base_address": 0x140001000,
                        "allocation_base": 0x140000000,
                        "region_size": 0x3000,
                        "state": 0x1000,
                        "protect": 0x20,
                        "allocation_protect": 0x20,
                        "type": 0x1000000,
                        "readable": True,
                        "writable": False,
                        "executable": True,
                        "guarded": False,
                    },
                    {
                        "base_address": 0x140004000,
                        "allocation_base": 0x140000000,
                        "region_size": 0x2000,
                        "state": 0x1000,
                        "protect": 0x04,
                        "allocation_protect": 0x04,
                        "type": 0x20000,
                        "readable": True,
                        "writable": True,
                        "executable": False,
                        "guarded": False,
                    },
                ],
            }
        if tool_name == "ce.aob_scan":
            pattern = str((payload or {}).get("pattern", ""))
            matches = [0x140000200] if pattern else []
            return {
                "ok": True,
                "matches": matches,
                "returned_count": len(matches),
                "truncated": False,
                "session_id": session_id or "ce-test",
            }
        if tool_name == "ce.resolve_symbol":
            if payload and "symbol" in payload:
                return {"ok": True, "symbol": str(payload["symbol"]), "address": 0x140000000, "resolved_via": "ce_symbol"}
            if payload and "address" in payload:
                raw_address = payload["address"]
                if isinstance(raw_address, str):
                    resolved_address = 0x140000000 if raw_address == "game.exe+0" else 0x140000100
                else:
                    resolved_address = int(raw_address)
                return {"ok": True, "symbol": "game.exe+0", "address": resolved_address, "resolved_via": "module_offset"}
        return {"ok": True, "tool_name": tool_name, "payload": payload or {}, "session_id": session_id or "ce-test"}

    def native_call(self,
                    tool_name: str,
                    payload: dict[str, Any] | None = None,
                    session_id: str | None = None,
                    timeout_seconds: float = 30.0) -> dict[str, Any]:
        return self.native_call_safe(tool_name, payload=payload, session_id=session_id, timeout_seconds=timeout_seconds)

    def native_call_strict(self,
                           tool_name: str,
                           payload: dict[str, Any] | None = None,
                           session_id: str | None = None,
                           timeout_seconds: float = 30.0) -> dict[str, Any]:
        result = self.native_call_safe(tool_name, payload=payload, session_id=session_id, timeout_seconds=timeout_seconds)
        if result.get("ok") is not True:
            raise RuntimeError(str(result.get("error", f"{tool_name} failed")))
        return result

    def lua_eval(self, script: str, session_id: str | None = None, timeout_seconds: float = 30.0) -> dict[str, Any]:
        self.script_calls.append(("lua_eval", script, session_id, timeout_seconds))
        return {"ok": True, "value": script, "session_id": session_id or "ce-test"}

    def lua_exec(self, script: str, session_id: str | None = None, timeout_seconds: float = 30.0) -> dict[str, Any]:
        self.script_calls.append(("lua_exec", script, session_id, timeout_seconds))
        return {"ok": True, "value": script, "session_id": session_id or "ce-test"}

    def auto_assemble(self, script: str, session_id: str | None = None, timeout_seconds: float = 30.0) -> dict[str, Any]:
        self.script_calls.append(("auto_assemble", script, session_id, timeout_seconds))
        return {"ok": True, "success": True, "script": script, "session_id": session_id or "ce-test"}

    def call_lua_function(self,
                          function_name: str,
                          args: list[Any] | tuple[Any, ...] | None = None,
                          session_id: str | None = None,
                          result_field: str = "value",
                          timeout_seconds: float = 30.0) -> dict[str, Any]:
        self.lua_calls.append((function_name, "function", args, session_id, result_field, timeout_seconds))
        if function_name == "getAddressSafe":
            expr = (args or ["game.exe+0"])[0]
            resolved = 0x140000000 if expr == "game.exe+0" else 0x140000100
            return {"ok": True, "address": resolved}
        if function_name in {"pause", "unpause", "registerSymbol", "unregisterSymbol"}:
            return {"ok": True, result_field: True}
        return {"ok": True, result_field: f"{function_name}-result"}

    def call_runtime_function(self,
                              runtime,
                              function_name: str,
                              args: list[Any] | tuple[Any, ...] | None = None,
                              session_id: str | None = None,
                              timeout_seconds: float = 30.0) -> dict[str, Any]:
        runtime_name = getattr(runtime, "name", "runtime")
        self.runtime_calls.append((runtime_name, function_name, args, session_id, timeout_seconds))

        if runtime_name == "scan":
            if function_name == "list_enums":
                return {"ok": True, "scan_options": {"exact": 0}, "var_types": {"dword": 2}}
            if function_name == "create_session":
                return {"ok": True, "session_id": "scan-1"}
            if function_name == "list_sessions":
                return {
                    "ok": True,
                    "sessions": [{
                        "session_id": "scan-1",
                        "has_foundlist": False,
                        "only_one_result": False,
                        "state": "completed",
                        "scan_in_progress": False,
                        "has_completed_scan": True,
                        "last_scan_kind": "first",
                        "last_result_count": 2,
                    }],
                }
            if function_name == "get_session_state":
                return {
                    "ok": True,
                    "session_id": "scan-1",
                    "state": "completed",
                    "scan_in_progress": False,
                    "has_completed_scan": True,
                    "last_scan_kind": "first",
                    "last_result_count": 2,
                }
            if function_name == "new_scan":
                return {"ok": True, "session_id": "scan-1", "reset": True}
            if function_name in {"first_scan", "next_scan"}:
                return {"ok": True, "session_id": "scan-1", "started": True}
            if function_name == "wait":
                return {"ok": True, "session_id": "scan-1", "completed": True}
            if function_name == "get_progress":
                return {"ok": True, "session_id": "scan-1", "total": 100, "current": 75}
            if function_name == "attach_foundlist":
                return {"ok": True, "session_id": "scan-1", "attached": True, "count": 2}
            if function_name == "detach_foundlist":
                return {"ok": True, "session_id": "scan-1", "attached": False}
            if function_name == "get_result_count":
                return {"ok": True, "session_id": "scan-1", "count": 2}
            if function_name == "get_results":
                return {
                    "ok": True,
                    "session_id": "scan-1",
                    "count": 2,
                    "returned_count": 2,
                    "truncated": False,
                    "results": [
                        {"index": 0, "address": "4096", "value": "inventory"},
                        {"index": 1, "address": "8192", "value": "slot"},
                    ],
                }
            if function_name == "save_results":
                return {"ok": True, "session_id": "scan-1", "saved_result_name": "saved"}
            if function_name == "set_only_one_result":
                return {"ok": True, "session_id": "scan-1", "only_one_result": True}
            if function_name == "get_only_result":
                return {"ok": True, "session_id": "scan-1", "address": "4096"}
            if function_name in {"destroy_session", "destroy_all_sessions"}:
                return {"ok": True, "destroyed": True}

        if runtime_name == "table":
            return {"ok": True, "runtime": runtime_name, "function": function_name, "record": {"id": 1}, "count": 1}

        if runtime_name == "pointer":
            return {"ok": True, "address": 0x140000100, "kind": function_name, "value": 123}

        if runtime_name == "process":
            if function_name == "get_window_list":
                return {"ok": True, "windows": []}
            if function_name == "get_common_module_list":
                return {"ok": True, "modules": ["game.exe"]}
            if function_name == "get_auto_attach_list":
                return {"ok": True, "entries": ["game.exe"]}
            if function_name == "set_auto_attach_list":
                return {"ok": True, "entries": list((args or [[]])[0])}
            if function_name in {"clear_auto_attach_list", "add_auto_attach_target", "remove_auto_attach_target"}:
                return {"ok": True, "entries": ["game.exe"]}
            if function_name == "get_process_id_from_name":
                return {"ok": True, "process_name": "game.exe", "process_id": 4321}
            if function_name == "target_is_64bit":
                return {"ok": True, "is64": True}
            if function_name == "get_ce_version":
                return {"ok": True, "version": 7.5}
            if function_name == "get_cheat_engine_dir":
                return {"ok": True, "path": r"C:\Cheat Engine"}
            if function_name == "get_foreground_process":
                return {"ok": True, "process_id": 4321}
            if function_name == "get_cpu_count":
                return {"ok": True, "count": 16}

        if runtime_name == "lua":
            if function_name == "get_package_paths":
                return {"ok": True, "path": "./?.lua", "cpath": "./?.dll", "path_entries": ["./?.lua"], "cpath_entries": ["./?.dll"]}
            if function_name == "get_environment":
                return {
                    "ok": True,
                    "lua_version": "Lua 5.x",
                    "path": "./?.lua",
                    "cpath": "./?.dll",
                    "path_entries": ["./?.lua"],
                    "cpath_entries": ["./?.dll"],
                    "loaded_modules": ["sample_module"],
                    "preloaded_modules": ["sample_preload"],
                    "searcher_count": 4,
                    "managed_path_entries": ["./?.lua"],
                    "managed_cpath_entries": ["./?.dll"],
                    "configured_library_roots": ["C:/tmp"],
                }
            if function_name in {"add_package_path", "add_package_cpath", "add_library_root", "remove_package_path", "remove_package_cpath", "remove_library_root"}:
                return {
                    "ok": True,
                    "changed": True,
                    "path": "./?.lua",
                    "cpath": "./?.dll",
                    "path_entries": ["./?.lua"],
                    "cpath_entries": ["./?.dll"],
                    "configured_library_roots": ["C:/tmp"],
                    "managed_path_entries": ["./?.lua"],
                    "managed_cpath_entries": ["./?.dll"],
                }
            if function_name == "configure_environment":
                return {
                    "ok": True,
                    "lua_version": "Lua 5.x",
                    "path": "./?.lua",
                    "cpath": "./?.dll",
                    "path_entries": ["./?.lua"],
                    "cpath_entries": ["./?.dll"],
                    "loaded_modules": ["sample_module"],
                    "preloaded_modules": ["sample_preload"],
                    "searcher_count": 4,
                    "configured_library_roots": ["C:/tmp"],
                    "managed_path_entries": ["./?.lua"],
                    "managed_cpath_entries": ["./?.dll"],
                    "prepend": True,
                    "reset_managed": True,
                }
            if function_name == "reset_environment":
                return {
                    "ok": True,
                    "lua_version": "Lua 5.x",
                    "path": "",
                    "cpath": "",
                    "path_entries": [],
                    "cpath_entries": [],
                    "loaded_modules": ["sample_module"],
                    "preloaded_modules": ["sample_preload"],
                    "searcher_count": 4,
                    "configured_library_roots": [],
                    "managed_path_entries": [],
                    "managed_cpath_entries": [],
                    "reset": True,
                }
            if function_name == "require_module":
                return {"ok": True, "module_name": "sample_module", "loaded": True, "value_type": "table", "value": {"answer": 42}}
            if function_name == "unload_module":
                return {"ok": True, "module_name": "sample_module", "loaded": False}
            if function_name == "list_loaded_modules":
                return {"ok": True, "count": 1, "modules": ["sample_module"]}
            if function_name == "list_preloaded_modules":
                return {"ok": True, "count": 1, "modules": ["sample_preload"]}
            if function_name in {"preload_module_source", "preload_module_file"}:
                return {"ok": True, "module_name": "sample_preload", "preloaded": True, "force_reload": False}
            if function_name == "unpreload_module":
                return {"ok": True, "module_name": "sample_preload", "preloaded": False}
            if function_name == "call_module_function":
                return {"ok": True, "module_name": "sample_module", "function_name": "answer", "value": 42}
            if function_name == "run_file":
                return {"ok": True, "path": str((args or ["script.lua"])[0]), "result": {"value": 1}}

        if runtime_name == "structure":
            if function_name == "list_structures":
                return {"ok": True, "count": 1, "structures": [{"index": 0, "name": "Player", "size": 16, "count": 1, "global": True}]}
            if function_name == "get_structure":
                return {"ok": True, "structure": {"index": 0, "name": "Player", "size": 16, "count": 1, "global": True, "elements": []}}
            if function_name in {"create_structure", "define_structure", "auto_guess", "fill_from_dotnet"}:
                return {"ok": True, "structure": {"index": 0, "name": "Player", "size": 16, "count": 1, "global": True, "elements": []}}
            if function_name == "read_structure":
                return {
                    "ok": True,
                    "address": 0x140000000,
                    "address_hex": "0x140000000",
                    "structure": {"index": 0, "name": "Player", "size": 16, "count": 1, "global": True},
                    "fields": [{"name": "health", "offset": 0, "address": 0x140000000, "value": 100, "value_kind": "integer"}],
                }
            if function_name == "add_element":
                return {
                    "ok": True,
                    "structure": {"index": 0, "name": "Player", "size": 16, "count": 1, "global": True, "elements": []},
                    "element": {"offset": 0, "name": "health", "vartype": 2, "bytesize": 4},
                }
            if function_name == "delete_structure":
                return {"ok": True, "deleted": True, "name": "Player", "index": 0}

        if runtime_name == "dissect":
            if function_name == "get_references":
                return {"ok": True, "address": 0x140000000, "count": 1, "returned_count": 1, "truncated": False, "references": [{"address": 0x140000120}]}
            if function_name == "get_referenced_strings":
                return {"ok": True, "count": 1, "returned_count": 1, "truncated": False, "strings": ["inventory"]}
            if function_name == "get_referenced_functions":
                return {"ok": True, "count": 1, "returned_count": 1, "truncated": False, "functions": ["game.exe+1234"]}
            return {"ok": True, "dissected": True}

        if runtime_name == "debug":
            if function_name == "status":
                return {"ok": True, "is_debugging": False, "can_break": False, "is_broken": False, "breakpoint_count": 0, "breakpoints": [], "watches": []}
            if function_name == "start":
                return {"ok": True, "is_debugging": True, "breakpoint_count": 0, "breakpoints": [], "watches": []}
            if function_name == "continue_execution":
                return {"ok": True, "continued": True, "continue_option": "run", "is_broken": False}
            if function_name == "list_breakpoints":
                return {"ok": True, "count": 0, "breakpoints": []}
            if function_name == "watch_start":
                return {"ok": True, "watch": {"watch_id": "watch-1", "address": 0x140000000, "active": True, "hit_count": 0}, "status": {"is_debugging": True}}
            if function_name == "watch_get_hits":
                return {"ok": True, "watch_id": "watch-1", "active": True, "hit_count": 1, "returned_count": 1, "truncated": False, "hits": [{"instruction_pointer": 0x140010000}]}
            if function_name == "watch_stop":
                return {"ok": True, "stopped": True, "watch_id": "watch-1", "hit_count": 1}
            if function_name == "watch_stop_all":
                return {"ok": True, "count": 1, "stopped": [{"watch_id": "watch-1", "address": 0x140000000, "hit_count": 1}]}

        return {"ok": True, "runtime": runtime_name, "function": function_name, "args": list(args or [])}

    def to_lua_literal(self, value: Any) -> str:
        if value is None:
            return "nil"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        if isinstance(value, list):
            return "{" + ", ".join(self.to_lua_literal(item) for item in value) + "}"
        if isinstance(value, dict):
            return "{" + ", ".join(f"[{self.to_lua_literal(key)}] = {self.to_lua_literal(item)}" for key, item in value.items()) + "}"
        return self.to_lua_literal(str(value))


class FakeServer:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *, name: str, description: str):
        def decorator(function):
            self.tools[name] = function
            return function
        return decorator


def build_sample_args(tool_name: str, signature: inspect.Signature) -> dict[str, Any]:
    temp_dir = Path(tempfile.gettempdir())
    script_path = temp_dir / "ce_mcp_test_script.lua"
    script_path.write_text("return {value = 1}\n", encoding="utf-8")
    export_path = temp_dir / "ce_mcp_export.bin"

    overrides: dict[str, Any] = {
        "session_id": "ce-test",
        "scan_session_id": "scan-1",
        "watch_id": "watch-1",
        "record_id": 1,
        "process_id": 4321,
        "process_name": "game.exe",
        "module_name": "game.exe",
        "field_name": "GetLuaState",
        "field_names": ["GetLuaState", "ShowMessage"],
        "query": "Lua",
        "limit": 2,
        "count": 2,
        "size": 4,
        "max_results": 2,
        "max_length": 32,
        "address": "game.exe+0",
        "base_address": "game.exe+0",
        "start_address": "game.exe+0",
        "end_address": "game.exe+0x100",
        "expression": "game.exe+0",
        "offsets": [16, 32],
        "value": 123,
        "value2": 456,
        "values": [1, 2, 3],
        "bytes_hex": "90",
        "bytes": [1, 2, 3],
        "wide": False,
        "path": str(export_path),
        "name": "Player",
        "entry": "game.exe",
        "entries": ["game.exe"],
        "description": "health",
        "script": "return { value = 1 }",
        "function_name": "readInteger",
        "args": [123],
        "result_field": "value",
        "variable_name": "ce_mcp_test",
        "text": "inventory",
        "encoding": "ascii",
        "case_sensitive": False,
        "value_type": "dword",
        "scan_option": "exact",
        "rounding_type": "rounded",
        "protection_flags": "*X*C*W",
        "alignment_type": "not_aligned",
        "alignment_param": "1",
        "saved_result_name": "saved",
        "timeout_seconds": 60.0,
        "include_script": False,
        "active": True,
        "enabled": True,
        "donotsave": False,
        "change_name": True,
        "add_global": True,
        "destroy": True,
        "debugger_interface": 0,
        "continue_option": "run",
        "method": "debug_register",
        "auto_continue": True,
        "globals": {"player_name": "inventory", "limit_value": 7},
        "options": {
            "description": "health",
            "address": "game.exe+0",
            "type": "dword",
        },
        "elements": [
            {"offset": 0, "name": "health", "vartype": "dword", "bytesize": 4},
            {"offset": 4, "name": "armor", "vartype": "dword", "bytesize": 4},
        ],
        "records": [
            {"description": "health", "address": "game.exe+0", "type": "dword", "value": 100},
            {"description": "armor", "address": "game.exe+4", "type": "4 Bytes", "value": 50},
        ],
        "library_roots": [str(temp_dir)],
        "package_paths": [str(temp_dir / "?.lua")],
        "package_cpaths": [str(temp_dir / "?.dll")],
    }

    if tool_name == "ce.run_script_file":
        overrides["path"] = str(script_path)
    if tool_name == "ce.lua_run_file":
        overrides["path"] = str(script_path)
    if tool_name == "ce.lua_add_library_root":
        overrides["path"] = str(temp_dir)
    if tool_name == "ce.lua_remove_library_root":
        overrides["path"] = str(temp_dir)
    if tool_name == "ce.lua_configure_environment":
        overrides["library_roots"] = [str(temp_dir)]
        overrides["package_paths"] = [str(temp_dir / "?.lua")]
        overrides["package_cpaths"] = [str(temp_dir / "?.dll")]
        overrides["prepend"] = True
        overrides["reset_managed"] = True
    if tool_name in {"ce.lua_preload_file", "ce.run_script_file", "ce.lua_run_file"}:
        overrides["path"] = str(script_path)
    if tool_name in {"ce.lua_require_module", "ce.lua_unload_module", "ce.lua_call_module_function"}:
        overrides["module_name"] = "sample_module"
    if tool_name in {"ce.lua_preload_module", "ce.lua_unpreload_module", "ce.lua_preload_file"}:
        overrides["module_name"] = "sample_preload"
    if tool_name == "ce.lua_call_module_function":
        overrides["function_name"] = "answer"
        overrides["args"] = []
    if tool_name == "ce.structure_add_element":
        overrides["options"] = {"offset": 0, "name": "health", "vartype": "dword", "bytesize": 4}
    if tool_name == "ce.structure_define":
        overrides["elements"] = [{"offset": 0, "name": "health", "vartype": "dword", "bytesize": 4}]
    if tool_name == "ce.structure_read":
        overrides["name"] = "Player"
        overrides["address"] = "game.exe+0"
        overrides["max_depth"] = 1
        overrides["include_raw"] = True
    if tool_name == "ce.record_create":
        overrides["options"] = {"description": "health", "address": "game.exe+0", "type": "dword", "value": 100}
    if tool_name == "ce.record_create_group":
        overrides["description"] = "Player"
        overrides["records"] = [
            {"description": "health", "address": "game.exe+0", "type": "dword", "value": 100},
            {"description": "armor", "address": "game.exe+4", "type": "4 Bytes", "value": 50},
        ]
        overrides["options"] = {"active": False}
    if tool_name == "ce.record_create_many":
        overrides["records"] = [
            {"description": "health", "address": "game.exe+0", "type": "dword", "value": 100},
            {"description": "armor", "address": "game.exe+4", "type": "4 Bytes", "value": 50},
        ]
    if tool_name in {"ce.scan_first", "ce.scan_next"}:
        overrides["options"] = {"scan_option": "exact", "value_type": "dword", "input1": "100"}
    if tool_name == "ce.scan_string":
        overrides["encoding"] = "both"
        overrides["start_address"] = None
        overrides["end_address"] = None
    if tool_name in {"ce.aob_scan", "ce.aob_scan_unique"}:
        overrides["start_address"] = None
        overrides["end_address"] = None
    if tool_name in {"ce.scan_first_ex", "ce.scan_once", "ce.scan_value"}:
        overrides["start_address"] = None
        overrides["end_address"] = None
    if tool_name.startswith("ce.debug_watch_") and tool_name.endswith("_start"):
        overrides["address"] = "game.exe+0"

    args: dict[str, Any] = {}
    for parameter_name, parameter in signature.parameters.items():
        if parameter_name in overrides:
            args[parameter_name] = overrides[parameter_name]
            continue

        default = parameter.default
        if default is not inspect.Signature.empty:
            args[parameter_name] = default
            continue

        args[parameter_name] = sample_value_for_annotation(parameter.annotation)
    return args


def sample_value_for_annotation(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is None:
        if annotation is inspect.Signature.empty:
            return "sample"
        if annotation is str:
            return "sample"
        if annotation is int:
            return 1
        if annotation is float:
            return 1.0
        if annotation is bool:
            return True
        if annotation is object:
            return 1
        return "sample"

    if origin is list:
        args = get_args(annotation)
        item_annotation = args[0] if args else str
        return [sample_value_for_annotation(item_annotation)]

    if origin is dict:
        return {}

    if origin is tuple:
        args = get_args(annotation)
        return tuple(sample_value_for_annotation(arg) for arg in args)

    if origin is type(None):
        return None

    union_args = [arg for arg in get_args(annotation) if arg is not type(None)]
    if union_args:
        return sample_value_for_annotation(union_args[0])

    return "sample"
