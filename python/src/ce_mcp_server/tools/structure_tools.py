from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..errors import ToolUsageError
from ..registration import ParameterSpec, ToolSpec, register_specs
from ..runtime.dissect_runtime import DISSECT_RUNTIME
from ..runtime.structure_runtime import STRUCTURE_RUNTIME
from .common import passthrough_tool, runtime_tool

DISSECT_TIMEOUT_PARAMETER = ParameterSpec("timeout_seconds", float, 180.0)
DISSECT_CHUNK_SIZE_PARAMETER = ParameterSpec("chunk_size", int, 0x200000)
EXECUTABLE_ONLY_PARAMETER = ParameterSpec("executable_only", bool, True)
_MAX_MEMORY_MAP_LIMIT = 8192
_MEM_COMMIT = 0x1000


def _module_matches(entry: dict[str, Any], requested_name: str) -> bool:
    requested = requested_name.casefold()
    module_name = str(entry.get("module_name", ""))
    module_path = str(entry.get("module_path", ""))
    return (
        module_name.casefold() == requested or
        module_path.casefold() == requested or
        Path(module_path).name.casefold() == requested
    )


def _resolve_module_entry(ctx: ToolContext, session_id: str, module_name: str) -> dict[str, Any]:
    modules = ctx.native_call_strict("ce.list_modules_full", session_id=session_id, timeout_seconds=30.0)
    for entry in modules.get("modules", []):
        if isinstance(entry, dict) and _module_matches(entry, module_name):
            return dict(entry)
    raise ToolUsageError(
        "module was not found in the attached target",
        code="module_not_found",
        hint="Refresh the module list and confirm the target is still attached to the expected process.",
        details={"module_name": module_name},
    )


def _build_dissect_chunks(regions: list[dict[str, Any]],
                          *,
                          module_base: int,
                          module_size: int,
                          chunk_size: int,
                          executable_only: bool) -> tuple[list[tuple[int, int]], list[dict[str, Any]]]:
    module_end = module_base + module_size
    selected_regions: list[dict[str, Any]] = []
    for region in regions:
        if not isinstance(region, dict):
            continue
        base_address = int(region.get("base_address", 0) or 0)
        region_size = int(region.get("region_size", 0) or 0)
        if base_address <= 0 or region_size <= 0:
            continue
        region_end = base_address + region_size
        if region_end <= module_base or base_address >= module_end:
            continue
        if int(region.get("state", 0) or 0) != _MEM_COMMIT:
            continue
        if bool(region.get("guarded", False)):
            continue
        if executable_only and not bool(region.get("executable", False)):
            continue
        selected_regions.append(dict(region))

    if not selected_regions:
        selected_regions = [{
            "base_address": module_base,
            "region_size": module_size,
            "state": _MEM_COMMIT,
            "guarded": False,
            "executable": True,
        }]

    chunks: list[tuple[int, int]] = []
    for region in selected_regions:
        region_start = max(module_base, int(region.get("base_address", 0) or 0))
        region_end = min(module_end, region_start + int(region.get("region_size", 0) or 0))
        cursor = region_start
        while cursor < region_end:
            size = min(chunk_size, region_end - cursor)
            if size <= 0:
                break
            chunks.append((cursor, size))
            cursor += size

    return chunks, selected_regions


def _dissect_module_handler(ctx: ToolContext,
                            *,
                            module_name: str,
                            clear_first: bool = True,
                            executable_only: bool = True,
                            chunk_size: int = 0x200000,
                            timeout_seconds: float = 180.0,
                            session_id: str | None = None) -> dict[str, Any]:
    resolved_timeout = float(timeout_seconds)
    if resolved_timeout <= 0.0:
        raise ToolUsageError(
            "timeout_seconds must be greater than zero",
            code="invalid_timeout_seconds",
            hint="Use a positive timeout for chunked module dissection.",
            details={"received": timeout_seconds},
        )
    if int(chunk_size) <= 0:
        raise ToolUsageError(
            "chunk_size must be greater than zero",
            code="invalid_chunk_size",
            hint="Use a positive chunk size in bytes for chunked module dissection.",
            details={"received": chunk_size},
        )

    resolved_session = ctx.resolve_session_id(session_id)
    module = _resolve_module_entry(ctx, resolved_session, module_name)
    module_base = int(module.get("base_address", 0) or 0)
    module_size = int(module.get("size", 0) or 0)
    if module_base <= 0 or module_size <= 0:
        raise ToolUsageError(
            "module entry is missing a valid base or size",
            code="invalid_module_bounds",
            details={"module_name": module_name, "base_address": module.get("base_address"), "size": module.get("size")},
        )

    map_payload = {
        "start_address": module_base,
        "end_address": module_base + module_size,
        "limit": _MAX_MEMORY_MAP_LIMIT,
        "include_free": False,
    }
    map_timeout = max(5.0, min(resolved_timeout, 30.0))
    map_result = ctx.native_call_safe(
        "ce.query_memory_map",
        payload=map_payload,
        session_id=resolved_session,
        timeout_seconds=map_timeout,
    )
    map_regions = list(map_result.get("regions", [])) if map_result.get("ok") is True else []
    chunks, selected_regions = _build_dissect_chunks(
        map_regions,
        module_base=module_base,
        module_size=module_size,
        chunk_size=int(chunk_size),
        executable_only=bool(executable_only),
    )

    if clear_first:
        clear_result = ctx.call_runtime_function(
            DISSECT_RUNTIME,
            "clear",
            args=[],
            session_id=resolved_session,
            timeout_seconds=min(30.0, resolved_timeout),
        )
        if clear_result.get("ok") is not True:
            return clear_result

    deadline = time.monotonic() + resolved_timeout
    completed_chunks = 0
    for chunk_base, chunk_len in chunks:
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            return {
                "ok": False,
                "error": "operation_timed_out",
                "module_name": module_name,
                "module_base": module_base,
                "module_size": module_size,
                "completed_chunks": completed_chunks,
                "chunk_count": len(chunks),
                "strategy": "chunked_regions",
            }

        chunk_result = ctx.call_runtime_function(
            DISSECT_RUNTIME,
            "dissect_region",
            args=[chunk_base, chunk_len, False],
            session_id=resolved_session,
            timeout_seconds=max(5.0, min(remaining, 30.0)),
        )
        if chunk_result.get("ok") is not True:
            failed = dict(chunk_result)
            failed.setdefault("module_name", module_name)
            failed.setdefault("module_base", module_base)
            failed.setdefault("module_size", module_size)
            failed["completed_chunks"] = completed_chunks
            failed["chunk_count"] = len(chunks)
            failed["strategy"] = "chunked_regions"
            return failed

        completed_chunks += 1

    return {
        "ok": True,
        "session_id": resolved_session,
        "module_name": module_name,
        "module_base": module_base,
        "module_size": module_size,
        "dissected": True,
        "strategy": "chunked_regions",
        "clear_first": bool(clear_first),
        "executable_only": bool(executable_only),
        "chunk_size": int(chunk_size),
        "region_count": len(selected_regions),
        "chunk_count": len(chunks),
        "completed_chunks": completed_chunks,
        "memory_map_timed_out": bool(map_result.get("timed_out", False)),
        "memory_map_truncated": bool(map_result.get("truncated", False)),
    }


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs: list[ToolSpec] = [
        runtime_tool(
            ctx,
            name="ce.structure_list",
            description="List Cheat Engine structure definitions from the global structure list.",
            runtime=STRUCTURE_RUNTIME,
            function_name="list_structures",
            parameters=(ParameterSpec("include_elements", bool, False),),
        ),
        runtime_tool(
            ctx,
            name="ce.structure_get",
            description="Fetch one Cheat Engine structure definition by name or index.",
            runtime=STRUCTURE_RUNTIME,
            function_name="get_structure",
            parameters=(
                ParameterSpec("name", str | None, None),
                ParameterSpec("index", int | None, None),
                ParameterSpec("include_elements", bool, True),
            ),
            arg_builder=lambda name=None, index=None, include_elements=True: [name, index, include_elements],
        ),
        runtime_tool(
            ctx,
            name="ce.structure_create",
            description="Create a Cheat Engine structure definition and optionally add it to the global structure list.",
            runtime=STRUCTURE_RUNTIME,
            function_name="create_structure",
            parameters=(ParameterSpec("name", str), ParameterSpec("add_global", bool, True)),
            arg_builder=lambda name, add_global=True: [name, add_global],
        ),
        runtime_tool(
            ctx,
            name="ce.structure_delete",
            description="Remove a Cheat Engine structure definition by name or index.",
            runtime=STRUCTURE_RUNTIME,
            function_name="delete_structure",
            parameters=(
                ParameterSpec("name", str | None, None),
                ParameterSpec("index", int | None, None),
                ParameterSpec("destroy", bool, True),
            ),
            arg_builder=lambda name=None, index=None, destroy=True: [name, index, destroy],
        ),
        runtime_tool(
            ctx,
            name="ce.structure_add_element",
            description="Append one element to an existing Cheat Engine structure definition.",
            runtime=STRUCTURE_RUNTIME,
            function_name="add_element",
            parameters=(
                ParameterSpec("name", str | None, None),
                ParameterSpec("index", int | None, None),
                ParameterSpec("options", dict[str, object], {}),
            ),
            arg_builder=lambda name=None, index=None, options=None: [name, index, options or {}],
        ),
        runtime_tool(
            ctx,
            name="ce.structure_define",
            description="Create a Cheat Engine structure definition from a list of element option dictionaries.",
            runtime=STRUCTURE_RUNTIME,
            function_name="define_structure",
            parameters=(
                ParameterSpec("name", str),
                ParameterSpec("elements", list[dict[str, object]], []),
                ParameterSpec("add_global", bool, True),
            ),
            arg_builder=lambda name, elements=None, add_global=True: [name, elements or [], add_global],
        ),
        runtime_tool(
            ctx,
            name="ce.structure_auto_guess",
            description="Use Cheat Engine's Structure.autoGuess on a structure definition against a memory address.",
            runtime=STRUCTURE_RUNTIME,
            function_name="auto_guess",
            parameters=(
                ParameterSpec("base_address", int | str),
                ParameterSpec("name", str | None, None),
                ParameterSpec("index", int | None, None),
                ParameterSpec("offset", int, 0),
                ParameterSpec("size", int, 4096),
                DISSECT_TIMEOUT_PARAMETER,
            ),
            arg_builder=lambda base_address, name=None, index=None, offset=0, size=4096, timeout_seconds=120.0: [name, index, base_address, offset, size],
            timeout_seconds=120.0,
        ),
        runtime_tool(
            ctx,
            name="ce.structure_fill_from_dotnet",
            description="Populate a structure definition from a .NET object address using Cheat Engine's fillFromDotNetAddress helper.",
            runtime=STRUCTURE_RUNTIME,
            function_name="fill_from_dotnet",
            parameters=(
                ParameterSpec("address", int | str),
                ParameterSpec("name", str | None, None),
                ParameterSpec("index", int | None, None),
                ParameterSpec("change_name", bool, True),
                DISSECT_TIMEOUT_PARAMETER,
            ),
            arg_builder=lambda address, name=None, index=None, change_name=True, timeout_seconds=120.0: [name, index, address, change_name],
            timeout_seconds=120.0,
        ),
        runtime_tool(
            ctx,
            name="ce.structure_read",
            description="Read a memory address as an instance of a Cheat Engine structure definition.",
            runtime=STRUCTURE_RUNTIME,
            function_name="read_structure",
            parameters=(
                ParameterSpec("address", int | str),
                ParameterSpec("name", str | None, None),
                ParameterSpec("index", int | None, None),
                ParameterSpec("max_depth", int, 1),
                ParameterSpec("include_raw", bool, True),
                DISSECT_TIMEOUT_PARAMETER,
            ),
            arg_builder=lambda address, name=None, index=None, max_depth=1, include_raw=True, timeout_seconds=120.0: [name, index, address, max_depth, include_raw],
            timeout_seconds=120.0,
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_clear",
            description="Clear the current Cheat Engine DissectCode analysis state.",
            runtime=DISSECT_RUNTIME,
            function_name="clear",
            parameters=(),
        ),
        passthrough_tool(
            name="ce.dissect_module",
            description="Run Cheat Engine DissectCode against a module by chunking executable regions instead of one monolithic full-module pass.",
            parameters=(
                ParameterSpec("module_name", str),
                ParameterSpec("clear_first", bool, True),
                EXECUTABLE_ONLY_PARAMETER,
                DISSECT_CHUNK_SIZE_PARAMETER,
                DISSECT_TIMEOUT_PARAMETER,
                ParameterSpec("session_id", str | None, None),
            ),
            handler=lambda **kwargs: _dissect_module_handler(ctx, **kwargs),
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_region",
            description="Run Cheat Engine's DissectCode analysis on an address range.",
            runtime=DISSECT_RUNTIME,
            function_name="dissect_region",
            parameters=(
                ParameterSpec("base_address", int | str),
                ParameterSpec("size", int),
                ParameterSpec("clear_first", bool, True),
                DISSECT_TIMEOUT_PARAMETER,
            ),
            arg_builder=lambda base_address, size, clear_first=True, timeout_seconds=180.0: [base_address, size, clear_first],
            timeout_seconds=180.0,
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_get_references",
            description="Return the DissectCode references that point to the given address.",
            runtime=DISSECT_RUNTIME,
            function_name="get_references",
            parameters=(ParameterSpec("address", int | str), ParameterSpec("limit", int, 128), DISSECT_TIMEOUT_PARAMETER),
            arg_builder=lambda address, limit=128, timeout_seconds=30.0: [address, limit],
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_get_referenced_strings",
            description="Return strings discovered by the current DissectCode analysis state.",
            runtime=DISSECT_RUNTIME,
            function_name="get_referenced_strings",
            parameters=(ParameterSpec("limit", int, 128), DISSECT_TIMEOUT_PARAMETER),
            arg_builder=lambda limit=128, timeout_seconds=30.0: [limit],
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_get_referenced_functions",
            description="Return functions discovered by the current DissectCode analysis state.",
            runtime=DISSECT_RUNTIME,
            function_name="get_referenced_functions",
            parameters=(ParameterSpec("limit", int, 128), DISSECT_TIMEOUT_PARAMETER),
            arg_builder=lambda limit=128, timeout_seconds=30.0: [limit],
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_save",
            description="Save the current DissectCode analysis state to disk.",
            runtime=DISSECT_RUNTIME,
            function_name="save",
            parameters=(ParameterSpec("path", str), DISSECT_TIMEOUT_PARAMETER),
            arg_builder=lambda path, timeout_seconds=30.0: [path],
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_load",
            description="Load a DissectCode analysis state from disk.",
            runtime=DISSECT_RUNTIME,
            function_name="load",
            parameters=(ParameterSpec("path", str), DISSECT_TIMEOUT_PARAMETER),
            arg_builder=lambda path, timeout_seconds=30.0: [path],
        ),
    ]
    register_specs(server, specs)
