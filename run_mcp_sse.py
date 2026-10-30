"""Remote HTTP/SSE Launcher for News MCP Server.

Exposes the Model Context Protocol (MCP) server over SSE (Server-Sent Events) and HTTP,
allowing remote agents, IDEs, and services to connect over the network.

Usage:
    python run_mcp_sse.py
    # Runs on http://0.0.0.0:8000
"""

from __future__ import annotations

import argparse
import os
import uvicorn
from mcp_server.server import mcp

app = mcp.sse_app()


def main():
    parser = argparse.ArgumentParser(description="Run News MCP Server via SSE/HTTP")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"), help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", 8000)), help="Port to bind (default: 8000)")
    args = parser.parse_args()

    print(f"📡 Starting News MCP SSE Server on http://{args.host}:{args.port}")
    print(f"🔗 SSE Endpoint: http://{args.host}:{args.port}/sse")
    print(f"📨 Messages Endpoint: http://{args.host}:{args.port}/messages/")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

