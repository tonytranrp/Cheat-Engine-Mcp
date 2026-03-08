from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..context import ToolContext
from ..registration import ParameterSpec, ToolSpec, register_specs


def register(server: FastMCP, ctx: ToolContext) -> None:
    def fetch_fields(session_id: str | None = None) -> list[dict]:
        response = ctx.native_call_safe("ce.exported.list", payload={"limit": 159}, session_id=session_id)
        return list(response.get("fields", [])) if response.get("ok") else []

    specs = [
        ToolSpec(
            name="ce.exported.list_available",
            description="List ExportedFunctions fields that are currently non-null in the connected Cheat Engine build.",
            parameters=(ParameterSpec("session_id", str | None, None),),
            handler=lambda session_id=None: ctx.native_call_safe("ce.exported.list", payload={"available_only": True, "limit": 159}, session_id=session_id),
        ),
        ToolSpec(
            name="ce.exported.list_typed_functions",
            description="List typed function-pointer fields from the copied ExportedFunctions block.",
            parameters=(ParameterSpec("session_id", str | None, None),),
            handler=lambda session_id=None: {
                "ok": True,
                "fields": [field for field in fetch_fields(session_id) if field.get("kind") == "typed_function"],
            },
        ),
        ToolSpec(
            name="ce.exported.list_pointer_fields",
            description="List raw pointer fields from the copied ExportedFunctions block.",
            parameters=(ParameterSpec("session_id", str | None, None),),
            handler=lambda session_id=None: {
                "ok": True,
                "fields": [field for field in fetch_fields(session_id) if field.get("kind") == "pointer"],
            },
        ),
        ToolSpec(
            name="ce.exported.search_fields",
            description="Search ExportedFunctions field names and type names by substring.",
            parameters=(ParameterSpec("query", str), ParameterSpec("session_id", str | None, None)),
            handler=lambda query, session_id=None: {
                "ok": True,
                "query": query,
                "fields": [
                    field
                    for field in fetch_fields(session_id)
                    if query.lower() in str(field.get("name", "")).lower() or query.lower() in str(field.get("type_name", "")).lower()
                ],
            },
        ),
        ToolSpec(
            name="ce.exported.get_many",
            description="Fetch multiple ExportedFunctions fields by name in one call.",
            parameters=(ParameterSpec("field_names", list[str]), ParameterSpec("session_id", str | None, None)),
            handler=lambda field_names, session_id=None: {
                "ok": True,
                "fields": [ctx.native_call_safe("ce.exported.get", payload={"field_name": name}, session_id=session_id) for name in field_names],
            },
        ),
    ]

    register_specs(server, specs)
