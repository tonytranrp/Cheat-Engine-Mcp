from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from . import (
    address_tools,
    debug_tools,
    exported_tools,
    memory_tools,
    native_tools,
    pointer_tools,
    process_tools,
    record_tools,
    scan_helper_tools,
    scan_tools,
    script_tools,
    structure_tools,
    table_tools,
)


def register_all(server: FastMCP, ctx: ToolContext) -> None:
    native_tools.register(server, ctx)
    script_tools.register(server, ctx)
    exported_tools.register(server, ctx)
    process_tools.register(server, ctx)
    debug_tools.register(server, ctx)
    address_tools.register(server, ctx)
    memory_tools.register(server, ctx)
    pointer_tools.register(server, ctx)
    scan_tools.register(server, ctx)
    scan_helper_tools.register(server, ctx)
    structure_tools.register(server, ctx)
    table_tools.register(server, ctx)
    record_tools.register(server, ctx)
