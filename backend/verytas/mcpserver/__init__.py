"""Verytas as an MCP server (Streamable HTTP, stateless, JSON responses) at /mcp. See docs/mcp.md."""

from __future__ import annotations

from fastapi import FastAPI

from verytas.mcpserver.auth import CallLimiter, McpGate
from verytas.mcpserver.tools import build_server


def mount_mcp(app: FastAPI):
    """Registers /mcp on the app and returns the session manager, whose run() the app's lifespan must hold open.

    The route is added to the app's own router rather than mounted as a sub-application, so the request
    keeps the real FastAPI app in its scope (the tools read its settings, database and Prism from it) and
    /mcp answers without a redirect, which several clients do not follow on a POST.
    """
    settings = app.state.settings
    app.state.mcp_limiter = CallLimiter(settings.mcp_calls_per_minute)
    server = build_server(settings)
    server.streamable_http_app()  # creates the session manager; the Starlette app it returns is not used
    gate = McpGate(server.session_manager)
    for path in ("/mcp", "/mcp/"):
        app.add_route(path, gate, include_in_schema=False)
    return server.session_manager
