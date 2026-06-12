#!/usr/bin/env bash
# TWAK probe — re-runnable. Reads TWAK_WALLET_PASSWORD from env/.env.
# Findings as of 2026-06-12 recorded in docs/vendor/trust-wallet-agent-kit/NOTES.md
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && export $(grep -E '^TWAK_WALLET_PASSWORD=' .env | head -1)

echo "=== auth ===";        twak auth status
echo "=== chains ===";      twak chains
echo "=== price ===";       twak price BNB
echo "=== quote ===";       twak swap 10 USDT WBNB --chain bsc --quote-only
echo "=== compete ===";     twak compete status --json
echo "=== mcp tools ==="
printf '%s\n%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"aria-probe","version":"0.1"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | timeout 30 twak serve --password "$TWAK_WALLET_PASSWORD" 2>/dev/null \
  | python3 -c "
import json,sys
for line in sys.stdin:
    line=line.strip()
    if not line.startswith('{'): continue
    msg=json.loads(line)
    if msg.get('id')==2:
        tools=msg['result']['tools']
        open('docs/vendor/trust-wallet-agent-kit/observed-tools.json','w').write(json.dumps(tools,indent=2))
        print(len(tools),'tools ->','docs/vendor/trust-wallet-agent-kit/observed-tools.json')
"
