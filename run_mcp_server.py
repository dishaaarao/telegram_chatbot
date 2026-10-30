"""Standalone Launcher for News MCP Server.

Can be run directly via:
    python run_mcp_server.py

Or configured in Claude Desktop / Cursor settings:
{
  "mcpServers": {
    "news": {
      "command": "/path/to/.venv/bin/python",
      "args": ["/path/to/run_mcp_server.py"]
    }
  }
}
"""

from __future__ import annotations

import sys
from mcp_server.server import run_stdio

if __name__ == "__main__":
    try:
        run_stdio()
    except KeyboardInterrupt:
        sys.exit(0)

