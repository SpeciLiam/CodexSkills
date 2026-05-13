#!/usr/bin/env python3
"""
Wrapper script to launch the nodriver MCP server with correct paths.
This ensures the nodriver_server module can be found regardless of cwd.
"""
import os
import sys

# Get the directory containing this script (mcp/)
script_dir = os.path.dirname(os.path.abspath(__file__))

# Add mcp/ to Python path so nodriver_server can be imported
if script_dir not in sys.path:
  sys.path.insert(0, script_dir)

# Also add project root for any project-wide imports
project_root = os.path.dirname(script_dir)
if project_root not in sys.path:
  sys.path.insert(0, project_root)

# Now import and run the server
from nodriver_server.server import main
import asyncio

if __name__ == "__main__":
  asyncio.run(main())
