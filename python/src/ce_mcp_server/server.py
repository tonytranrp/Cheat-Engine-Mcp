from __future__ import annotations

import argparse
import logging
import time
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from .bridge import CheatEngineBridge
from .context import ToolContext
from .tools import register_all


logger = logging.getLogger("ce-mcp.server")
bridge: CheatEngineBridge | None = None
context: ToolContext | None = None


def get_bridge() -> CheatEngineBridge:
    if bridge is None:
        raise RuntimeError("bridge has not been initialized")
    return bridge


@asynccontextmanager
async def lifespan(_server: FastMCP):
    get_bridge().start()
    try:
        yield
    finally:
        get_bridge().stop()


server = FastMCP(
    name="cheat-engine-mcp",
    instructions="Persistent MCP backend for a live Cheat Engine plugin bridge.",
    lifespan=lifespan,
    log_level="INFO",
)


def build_context() -> ToolContext:
    global context
    if context is None:
        context = ToolContext(get_bridge)
    return context


def run_bridge_only(active_bridge: CheatEngineBridge) -> None:
    active_bridge.start()
    logger.info("Bridge-only mode is active on %s:%d", active_bridge.host, active_bridge.port)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Bridge-only mode interrupted, shutting down.")
    finally:
        active_bridge.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cheat Engine MCP backend server")
    parser.add_argument("--bridge-host", default="127.0.0.1")
    parser.add_argument("--bridge-port", type=int, default=5556)
    parser.add_argument("--transport", default="stdio", choices=("stdio", "sse", "streamable-http", "bridge-only"))
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"))
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    global bridge
    bridge = CheatEngineBridge(host=args.bridge_host, port=args.bridge_port, logger=logging.getLogger("ce-mcp.bridge"))

    register_all(server, build_context())
    if args.transport == "bridge-only":
        run_bridge_only(bridge)
        return
    server.run(args.transport)


if __name__ == "__main__":
    main()
