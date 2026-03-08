from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, register_specs
from ..runtime.dissect_runtime import DISSECT_RUNTIME
from ..runtime.structure_runtime import STRUCTURE_RUNTIME
from .common import runtime_tool


def register(server: FastMCP, ctx: ToolContext) -> None:
    specs = [
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
            ),
            arg_builder=lambda base_address, name=None, index=None, offset=0, size=4096: [name, index, base_address, offset, size],
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
            ),
            arg_builder=lambda address, name=None, index=None, change_name=True: [name, index, address, change_name],
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
        runtime_tool(
            ctx,
            name="ce.dissect_module",
            description="Run Cheat Engine's DissectCode analysis on a module name or CE symbol expression.",
            runtime=DISSECT_RUNTIME,
            function_name="dissect_module",
            parameters=(ParameterSpec("module_name", str), ParameterSpec("clear_first", bool, True)),
            arg_builder=lambda module_name, clear_first=True: [module_name, clear_first],
            timeout_seconds=180.0,
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_region",
            description="Run Cheat Engine's DissectCode analysis on an address range.",
            runtime=DISSECT_RUNTIME,
            function_name="dissect_region",
            parameters=(ParameterSpec("base_address", int | str), ParameterSpec("size", int), ParameterSpec("clear_first", bool, True)),
            arg_builder=lambda base_address, size, clear_first=True: [base_address, size, clear_first],
            timeout_seconds=180.0,
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_get_references",
            description="Return the DissectCode references that point to the given address.",
            runtime=DISSECT_RUNTIME,
            function_name="get_references",
            parameters=(ParameterSpec("address", int | str), ParameterSpec("limit", int, 128)),
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_get_referenced_strings",
            description="Return strings discovered by the current DissectCode analysis state.",
            runtime=DISSECT_RUNTIME,
            function_name="get_referenced_strings",
            parameters=(ParameterSpec("limit", int, 128),),
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_get_referenced_functions",
            description="Return functions discovered by the current DissectCode analysis state.",
            runtime=DISSECT_RUNTIME,
            function_name="get_referenced_functions",
            parameters=(ParameterSpec("limit", int, 128),),
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_save",
            description="Save the current DissectCode analysis state to disk.",
            runtime=DISSECT_RUNTIME,
            function_name="save",
            parameters=(ParameterSpec("path", str),),
        ),
        runtime_tool(
            ctx,
            name="ce.dissect_load",
            description="Load a DissectCode analysis state from disk.",
            runtime=DISSECT_RUNTIME,
            function_name="load",
            parameters=(ParameterSpec("path", str),),
        ),
    ]
    register_specs(server, specs)
