from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, register_specs
from ..runtime.pointer_runtime import POINTER_RUNTIME
from .common import runtime_tool


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
        runtime_tool(ctx, name="ce.resolve_pointer_chain", description="Resolve a multilevel pointer chain to its final address.", runtime=POINTER_RUNTIME, function_name="resolve", parameters=(ParameterSpec("base_address", int | str), ParameterSpec("offsets", list[int]))),
    ]

    read_kinds = [
        ("byte", "Read one byte through a multilevel pointer chain."),
        ("bytes", "Read a byte array through a multilevel pointer chain."),
        ("small_integer", "Read a signed 16-bit integer through a multilevel pointer chain."),
        ("integer", "Read a signed 32-bit integer through a multilevel pointer chain."),
        ("qword", "Read a 64-bit integer through a multilevel pointer chain."),
        ("pointer", "Read a pointer-sized value through a multilevel pointer chain."),
        ("float", "Read a float through a multilevel pointer chain."),
        ("double", "Read a double through a multilevel pointer chain."),
        ("string", "Read a string through a multilevel pointer chain."),
    ]
    for kind, description in read_kinds:
        params = [ParameterSpec("base_address", int | str), ParameterSpec("offsets", list[int])]
        if kind == "bytes":
            params.append(ParameterSpec("size", int, 16))
            specs.append(runtime_tool(ctx, name=f"ce.read_pointer_chain_{kind}", description=description, runtime=POINTER_RUNTIME, function_name="read", parameters=tuple(params), arg_builder=lambda base_address, offsets, size=16, *, _kind=kind: [_kind, base_address, offsets, size, False]))
        elif kind == "string":
            params.append(ParameterSpec("max_length", int, 64))
            params.append(ParameterSpec("wide", bool, False))
            specs.append(runtime_tool(ctx, name=f"ce.read_pointer_chain_{kind}", description=description, runtime=POINTER_RUNTIME, function_name="read", parameters=tuple(params), arg_builder=lambda base_address, offsets, max_length=64, wide=False, *, _kind=kind: [_kind, base_address, offsets, max_length, wide]))
        else:
            specs.append(runtime_tool(ctx, name=f"ce.read_pointer_chain_{kind}", description=description, runtime=POINTER_RUNTIME, function_name="read", parameters=tuple(params), arg_builder=lambda base_address, offsets, *, _kind=kind: [_kind, base_address, offsets, 0, False]))

    write_kinds = [
        ("byte", "Write one byte through a multilevel pointer chain.", int),
        ("bytes", "Write a byte array through a multilevel pointer chain.", list[int]),
        ("small_integer", "Write a signed 16-bit integer through a multilevel pointer chain.", int),
        ("integer", "Write a signed 32-bit integer through a multilevel pointer chain.", int),
        ("qword", "Write a 64-bit integer through a multilevel pointer chain.", int),
        ("pointer", "Write a pointer-sized value through a multilevel pointer chain.", int),
        ("float", "Write a float through a multilevel pointer chain.", float),
        ("double", "Write a double through a multilevel pointer chain.", float),
        ("string", "Write a string through a multilevel pointer chain.", str),
    ]
    for kind, description, annotation in write_kinds:
        specs.append(runtime_tool(ctx, name=f"ce.write_pointer_chain_{kind}", description=description, runtime=POINTER_RUNTIME, function_name="write", parameters=(ParameterSpec("base_address", int | str), ParameterSpec("offsets", list[int]), ParameterSpec("value", annotation)), arg_builder=lambda base_address, offsets, value, *, _kind=kind: [_kind, base_address, offsets, value]))

    register_specs(server, specs)
