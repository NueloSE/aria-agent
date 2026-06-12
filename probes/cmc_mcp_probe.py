#!/usr/bin/env python3
"""Probe the CMC Agent Hub MCP server: list tools, call tools, save observed reality.

Stdlib only — no pip installs needed.

Usage:
  python3 probes/cmc_mcp_probe.py list
  python3 probes/cmc_mcp_probe.py call <tool_name> '<json_args>'

Outputs:
  docs/vendor/cmc-agent-hub/observed-tools.json   (from `list`)
  tests/fixtures/cmc_<tool_name>.json             (from `call`)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCP_URL = "https://mcp.coinmarketcap.com/mcp"


def load_api_key() -> str:
    key = os.environ.get("CMC_MCP_API_KEY")
    if not key:
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("CMC_MCP_API_KEY="):
                key = line.split("=", 1)[1].split("#")[0].strip()
    if not key:
        sys.exit("CMC_MCP_API_KEY not found in env or .env")
    return key


def post(payload: dict, session_id: str | None, key: str) -> tuple[dict | None, str | None]:
    """POST a JSON-RPC message. Returns (parsed_result, session_id)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "X-CMC-MCP-API-KEY": key,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(MCP_URL, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        sid = resp.headers.get("Mcp-Session-Id") or session_id
        body = resp.read().decode()
        ctype = resp.headers.get("Content-Type", "")
    if not body.strip():
        return None, sid
    if "text/event-stream" in ctype:
        # SSE: take the last `data:` line that parses as JSON
        result = None
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    result = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    pass
        return result, sid
    return json.loads(body), sid


def handshake(key: str) -> str | None:
    init = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "aria-probe", "version": "0.1"},
        },
    }
    result, sid = post(init, None, key)
    server = (result or {}).get("result", {}).get("serverInfo", {})
    print(f"server: {server.get('name')} {server.get('version')}  session={sid}")
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid, key)
    return sid


def main() -> None:
    key = load_api_key()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    sid = handshake(key)

    if cmd == "list":
        result, _ = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, sid, key)
        tools = result.get("result", {}).get("tools", [])
        out = ROOT / "docs/vendor/cmc-agent-hub/observed-tools.json"
        out.write_text(json.dumps(tools, indent=2))
        print(f"\n{len(tools)} tools -> {out}\n")
        for t in tools:
            desc = (t.get("description") or "").split("\n")[0][:100]
            params = list(t.get("inputSchema", {}).get("properties", {}).keys())
            print(f"  {t['name']}  args={params}\n      {desc}")
    elif cmd == "call":
        tool, args = sys.argv[2], json.loads(sys.argv[3] if len(sys.argv) > 3 else "{}")
        result, _ = post(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": tool, "arguments": args}},
            sid, key,
        )
        fixtures = ROOT / "tests/fixtures"
        fixtures.mkdir(parents=True, exist_ok=True)
        out = fixtures / f"cmc_{tool}.json"
        out.write_text(json.dumps(result, indent=2))
        print(f"-> {out}")
        print(json.dumps(result, indent=2)[:2000])
    else:
        sys.exit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
