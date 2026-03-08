from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ce_mcp_server.bridge import CheatEngineBridge
from ce_mcp_server.context import ToolContext
from ce_mcp_server.tools import register_all
from test_support import FakeServer


REPO_ROOT = Path(__file__).resolve().parents[1]
DOTNET_TARGET_PROJECT = REPO_ROOT / "tests" / "assets" / "dotnet_target" / "DotNetTarget.csproj"
DOTNET_TARGET_DLL = REPO_ROOT / "tests" / "assets" / "dotnet_target" / "bin" / "Release" / "net8.0" / "DotNetTarget.dll"


@dataclass(slots=True)
class DotNetTarget:
    process: subprocess.Popen[str]
    pid: int
    process_name: str
    address: int
    health_address: int
    speed_address: int
    coins_address: int

    @classmethod
    def build(cls) -> None:
        subprocess.run(
            ["dotnet", "build", str(DOTNET_TARGET_PROJECT), "-c", "Release"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    @classmethod
    def start(cls) -> "DotNetTarget":
        process = subprocess.Popen(
            ["dotnet", str(DOTNET_TARGET_DLL)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdout is not None
        line = process.stdout.readline().strip()
        if not line:
            stderr = ""
            if process.stderr is not None:
                stderr = process.stderr.read()
            process.terminate()
            raise RuntimeError(f"dotnet target did not emit startup payload: {stderr}")

        payload = json.loads(line)
        return cls(
            process=process,
            pid=int(payload["pid"]),
            process_name=str(payload["process_name"]),
            address=int(payload["address"]),
            health_address=int(payload["health_address"]),
            speed_address=int(payload["speed_address"]),
            coins_address=int(payload["coins_address"]),
        )

    def stop(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


@dataclass(slots=True)
class RemoteScratch:
    base: int
    size: int
    integer_address: int
    ascii_address: int
    wide_address: int
    bytes_address: int
    pointer_holder: int
    pointer_target: int
    scan_integer_address: int
    pattern_address: int
    pattern_hex: str


@dataclass(slots=True)
class LocalScratch:
    base: int
    size: int
    integer_address: int
    ascii_address: int
    wide_address: int
    bytes_address: int
    pointer_holder: int
    pointer_target: int


class LiveToolSuite:
    def __init__(self,
                 *,
                 host: str = "127.0.0.1",
                 port: int = 5556,
                 primary_process_name: str | None = None) -> None:
        self.host = host
        self.port = port
        self.primary_process_name = primary_process_name or os.environ.get("CE_MCP_PRIMARY_PROCESS", "Minecraft.Windows.exe")
        self.bridge = CheatEngineBridge(host=host, port=port)
        self.context = ToolContext(lambda: self.bridge)
        self.server = FakeServer()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="ce_mcp_live_"))
        self.session_id: str | None = None
        self.primary_process_id: int | None = None
        self.primary_module_name: str | None = None
        self.primary_module_base: int | None = None
        self.system_function_address: int | None = None
        self.remote_scratch: RemoteScratch | None = None
        self.local_scratch: LocalScratch | None = None
        self.dotnet_target: DotNetTarget | None = None
        self.dotnet_structure_name = "CE_MCP_DotNet_Live"
        self.structure_names: list[str] = []
        self.general_record_id: int | None = None
        self.script_record_id: int | None = None
        self.extra_record_ids: list[int] = []
        self.table_file_name = f"ce_mcp_live_payload_{self.temp_dir.name}"
        self.table_save_path = self.temp_dir / "live_table.ct"
        self.table_export_path = self.temp_dir / "payload.bin"
        self.dissect_path = self.temp_dir / "live_dissect.dct"
        self.lua_module_root = self.temp_dir / "lua_libs"
        self.lua_module_name = "ce_live_module"
        self.lua_script_path = self.temp_dir / "ce_live_script.lua"
        self.lua_preload_module_name = "ce_live_preload"
        self.lua_preload_file_module_name = "ce_live_preload_file"
        self.lua_preload_file_path = self.temp_dir / "ce_live_preload.lua"
        self.auto_attach_original: list[str] = []
        self.invoked: set[str] = set()

    def start(self) -> None:
        register_all(self.server, self.context)
        self.bridge.start()
        self.session_id = self._wait_for_session()
        self._attach_primary()
        self._discover_primary_module()
        self._snapshot_auto_attach_list()
        self._prepare_lua_files()
        self._prepare_remote_scratch()

    def stop(self) -> None:
        try:
            if self.session_id is not None:
                self._safe_call("ce.debug_watch_stop_all")
                self._safe_call("ce.scan_destroy_all_sessions")
                for record_id in reversed(self.extra_record_ids):
                    self._safe_call("ce.record_delete", record_id=record_id)
                if self.general_record_id is not None:
                    self._safe_call("ce.record_delete", record_id=self.general_record_id)
                if self.script_record_id is not None:
                    self._safe_call("ce.record_delete", record_id=self.script_record_id)
                for structure_name in list(self.structure_names):
                    self._safe_call("ce.structure_delete", name=structure_name, destroy=True)
                if self.remote_scratch is not None:
                    self._safe_call("ce.dealloc", address=self.remote_scratch.base, size=self.remote_scratch.size)
                if self.auto_attach_original:
                    self._safe_call("ce.set_auto_attach_list", entries=self.auto_attach_original)
                else:
                    self._safe_call("ce.clear_auto_attach_list")
                if self.primary_process_name:
                    self._safe_call("ce.attach_process", process_name=self.primary_process_name)
        finally:
            if self.dotnet_target is not None:
                self.dotnet_target.stop()
                self.dotnet_target = None
            self.bridge.stop()
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def run(self) -> dict[str, Any]:
        self.start()
        try:
            self._run_native_tools()
            self._refresh_session()
            self._run_exported_tools()
            self._run_address_tools()
            self._run_process_tools()
            self._refresh_session()
            self._run_pointer_tools()
            self._refresh_session()
            self._prepare_remote_scratch()
            self._run_memory_tools()
            self._refresh_session()
            self._run_script_tools()
            self._refresh_session()
            self._run_scan_tools()
            self._refresh_session()
            self._run_table_and_record_tools()
            self._refresh_session()
            self._run_structure_and_dissect_tools()
            self._refresh_session(attach_primary=False)
            self._run_debug_tools()
            self._assert_all_tools_invoked()
            return {
                "ok": True,
                "tool_count": len(self.server.tools),
                "invoked_count": len(self.invoked),
                "invoked_tools": sorted(self.invoked),
                "primary_process_id": self.primary_process_id,
                "primary_process_name": self.primary_process_name,
                "primary_module_name": self.primary_module_name,
                "primary_module_base": self.primary_module_base,
            }
        finally:
            self.stop()

    def _wait_for_session(self, timeout_seconds: float = 20.0) -> str:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            sessions = self.bridge.list_sessions()
            if sessions:
                return str(sessions[0]["session_id"])
            time.sleep(0.5)
        raise RuntimeError("no Cheat Engine bridge session connected")

    def _call(self, tool_name: str, /, **kwargs: Any) -> dict[str, Any]:
        function = self.server.tools[tool_name]
        signature = inspect.signature(function)
        if "session_id" in signature.parameters and "session_id" not in kwargs and self.session_id is not None:
            kwargs["session_id"] = self.session_id
        result = function(**kwargs)
        self.invoked.add(tool_name)
        if isinstance(result, dict) and result.get("ok") is False:
            raise AssertionError(f"{tool_name} failed: {json.dumps(result, indent=2)}")
        return result

    def _safe_call(self, tool_name: str, /, **kwargs: Any) -> dict[str, Any] | None:
        try:
            return self._call(tool_name, **kwargs)
        except Exception:
            return None

    def _attach_primary(self) -> None:
        attached = self._call("ce.attach_process", process_name=self.primary_process_name)
        self.primary_process_id = int(attached["process_id"])

    def _discover_primary_module(self) -> None:
        modules = self._call("ce.list_modules_full")
        for module in modules.get("modules", []):
            if str(module.get("module_name", "")).lower() == str(self.primary_process_name).lower():
                self.primary_module_name = str(module["module_name"])
                self.primary_module_base = int(module["base_address"])
                break
        if self.primary_module_name is None or self.primary_module_base is None:
            raise RuntimeError("failed to locate primary module")

        system_address = self._call("ce.get_address_safe", expression="kernel32.GetTickCount64")
        self.system_function_address = int(system_address["address"])

    def _snapshot_auto_attach_list(self) -> None:
        result = self._call("ce.get_auto_attach_list")
        self.auto_attach_original = list(result.get("entries", []))

    def _prepare_lua_files(self) -> None:
        self.lua_module_root.mkdir(parents=True, exist_ok=True)
        (self.lua_module_root / f"{self.lua_module_name}.lua").write_text(
            "local M = {}\n"
            "function M.answer()\n"
            "  return 42\n"
            "end\n"
            "function M.echo(value)\n"
            "  return value\n"
            "end\n"
            "return M\n",
            encoding="utf-8",
        )
        self.lua_script_path.write_text("return { value = 77, source = 'ce_live_script' }\n", encoding="utf-8")
        self.lua_preload_file_path.write_text(
            "local M = {}\n"
            "function M.answer()\n"
            "  return 84\n"
            "end\n"
            "return M\n",
            encoding="utf-8",
        )

    def _prepare_remote_scratch(self) -> None:
        if self.remote_scratch is not None:
            self._safe_call("ce.dealloc", address=self.remote_scratch.base, size=self.remote_scratch.size)
        remote_base = int(self.context.call_lua_function("allocateMemory", args=[0x2000], session_id=self.session_id, result_field="address")["address"])
        pattern_hex = "43 45 20 4D 43 50 20 4C 49 56 45 20 50 41 54 54 45 52 4E 20 30 31"
        pattern_bytes = [int(part, 16) for part in pattern_hex.split()]
        script = f"""
local base = {remote_base}
writeBytes(base + 0x010, 0x41)
writeSmallInteger(base + 0x020, 0x1234)
writeInteger(base + 0x030, 0x12345678)
writeQword(base + 0x040, 0x1122334455667788)
writePointer(base + 0x050, base + 0x200)
writeByte(base + 0x200, 0x5A)
writeSmallInteger(base + 0x210, 0x1357)
writeInteger(base + 0x220, 0x2468ACE0)
writeQword(base + 0x230, 0x0102030405060708)
writePointer(base + 0x240, base + 0x300)
writeFloat(base + 0x250, 3.25)
writeDouble(base + 0x260, 6.5)
writeString(base + 0x270, 'PointerChainLive')
writeBytes(base + 0x280, {{0xAA, 0xBB, 0xCC, 0xDD}})
writeString(base + 0x300, 'ce_mcp_inventory_ascii')
writeBytes(base + 0x400, {{0x63,0x00,0x65,0x00,0x5F,0x00,0x6D,0x00,0x63,0x00,0x70,0x00,0x5F,0x00,0x69,0x00,0x6E,0x00,0x76,0x00,0x65,0x00,0x6E,0x00,0x74,0x00,0x6F,0x00,0x72,0x00,0x79,0x00,0x5F,0x00,0x77,0x00,0x69,0x00,0x64,0x00,0x65,0x00,0x00,0x00}})
writeBytes(base + 0x500, {{0x10, 0x20, 0x30, 0x40}})
writeInteger(base + 0x600, 0x51525354)
writeBytes(base + 0x700, {self._lua_array(pattern_bytes)})
return {{ base = base }}
"""
        result = self.context.lua_exec(script, session_id=self.session_id, timeout_seconds=30.0)
        if result.get("ok") is False:
            raise RuntimeError(str(result.get("error", "remote scratch init failed")))

        self.remote_scratch = RemoteScratch(
            base=remote_base,
            size=0x2000,
            integer_address=remote_base + 0x030,
            ascii_address=remote_base + 0x300,
            wide_address=remote_base + 0x400,
            bytes_address=remote_base + 0x500,
            pointer_holder=remote_base + 0x050,
            pointer_target=remote_base + 0x200,
            scan_integer_address=remote_base + 0x600,
            pattern_address=remote_base + 0x700,
            pattern_hex=pattern_hex,
        )

    def _refresh_session(self, *, attach_primary: bool = True) -> None:
        self.bridge.stop()
        time.sleep(1.0)
        self.bridge.start()
        self.session_id = self._wait_for_session()
        self.context.invalidate_runtime_cache()
        if attach_primary:
            self._call("ce.attach_process", process_name=self.primary_process_name)

    def _prepare_local_scratch(self) -> None:
        script = """
_G.__ce_mcp_local_ms = _G.__ce_mcp_local_ms or createMemoryStream()
local ms = _G.__ce_mcp_local_ms
ms.Size = 0x1000
local base = ms.Memory
writeBytesLocal(base + 0x010, 0x42)
writeSmallIntegerLocal(base + 0x020, 0x2222)
writeIntegerLocal(base + 0x030, 0x33445566)
writeQwordLocal(base + 0x040, 0x1122334455667788)
writePointerLocal(base + 0x050, base + 0x200)
writeByteLocal(base + 0x200, 0x7A)
writeSmallIntegerLocal(base + 0x210, 0x2468)
writeIntegerLocal(base + 0x220, 0x11224488)
writeQwordLocal(base + 0x230, 0x0101010102020202)
writePointerLocal(base + 0x240, base + 0x300)
writeFloatLocal(base + 0x250, 9.5)
writeDoubleLocal(base + 0x260, 12.75)
writeStringLocal(base + 0x270, 'LocalPointerChain')
writeBytesLocal(base + 0x280, {0x90, 0x91, 0x92, 0x93})
writeStringLocal(base + 0x300, 'ce_mcp_local_ascii')
writeBytesLocal(base + 0x400, {0x63,0x00,0x65,0x00,0x5F,0x00,0x6D,0x00,0x63,0x00,0x70,0x00,0x5F,0x00,0x6C,0x00,0x6F,0x00,0x63,0x00,0x61,0x00,0x6C,0x00,0x5F,0x00,0x77,0x00,0x69,0x00,0x64,0x00,0x65,0x00,0x00,0x00})
writeBytesLocal(base + 0x500, {0x01, 0x02, 0x03, 0x04})
return { base = base }
"""
        result = self.context.lua_exec(script, session_id=self.session_id, timeout_seconds=30.0)
        if result.get("ok") is False:
            raise RuntimeError(str(result.get("error", "local scratch init failed")))
        base = int(result["base"])
        self.local_scratch = LocalScratch(
            base=base,
            size=0x1000,
            integer_address=base + 0x030,
            ascii_address=base + 0x300,
            wide_address=base + 0x400,
            bytes_address=base + 0x500,
            pointer_holder=base + 0x050,
            pointer_target=base + 0x200,
        )

    @staticmethod
    def _lua_array(values: list[int]) -> str:
        return "{" + ", ".join(f"0x{value:02X}" for value in values) + "}"
    def _run_native_tools(self) -> None:
        assert self.remote_scratch is not None
        scratch_symbol = "ce_mcp_native_scratch"
        scratch_end_symbol = "ce_mcp_native_scratch_end"
        self._call("ce.bridge_status")
        self._call("ce.list_sessions")
        self._call("ce.normalize_address", address=f"{self.primary_module_name}+0")
        self._call("ce.verify_target")
        self._call("ce.list_tools")
        self._call("ce.get_attached_process")
        self._call("ce.attach_process", process_name=self.primary_process_name)
        self._call("ce.get_process_list", limit=8)
        self._call("ce.list_modules", limit=16)
        self._call("ce.list_modules_full")
        self._call("ce.register_symbol", name=scratch_symbol, address=self.remote_scratch.pattern_address, donotsave=True)
        self._call("ce.register_symbol", name=scratch_end_symbol, address=self.remote_scratch.pattern_address + 0x20, donotsave=True)
        self._call("ce.query_memory", address=f"{self.primary_module_name}+0")
        self._call(
            "ce.query_memory_map",
            limit=8,
            start_address=scratch_symbol,
            end_address=scratch_end_symbol,
            include_free=False,
        )
        self._call("ce.resolve_symbol", symbol=f"{self.primary_module_name}+0")
        self._call("ce.resolve_symbol", address=f"{self.primary_module_name}+0")
        self._call(
            "ce.aob_scan",
            pattern=self.remote_scratch.pattern_hex,
            start_address=scratch_symbol,
            end_address=scratch_end_symbol,
            max_results=4,
        )
        read_result = self._call("ce.read_memory", address=scratch_symbol, size=8)
        self._call("ce.write_memory", address=scratch_symbol, bytes_hex=str(read_result["bytes_hex"]))
        self._call("ce.exported.list", available_only=False, limit=32)
        self._call("ce.exported.get", field_name="GetLuaState")
        self._call("ce.unregister_symbol", name=scratch_end_symbol)
        self._call("ce.unregister_symbol", name=scratch_symbol)
        self._call("ce.detach_process")
        self._call("ce.attach_process", process_name=self.primary_process_name)

    def _run_exported_tools(self) -> None:
        self._call("ce.exported.list_available")
        self._call("ce.exported.list_typed_functions")
        self._call("ce.exported.list_pointer_fields")
        self._call("ce.exported.search_fields", query="Lua")
        self._call("ce.exported.get_many", field_names=["GetLuaState", "ShowMessage", "MainThreadCall"])

    def _run_address_tools(self) -> None:
        assert self.remote_scratch is not None
        self._call("ce.get_address", expression=f"{self.primary_module_name}+0")
        self._call("ce.get_address_safe", expression=f"{self.primary_module_name}+0")
        self._call("ce.get_name_from_address", address=self.primary_module_base)
        self._call("ce.register_symbol", name="ce_mcp_live_symbol", address=self.remote_scratch.base, donotsave=True)
        self._call("ce.get_address_safe", expression="ce_mcp_live_symbol")
        self._call("ce.unregister_symbol", name="ce_mcp_live_symbol")
        self._call("ce.reinitialize_symbolhandler")
        self._call("ce.in_module", address=self.primary_module_base)
        self._call("ce.in_system_module", address=self.system_function_address)
        self._call("ce.aob_scan_unique", pattern=self.remote_scratch.pattern_hex)
        self._call(
            "ce.aob_scan_module_unique",
            module_name=self.primary_module_name,
            pattern="4D 5A 90 00 03 00 00 00 04 00 00 00 FF FF 00 00",
        )

    def _run_process_tools(self) -> None:
        self._call("ce.get_ce_version")
        self._call("ce.get_cheat_engine_dir")
        self._call("ce.get_process_id_from_name", process_name=self.primary_process_name)
        self._call("ce.get_foreground_process")
        self._call("ce.get_cpu_count")
        self._call("ce.target_is_64bit")
        self._call("ce.get_window_list")
        self._call("ce.get_common_module_list")
        self._call("ce.get_auto_attach_list")
        self._call("ce.clear_auto_attach_list")
        self._call("ce.set_auto_attach_list", entries=[self.primary_process_name])
        self._call("ce.add_auto_attach_target", entry="dotnet.exe")
        self._call("ce.remove_auto_attach_target", entry="dotnet.exe")
        self._call("ce.pause_process")
        self._call("ce.unpause_process")

    def _run_memory_tools(self) -> None:
        assert self.remote_scratch is not None
        if self.local_scratch is None:
            self._prepare_local_scratch()
        assert self.local_scratch is not None

        self._call("ce.read_small_integer", address=self.remote_scratch.base + 0x020)
        self._call("ce.read_integer", address=self.remote_scratch.integer_address)
        self._call("ce.read_qword", address=self.remote_scratch.base + 0x040)
        self._call("ce.read_pointer", address=self.remote_scratch.pointer_holder)
        self._call("ce.read_float", address=self.remote_scratch.pointer_target + 0x050)
        self._call("ce.read_double", address=self.remote_scratch.pointer_target + 0x060)
        self._call("ce.read_small_integer_local", address=self.local_scratch.base + 0x020)
        self._call("ce.read_integer_local", address=self.local_scratch.integer_address)
        self._call("ce.read_qword_local", address=self.local_scratch.base + 0x040)
        self._call("ce.read_pointer_local", address=self.local_scratch.pointer_holder)
        self._call("ce.read_float_local", address=self.local_scratch.pointer_target + 0x050)
        self._call("ce.read_double_local", address=self.local_scratch.pointer_target + 0x060)

        self._call("ce.write_small_integer", address=self.remote_scratch.base + 0x020, value=0x7777)
        self._call("ce.write_integer", address=self.remote_scratch.integer_address, value=0x0BADF00D)
        self._call("ce.write_qword", address=self.remote_scratch.base + 0x040, value=0x0A0B0C0D0E0F0102)
        self._call("ce.write_pointer", address=self.remote_scratch.pointer_holder, value=self.remote_scratch.pointer_target)
        self._call("ce.write_float", address=self.remote_scratch.pointer_target + 0x050, value=7.5)
        self._call("ce.write_double", address=self.remote_scratch.pointer_target + 0x060, value=14.25)
        self._call("ce.write_small_integer_local", address=self.local_scratch.base + 0x020, value=0x5555)
        self._call("ce.write_integer_local", address=self.local_scratch.integer_address, value=0x12344321)
        self._call("ce.write_qword_local", address=self.local_scratch.base + 0x040, value=0x0908070605040302)
        self._call("ce.write_pointer_local", address=self.local_scratch.pointer_holder, value=self.local_scratch.pointer_target)
        self._call("ce.write_float_local", address=self.local_scratch.pointer_target + 0x050, value=2.5)
        self._call("ce.write_double_local", address=self.local_scratch.pointer_target + 0x060, value=11.125)

        self._call("ce.read_bytes_table", address=self.remote_scratch.bytes_address, count=4)
        self._call("ce.read_bytes_local_table", address=self.local_scratch.bytes_address, count=4)
        self._call("ce.write_bytes_values", address=self.remote_scratch.bytes_address, values=[0x44, 0x55, 0x66, 0x77])
        self._call("ce.write_bytes_local_values", address=self.local_scratch.bytes_address, values=[0x11, 0x22, 0x33, 0x44])
        self._call("ce.read_string_ex", address=self.remote_scratch.ascii_address, max_length=64, wide=False)
        self._call("ce.read_string_ex", address=self.remote_scratch.wide_address, max_length=64, wide=True)
        self._call("ce.read_string_local_ex", address=self.local_scratch.ascii_address, max_length=64, wide=False)
        self._call("ce.read_string_local_ex", address=self.local_scratch.wide_address, max_length=64, wide=True)
        self._call("ce.write_string_ex", address=self.remote_scratch.ascii_address, value="ce_mcp_written_ascii")
        self._call("ce.write_string_local_ex", address=self.local_scratch.ascii_address, value="ce_mcp_written_local")
        allocated = self._call("ce.allocate_memory", size=0x200)
        self._call("ce.full_access", address=self.remote_scratch.base, size=self.remote_scratch.size)
        self._call("ce.dealloc", address=int(allocated["address"]), size=0x200)

    def _run_pointer_tools(self) -> None:
        assert self.remote_scratch is not None
        base = self.remote_scratch.pointer_holder
        self._call("ce.resolve_pointer_chain", base_address=base, offsets=[0, 0])

        read_specs = {
            "ce.read_pointer_chain_byte": [0, 0],
            "ce.read_pointer_chain_bytes": [0, 0x80],
            "ce.read_pointer_chain_small_integer": [0, 0x10],
            "ce.read_pointer_chain_integer": [0, 0x20],
            "ce.read_pointer_chain_qword": [0, 0x30],
            "ce.read_pointer_chain_pointer": [0, 0x40],
            "ce.read_pointer_chain_float": [0, 0x50],
            "ce.read_pointer_chain_double": [0, 0x60],
        }
        for tool_name, offsets in read_specs.items():
            kwargs: dict[str, Any] = {"base_address": base, "offsets": offsets}
            if tool_name.endswith("_bytes"):
                kwargs["size"] = 4
            if tool_name.endswith("_string"):
                kwargs["max_length"] = 64
                kwargs["wide"] = False
            self._call(tool_name, **kwargs)

        self._call("ce.write_pointer_chain_byte", base_address=base, offsets=[0, 0], value=0x6A)
        self._call("ce.write_pointer_chain_bytes", base_address=base, offsets=[0, 0x80], value=[0xDE, 0xAD, 0xBE, 0xEF])
        self._call("ce.write_pointer_chain_small_integer", base_address=base, offsets=[0, 0x10], value=0x3333)
        self._call("ce.write_pointer_chain_integer", base_address=base, offsets=[0, 0x20], value=0x55667788)
        self._call("ce.write_pointer_chain_qword", base_address=base, offsets=[0, 0x30], value=0xAABBCCDDEEFF0011)
        self._call("ce.write_pointer_chain_pointer", base_address=base, offsets=[0, 0x40], value=self.remote_scratch.ascii_address)
        self._call("ce.write_pointer_chain_float", base_address=base, offsets=[0, 0x50], value=4.5)
        self._call("ce.write_pointer_chain_double", base_address=base, offsets=[0, 0x60], value=9.25)
        self._call("ce.write_pointer_chain_string", base_address=base, offsets=[0, 0x70], value="PointerChainWrite")
    def _run_script_tools(self) -> None:
        self._call("ce.lua_eval", script="1 + 1")
        self._call("ce.lua_exec", script="return { value = 2 }")
        self._call("ce.lua_eval_with_globals", script="player_name .. ':' .. tostring(limit_value)", globals={"player_name": "ce_live", "limit_value": 7})
        self._call("ce.lua_exec_with_globals", script="return { joined = player_name .. ':' .. tostring(limit_value) }", globals={"player_name": "ce_live", "limit_value": 9})
        self._call("ce.auto_assemble", script="{$lua}\nreturn ''\n{$asm}")
        self._call("ce.lua_call", function_name="readInteger", args=[self.remote_scratch.integer_address], result_field="value")
        self._call("ce.lua_set_global", variable_name="ce_mcp_live_global", value=1337)
        self._call("ce.lua_get_global", variable_name="ce_mcp_live_global")
        self._call("ce.run_script_file", path=str(self.lua_script_path))
        self._call("ce.lua_get_package_paths")
        self._call("ce.lua_get_environment")
        self._call("ce.lua_add_package_path", path=str(self.lua_module_root / "?.lua"), prepend=True)
        self._call("ce.lua_remove_package_path", path=str(self.lua_module_root / "?.lua"))
        self._call("ce.lua_add_package_cpath", path=str(self.lua_module_root / "?.dll"), prepend=True)
        self._call("ce.lua_remove_package_cpath", path=str(self.lua_module_root / "?.dll"))
        self._call("ce.lua_add_library_root", path=str(self.lua_module_root), prepend=True)
        self._call(
            "ce.lua_configure_environment",
            library_roots=[str(self.lua_module_root)],
            package_paths=[str(self.lua_module_root / "?.lua")],
            package_cpaths=[str(self.lua_module_root / "?.dll")],
            prepend=True,
        )
        self._call("ce.lua_preload_module", module_name=self.lua_preload_module_name, script="local M = {}; function M.answer() return 21 end; return M", force_reload=True)
        self._call("ce.lua_list_preloaded_modules")
        self._call("ce.lua_require_module", module_name=self.lua_preload_module_name, force_reload=True)
        self._call("ce.lua_call_module_function", module_name=self.lua_preload_module_name, function_name="answer", args=[], force_reload=True)
        self._call("ce.lua_unpreload_module", module_name=self.lua_preload_module_name)
        self._call("ce.lua_preload_file", module_name=self.lua_preload_file_module_name, path=str(self.lua_preload_file_path), force_reload=True)
        self._call("ce.lua_require_module", module_name=self.lua_preload_file_module_name, force_reload=True)
        self._call("ce.lua_call_module_function", module_name=self.lua_preload_file_module_name, function_name="answer", args=[], force_reload=False)
        self._call("ce.lua_require_module", module_name=self.lua_module_name, force_reload=True)
        self._call("ce.lua_call_module_function", module_name=self.lua_module_name, function_name="answer", args=[], force_reload=False)
        self._call("ce.lua_list_loaded_modules")
        self._call("ce.lua_unload_module", module_name=self.lua_module_name)
        self._call("ce.lua_unload_module", module_name=self.lua_preload_file_module_name)
        self._call("ce.lua_run_file", path=str(self.lua_script_path))

    def _run_scan_tools(self) -> None:
        assert self.remote_scratch is not None
        self._call("ce.scan_list_enums")
        self._call("ce.scan_list_sessions")

        base_start = self.remote_scratch.base
        base_end = self.remote_scratch.base + self.remote_scratch.size

        results_session = self._call("ce.scan_create_session")["session_id"]
        self._call("ce.scan_new", scan_session_id=results_session)
        self._call(
            "ce.scan_first",
            scan_session_id=results_session,
            options={
                "scan_option": "exact",
                "value_type": "dword",
                "input1": str(0x51525354),
                "start_address": str(base_start),
                "stop_address": str(base_end),
                "protection_flags": "*X*C*W",
            },
        )
        self._call("ce.scan_wait", scan_session_id=results_session)
        self._call("ce.scan_get_state", scan_session_id=results_session)
        self._call("ce.scan_get_progress", scan_session_id=results_session)
        self._call("ce.scan_attach_foundlist", scan_session_id=results_session)
        self._call("ce.scan_get_result_count", scan_session_id=results_session)
        self._call("ce.scan_get_results", scan_session_id=results_session, limit=8)
        self._call("ce.scan_save_results", scan_session_id=results_session, saved_result_name="ce_mcp_live_saved")
        self._call("ce.scan_detach_foundlist", scan_session_id=results_session)
        self._call("ce.scan_destroy_session", scan_session_id=results_session)

        single_result_session = self._call("ce.scan_create_session")["session_id"]
        self._call("ce.scan_new", scan_session_id=single_result_session)
        self._call("ce.scan_set_only_one_result", scan_session_id=single_result_session, enabled=True)
        self._call(
            "ce.scan_first",
            scan_session_id=single_result_session,
            options={
                "scan_option": "exact",
                "value_type": "dword",
                "input1": str(0x51525354),
                "start_address": str(base_start),
                "stop_address": str(base_end),
                "protection_flags": "*X*C*W",
            },
        )
        self._call("ce.scan_wait", scan_session_id=single_result_session)
        self._call("ce.scan_get_only_result", scan_session_id=single_result_session)
        self._call("ce.scan_destroy_session", scan_session_id=single_result_session)

        changed_session = self._call("ce.scan_create_session")["session_id"]
        self._call("ce.scan_new", scan_session_id=changed_session)
        self._call(
            "ce.scan_first",
            scan_session_id=changed_session,
            options={
                "scan_option": "exact",
                "value_type": "dword",
                "input1": str(0x51525354),
                "start_address": str(base_start),
                "stop_address": str(base_end),
                "protection_flags": "*X*C*W",
            },
        )
        self._call("ce.scan_wait", scan_session_id=changed_session)
        self._call("ce.write_integer", address=self.remote_scratch.scan_integer_address, value=0x61626364)
        self._call(
            "ce.scan_next",
            scan_session_id=changed_session,
            options={
                "scan_option": "changed",
                "input1": "",
                "input2": "",
            },
        )
        self._call("ce.scan_wait", scan_session_id=changed_session)
        self._call("ce.scan_attach_foundlist", scan_session_id=changed_session)
        self._call("ce.scan_get_results", scan_session_id=changed_session, limit=8)
        self._call("ce.scan_detach_foundlist", scan_session_id=changed_session)
        self._call("ce.scan_destroy_session", scan_session_id=changed_session)
        self._call("ce.scan_destroy_all_sessions")

        helper_session = self._call("ce.scan_create_session")["session_id"]
        self._call(
            "ce.scan_first_ex",
            scan_session_id=helper_session,
            scan_option="exact",
            value_type="dword",
            value=0x61626364,
            module_name=None,
            start_address=self.remote_scratch.base,
            end_address=self.remote_scratch.base + self.remote_scratch.size,
            protection_flags="*X*C*W",
            alignment_type="not_aligned",
            alignment_param="1",
            is_case_sensitive=False,
            is_unicode_scan=False,
        )
        self._call("ce.scan_wait", scan_session_id=helper_session)
        self._call("ce.scan_collect", scan_session_id=helper_session, limit=8)

        next_ex_session = self._call("ce.scan_create_session")["session_id"]
        self._call("ce.scan_new", scan_session_id=next_ex_session)
        self._call(
            "ce.scan_first",
            scan_session_id=next_ex_session,
            options={
                "scan_option": "exact",
                "value_type": "dword",
                "input1": str(0x61626364),
                "start_address": str(base_start),
                "stop_address": str(base_end),
                "protection_flags": "*X*C*W",
            },
        )
        self._call("ce.scan_wait", scan_session_id=next_ex_session)
        self._call("ce.write_integer", address=self.remote_scratch.scan_integer_address, value=0x71727374)
        self._call(
            "ce.scan_next_ex",
            scan_session_id=next_ex_session,
            scan_option="changed",
            value=None,
            value2=None,
            rounding_type="rounded",
            is_case_sensitive=False,
            is_unicode_scan=False,
            saved_result_name="",
        )
        self._call("ce.scan_wait", scan_session_id=next_ex_session)
        self._call("ce.scan_once", scan_option="exact", value_type="dword", value=0x61626364, start_address=self.remote_scratch.base, end_address=self.remote_scratch.base + self.remote_scratch.size)
        self._call("ce.scan_value", value=0x61626364, value_type="dword", scan_option="exact", start_address=self.remote_scratch.base, end_address=self.remote_scratch.base + self.remote_scratch.size)
        self._call("ce.scan_string", text="ce_mcp_inventory_ascii", encoding="ascii", start_address=self.remote_scratch.base, end_address=self.remote_scratch.base + self.remote_scratch.size, case_sensitive=True)
        self._call("ce.scan_destroy_all_sessions")

    def _run_table_and_record_tools(self) -> None:
        batch_records = self._call(
            "ce.record_create_many",
            records=[
                {
                    "description": "ce_mcp_live_batch_health",
                    "address": f"{self.primary_module_name}+0",
                    "type": "4 Bytes",
                    "value": 100,
                },
                {
                    "description": "ce_mcp_live_batch_bytes",
                    "address": f"{self.primary_module_name}+8",
                    "type": "Byte Array",
                    "value": "90 90",
                },
            ],
        )
        self.extra_record_ids.extend(int(entry["id"]) for entry in batch_records.get("records", []))
        group_records = self._call(
            "ce.record_create_group",
            description="ce_mcp_live_group",
            records=[
                {
                    "description": "group_child_health",
                    "address": f"{self.primary_module_name}+0",
                    "type": "4 Bytes",
                    "value": 111,
                },
                {
                    "description": "group_child_pointer",
                    "address": f"{self.primary_module_name}+0",
                    "type": "pointer",
                },
            ],
            options={"active": False},
        )
        if "group" in group_records and isinstance(group_records["group"], dict):
            self.extra_record_ids.append(int(group_records["group"]["id"]))
        self.extra_record_ids.extend(int(entry["id"]) for entry in group_records.get("records", []))

        record = self._call(
            "ce.record_create",
            options={
                "description": "ce_mcp_live_record",
                "address": f"{self.primary_module_name}+0",
                "type": "dword",
                "value": 100,
                "active": False,
            },
        )
        self.general_record_id = int(record["record"]["id"])
        script_record = self._call(
            "ce.record_create",
            options={
                "description": "ce_mcp_live_script_record",
                "address": f"{self.primary_module_name}+0",
                "type": "autoassembler",
                "script": "[ENABLE]\n[DISABLE]\n",
                "active": False,
            },
        )
        self.script_record_id = int(script_record["record"]["id"])

        self._call("ce.table_record_count")
        self._call("ce.record_list", include_script=False)
        self._call("ce.record_get_by_id", record_id=self.general_record_id, include_script=False)
        self._call("ce.record_get_by_description", description="ce_mcp_live_record", include_script=False)
        self._call("ce.record_find_all_by_description", description="ce_mcp_live_record")
        self._call("ce.record_set_description", record_id=self.general_record_id, description="ce_mcp_live_record_renamed")
        self._call("ce.record_set_address", record_id=self.general_record_id, address=f"{self.primary_module_name}+10")
        self._call("ce.record_set_type", record_id=self.general_record_id, value_type="4 Bytes")
        self._call("ce.record_set_type", record_id=self.general_record_id, value_type="pointer")
        self._call("ce.record_set_value", record_id=self.general_record_id, value=321)
        self._call("ce.record_set_active", record_id=self.general_record_id, active=False)
        self._call("ce.record_set_offsets", record_id=self.general_record_id, offsets=[0x10, 0x20])
        self._call("ce.record_get_offsets", record_id=self.general_record_id)
        self._call("ce.record_get_script", record_id=self.script_record_id)
        self._call("ce.record_set_script", record_id=self.script_record_id, script="[ENABLE]\nalloc(ce_mcp_tmp,16)\n[DISABLE]\ndealloc(ce_mcp_tmp)\n")
        self._call("ce.table_set_selected_record", record_id=self.general_record_id)
        self._call("ce.table_get_selected_record", include_script=False)
        self._call("ce.table_refresh")
        self._call("ce.table_rebuild_description_cache")
        self._call("ce.table_disable_all_without_execute")
        self._call("ce.table_create_file", name=self.table_file_name)
        self._call("ce.table_find_file", name=self.table_file_name)
        self._call("ce.table_export_file", name=self.table_file_name, path=str(self.table_export_path))
        self._call("ce.table_save", path=str(self.table_save_path))
        self._call("ce.table_load", path=str(self.table_save_path))

    def _run_structure_and_dissect_tools(self) -> None:
        assert self.remote_scratch is not None
        self._call("ce.structure_list", include_elements=False)
        self._call("ce.structure_create", name="CE_MCP_Live_Structure_A", add_global=True)
        self.structure_names.append("CE_MCP_Live_Structure_A")
        self._call(
            "ce.structure_add_element",
            name="CE_MCP_Live_Structure_A",
            options={"offset": 0, "name": "field0", "vartype": "dword", "bytesize": 4},
        )
        self._call("ce.structure_get", name="CE_MCP_Live_Structure_A", include_elements=True)
        self._call(
            "ce.structure_auto_guess",
            name="CE_MCP_Live_Structure_A",
            base_address=self.remote_scratch.base,
            offset=0,
            size=0x100,
        )
        self._call(
            "ce.structure_define",
            name="CE_MCP_Live_Structure_B",
            elements=[
                {"offset": 0, "name": "health", "vartype": "dword", "bytesize": 4},
                {"offset": 4, "name": "speed", "vartype": "float", "bytesize": 4},
            ],
            add_global=True,
        )
        self.structure_names.append("CE_MCP_Live_Structure_B")
        self._call(
            "ce.structure_define",
            name="CE_MCP_Live_Structure_Child",
            elements=[
                {"offset": 0, "name": "item_count", "vartype": "dword", "bytesize": 4},
            ],
            add_global=True,
        )
        self.structure_names.append("CE_MCP_Live_Structure_Child")
        self._call(
            "ce.structure_define",
            name="CE_MCP_Live_Structure_Read",
            elements=[
                {"offset": 0, "name": "health", "vartype": "dword", "bytesize": 4},
                {"offset": 4, "name": "speed", "vartype": "float", "bytesize": 4},
                {"offset": 8, "name": "inventory_ptr", "vartype": "pointer", "child_structure_name": "CE_MCP_Live_Structure_Child"},
            ],
            add_global=True,
        )
        self.structure_names.append("CE_MCP_Live_Structure_Read")
        self._call(
            "ce.lua_exec",
            script=(
                f"writeInteger({self.remote_scratch.base + 0x900}, 321)\n"
                f"writeFloat({self.remote_scratch.base + 0x904}, 1.5)\n"
                f"writePointer({self.remote_scratch.base + 0x908}, {self.remote_scratch.base + 0x930})\n"
                f"writeInteger({self.remote_scratch.base + 0x930}, 7)\n"
                "return { ok = true }"
            ),
        )
        self._call(
            "ce.structure_read",
            name="CE_MCP_Live_Structure_Read",
            address=self.remote_scratch.base + 0x900,
            max_depth=2,
            include_raw=True,
        )

        DotNetTarget.build()
        self.dotnet_target = DotNetTarget.start()
        self._call("ce.attach_process", process_id=self.dotnet_target.pid)
        self._call("ce.structure_create", name=self.dotnet_structure_name, add_global=True)
        self.structure_names.append(self.dotnet_structure_name)
        self._call(
            "ce.structure_fill_from_dotnet",
            name=self.dotnet_structure_name,
            address=self.dotnet_target.address,
            change_name=True,
        )

        module_info = self._call("ce.list_modules", limit=8)
        dotnet_module_name = str(module_info["modules"][0]["module_name"])
        dotnet_module_base = int(module_info["modules"][0]["base_address"])
        self._call("ce.dissect_clear")
        self._call("ce.dissect_module", module_name=dotnet_module_name, clear_first=True)
        self._call("ce.dissect_region", base_address=dotnet_module_base, size=0x2000, clear_first=True)
        self._call("ce.dissect_get_references", address=dotnet_module_base, limit=8)
        self._call("ce.dissect_get_referenced_strings", limit=8)
        self._call("ce.dissect_get_referenced_functions", limit=8)
        self._call("ce.dissect_save", path=str(self.dissect_path))
        self._call("ce.dissect_load", path=str(self.dissect_path))
        self._call("ce.attach_process", process_name=self.primary_process_name)

    def _run_debug_tools(self) -> None:
        if self.dotnet_target is None:
            DotNetTarget.build()
            self.dotnet_target = DotNetTarget.start()
        self._call("ce.attach_process", process_id=self.dotnet_target.pid)
        self._call("ce.debug_status")
        self._call("ce.debug_start", debugger_interface=2)
        self._call("ce.debug_continue", continue_option="run")
        self._call("ce.debug_list_breakpoints")
        self._safe_call("ce.debug_watch_accesses_start", address=self.dotnet_target.health_address, size=4, method="debug_register", max_hits=4, auto_continue=True, debugger_interface=2)
        self._safe_call("ce.debug_watch_writes_start", address=self.dotnet_target.health_address, size=4, method="debug_register", max_hits=4, auto_continue=True, debugger_interface=2)
        execute_watch = self._safe_call("ce.debug_watch_execute_start", address=self.primary_module_base, size=1, method="int3", max_hits=1, auto_continue=True, debugger_interface=2)
        watch_id = None
        if execute_watch is not None and execute_watch.get("ok") is not False:
            watch_id = str(execute_watch["watch"]["watch_id"])
        time.sleep(1.0)
        if watch_id is not None:
            self._safe_call("ce.debug_watch_get_hits", watch_id=watch_id, limit=8)
            self._safe_call("ce.debug_watch_stop", watch_id=watch_id)
        else:
            self._safe_call("ce.debug_watch_get_hits", watch_id="ce-missing-watch", limit=8)
            self._safe_call("ce.debug_watch_stop", watch_id="ce-missing-watch")
        self._call("ce.debug_watch_stop_all")
        self._call("ce.attach_process", process_name=self.primary_process_name)

    def _assert_all_tools_invoked(self) -> None:
        missing = sorted(set(self.server.tools) - self.invoked)
        if missing:
            raise AssertionError("live suite did not invoke every registered tool:\n" + "\n".join(missing))


def run_pointer_chain_string_smoke(primary_process_name: str | None = None) -> None:
    bridge = CheatEngineBridge(host="127.0.0.1", port=5556)
    bridge.start()
    try:
        deadline = time.time() + 20.0
        while time.time() < deadline and not bridge.list_sessions():
            time.sleep(0.5)
        if not bridge.list_sessions():
            raise RuntimeError("no Cheat Engine bridge session connected for pointer string smoke test")

        ctx = ToolContext(lambda: bridge)
        server = FakeServer()
        register_all(server, ctx)
        session_id = str(bridge.list_sessions()[0]["session_id"])
        process_name = primary_process_name or os.environ.get("CE_MCP_PRIMARY_PROCESS", "Minecraft.Windows.exe")
        attach_result = server.tools["ce.attach_process"](process_name=process_name, process_id=None, session_id=session_id)
        if attach_result.get("ok") is False:
            raise AssertionError(f"ce.attach_process failed for pointer string smoke ({process_name}): {attach_result}")

        base = int(ctx.call_lua_function("allocateMemory", args=[0x1000], session_id=session_id, result_field="address")["address"])
        init_script = (
            f"writePointer({base + 0x50}, {base + 0x200})\n"
            f"writeString({base + 0x270}, 'PointerChainLive')\n"
            f"return {{base={base}}}"
        )
        init_result = ctx.lua_exec(init_script, session_id=session_id, timeout_seconds=30.0)
        if init_result.get("ok") is False:
            raise AssertionError(f"pointer string smoke init failed: {init_result}")

        result = server.tools["ce.read_pointer_chain_string"](
            base_address=base + 0x50,
            offsets=[0, 0x70],
            max_length=64,
            wide=False,
            session_id=session_id,
        )
        if result.get("ok") is False:
            raise AssertionError(f"ce.read_pointer_chain_string failed in smoke test: {result}")
    finally:
        bridge.stop()


def run_live_tool_suite(*, primary_process_name: str | None = None) -> dict[str, Any]:
    group_methods = [
        ["_run_native_tools", "_run_exported_tools", "_run_address_tools", "_run_process_tools"],
        ["_run_pointer_tools"],
        ["_run_memory_tools", "_run_script_tools", "_run_scan_tools"],
        ["_run_table_and_record_tools"],
        ["_run_structure_and_dissect_tools"],
        ["_run_debug_tools"],
    ]

    aggregate_invoked: set[str] = set()
    all_tools: set[str] | None = None
    summary: dict[str, Any] = {}

    for methods in group_methods:
        suite = LiveToolSuite(primary_process_name=primary_process_name)
        suite.start()
        try:
            if all_tools is None:
                all_tools = set(suite.server.tools)
                summary = {
                    "primary_process_id": suite.primary_process_id,
                    "primary_process_name": suite.primary_process_name,
                    "primary_module_name": suite.primary_module_name,
                    "primary_module_base": suite.primary_module_base,
                }
            for method_name in methods:
                getattr(suite, method_name)()
        finally:
            suite.stop()
            aggregate_invoked.update(suite.invoked)

    assert all_tools is not None
    run_pointer_chain_string_smoke(primary_process_name=primary_process_name)
    aggregate_invoked.add("ce.read_pointer_chain_string")

    missing = sorted(all_tools - aggregate_invoked)
    if missing:
        raise AssertionError("live suite did not invoke every registered tool:\n" + "\n".join(missing))

    summary.update({
        "ok": True,
        "tool_count": len(all_tools),
        "invoked_count": len(aggregate_invoked),
        "invoked_tools": sorted(aggregate_invoked),
    })
    return summary
