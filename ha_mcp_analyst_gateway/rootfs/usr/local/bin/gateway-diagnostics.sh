#!/bin/sh
set -eu
BACKEND="${1:?backend required}"
# All tests are unauthenticated, read-only GETs. Never log request credentials.
check() {
  label="$1"
  url="$2"
  output="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --max-time 8 \
    --header 'Accept: application/json, text/event-stream' "$url" 2>/dev/null)" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "[DIAG] $label: NETWORK_ERROR curl_exit=$rc"
    return 0
  fi
  echo "[DIAG] $label: HTTP_$output"
}
check "MCP_UPSTREAM_UNAUTH" "$BACKEND"
check "MCP_PROXY_UNAUTH" "http://127.0.0.1:8787/api/mcp"
check "BLOCKED_ROOT" "http://127.0.0.1:8787/"
check "BLOCKED_OTHER_PATH" "http://127.0.0.1:8787/api/states"
if tailscale status --json 2>/dev/null | jq -e '.BackendState == "Running"' >/dev/null 2>&1; then
  echo "[DIAG] TAILSCALE: RUNNING"
else
  echo "[DIAG] TAILSCALE: NOT_RUNNING"
fi
echo "[DIAG] FUNNEL: DISABLED_BY_RELEASE"
echo "[DIAG] NOTE: HTTP_401 means authentication required, NOT a successful authenticated MCP session."
