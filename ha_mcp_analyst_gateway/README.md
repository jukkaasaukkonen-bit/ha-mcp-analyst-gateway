# HA MCP Analyst Gateway v0.2.3 — diagnostic release

This is an **experimental, fail-closed** diagnostic release. **Public Funnel is intentionally blocked**, even if enabled in configuration, until the authenticated MCP flow is verified. Keep `enable_public_funnel: false`.

## Installation
Update the GitHub repository from the ZIP package and then update the Home Assistant app to 0.2.3. Keep the existing Tailscale auth key in the app's private settings; do not commit credentials to GitHub.

## Diagnostics
On startup the app logs:
- `[DIAG] MCP_UPSTREAM_UNAUTH`: unauthenticated response from the HA MCP backend
- `[DIAG] MCP_PROXY_UNAUTH`: unauthenticated response through Nginx
- `[DIAG] BLOCKED_ROOT` and `[DIAG] BLOCKED_OTHER_PATH`: should be HTTP_404
- `[DIAG] TAILSCALE`: should be RUNNING
- `[DIAG] FUNNEL`: DISABLED_BY_RELEASE

Expected upstream/proxy status is commonly HTTP_401; other status codes require investigation. HTTP_401 is **not proof** that an authenticated MCP client can connect. No tokens are logged or transmitted by these diagnostic probes.

## Limitations
- No authenticated MCP end-to-end test yet.
- The `/supervisor/core/api/mcp` route may require Supervisor-specific authentication and may not accept ordinary client bearer credentials. Never inject Supervisor tokens into internet-facing proxy requests.
- The 08:00 and weekly ChatGPT tasks already scheduled are **not connected** to HA live data merely by installing this app.
- No Funnel activation until a supported secure OAuth/authentication architecture and tool access are validated.
