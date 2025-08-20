# MCP Auto Researcher (FastMCP 2.0 minimal)

This is a minimal FastMCP 2.0 server exposing a few demo tools, suitable for Cursor stdio transport.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run (stdio)

```bash
python -m mcp_auto_researcher.server --transport stdio
```

Or programmatically via `main()` entrypoint.

## Use in Cursor

Configure Cursor MCP to run:
- Command: `.../your/.venv/bin/python`
- Args: `-m mcp_auto_researcher.server --transport stdio`
- Working Directory: repo root

See FastMCP docs for Cursor integration: [Cursor 🤝 FastMCP](https://gofastmcp.com/integrations/cursor.md).

