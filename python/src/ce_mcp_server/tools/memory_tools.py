from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, register_specs
from .common import lua_function_tool


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = []

    read_scalar_specs = [
        ("ce.read_small_integer", "readSmallInteger", "Read a signed 16-bit integer from the attached process."),
        ("ce.read_integer", "readInteger", "Read a signed 32-bit integer from the attached process."),
        ("ce.read_qword", "readQword", "Read a 64-bit integer from the attached process."),
        ("ce.read_pointer", "readPointer", "Read a pointer-sized value from the attached process."),
        ("ce.read_float", "readFloat", "Read a float from the attached process."),
        ("ce.read_double", "readDouble", "Read a double from the attached process."),
        ("ce.read_small_integer_local", "readSmallIntegerLocal", "Read a signed 16-bit integer from the Cheat Engine process itself."),
        ("ce.read_integer_local", "readIntegerLocal", "Read a signed 32-bit integer from the Cheat Engine process itself."),
        ("ce.read_qword_local", "readQwordLocal", "Read a 64-bit integer from the Cheat Engine process itself."),
        ("ce.read_pointer_local", "readPointerLocal", "Read a pointer-sized value from the Cheat Engine process itself."),
        ("ce.read_float_local", "readFloatLocal", "Read a float from the Cheat Engine process itself."),
        ("ce.read_double_local", "readDoubleLocal", "Read a double from the Cheat Engine process itself."),
    ]
    for name, function_name, description in read_scalar_specs:
        specs.append(lua_function_tool(ctx, name=name, description=description, function_name=function_name, parameters=(ParameterSpec("address", int | str),), result_field="value"))

    write_scalar_specs = [
        ("ce.write_small_integer", "writeSmallInteger", "Write a signed 16-bit integer into the attached process."),
        ("ce.write_integer", "writeInteger", "Write a signed 32-bit integer into the attached process."),
        ("ce.write_qword", "writeQword", "Write a 64-bit integer into the attached process."),
        ("ce.write_pointer", "writePointer", "Write a pointer-sized value into the attached process."),
        ("ce.write_float", "writeFloat", "Write a float into the attached process."),
        ("ce.write_double", "writeDouble", "Write a double into the attached process."),
        ("ce.write_small_integer_local", "writeSmallIntegerLocal", "Write a signed 16-bit integer into the Cheat Engine process itself."),
        ("ce.write_integer_local", "writeIntegerLocal", "Write a signed 32-bit integer into the Cheat Engine process itself."),
        ("ce.write_qword_local", "writeQwordLocal", "Write a 64-bit integer into the Cheat Engine process itself."),
        ("ce.write_pointer_local", "writePointerLocal", "Write a pointer-sized value into the Cheat Engine process itself."),
        ("ce.write_float_local", "writeFloatLocal", "Write a float into the Cheat Engine process itself."),
        ("ce.write_double_local", "writeDoubleLocal", "Write a double into the Cheat Engine process itself."),
    ]
    for name, function_name, description in write_scalar_specs:
        specs.append(lua_function_tool(ctx, name=name, description=description, function_name=function_name, parameters=(ParameterSpec("address", int | str), ParameterSpec("value", int | float)), result_field="success"))

    specs.extend(
        [
            lua_function_tool(
                ctx,
                name="ce.read_bytes_table",
                description="Read a byte array from the attached process and return it as a JSON array.",
                function_name="readBytes",
                parameters=(ParameterSpec("address", int | str), ParameterSpec("count", int)),
                arg_builder=lambda address, count: [address, count, True],
                result_field="bytes",
            ),
            lua_function_tool(
                ctx,
                name="ce.read_bytes_local_table",
                description="Read a byte array from the Cheat Engine process itself and return it as a JSON array.",
                function_name="readBytesLocal",
                parameters=(ParameterSpec("address", int | str), ParameterSpec("count", int)),
                arg_builder=lambda address, count: [address, count, True],
                result_field="bytes",
            ),
            lua_function_tool(
                ctx,
                name="ce.write_bytes_values",
                description="Write a JSON array of byte values into the attached process.",
                function_name="writeBytes",
                parameters=(ParameterSpec("address", int | str), ParameterSpec("values", list[int])),
                arg_builder=lambda address, values: [address, values],
                result_field="success",
            ),
            lua_function_tool(
                ctx,
                name="ce.write_bytes_local_values",
                description="Write a JSON array of byte values into the Cheat Engine process itself.",
                function_name="writeBytesLocal",
                parameters=(ParameterSpec("address", int | str), ParameterSpec("values", list[int])),
                arg_builder=lambda address, values: [address, values],
                result_field="success",
            ),
            lua_function_tool(
                ctx,
                name="ce.read_string_ex",
                description="Read a string from the attached process.",
                function_name="readString",
                parameters=(ParameterSpec("address", int | str), ParameterSpec("max_length", int, 64), ParameterSpec("wide", bool, False)),
                arg_builder=lambda address, max_length=64, wide=False: [address, max_length, wide],
                result_field="value",
            ),
            lua_function_tool(
                ctx,
                name="ce.read_string_local_ex",
                description="Read a string from the Cheat Engine process itself.",
                function_name="readStringLocal",
                parameters=(ParameterSpec("address", int | str), ParameterSpec("max_length", int, 64), ParameterSpec("wide", bool, False)),
                arg_builder=lambda address, max_length=64, wide=False: [address, max_length, wide],
                result_field="value",
            ),
            lua_function_tool(
                ctx,
                name="ce.write_string_ex",
                description="Write a string into the attached process.",
                function_name="writeString",
                parameters=(ParameterSpec("address", int | str), ParameterSpec("value", str)),
                result_field="success",
            ),
            lua_function_tool(
                ctx,
                name="ce.write_string_local_ex",
                description="Write a string into the Cheat Engine process itself.",
                function_name="writeStringLocal",
                parameters=(ParameterSpec("address", int | str), ParameterSpec("value", str)),
                result_field="success",
            ),
            lua_function_tool(
                ctx,
                name="ce.allocate_memory",
                description="Allocate memory in the attached process using Cheat Engine's helper.",
                function_name="allocateMemory",
                parameters=(ParameterSpec("size", int), ParameterSpec("base_address", int | str | None, None)),
                arg_builder=lambda size, base_address=None: [size] if base_address is None else [size, base_address],
                result_field="address",
            ),
            lua_function_tool(
                ctx,
                name="ce.dealloc",
                description="Deallocate memory previously allocated by Cheat Engine.",
                function_name="deAlloc",
                parameters=(ParameterSpec("address", int | str), ParameterSpec("size", int | None, None)),
                arg_builder=lambda address, size=None: [address] if size is None else [address, size],
                result_field="success",
            ),
            lua_function_tool(
                ctx,
                name="ce.full_access",
                description="Mark a memory range as full-access using Cheat Engine's helper.",
                function_name="fullAccess",
                parameters=(ParameterSpec("address", int | str), ParameterSpec("size", int, 4096)),
                result_field="success",
            ),
        ]
    )

    register_specs(server, specs)
