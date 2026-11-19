# HA Report MCP v0.1.0 — closed beta
This app is a **separate read-only MCP service**. It reads JSON exports from `/share/ha_analyst_reports` mounted read-only. It does not access HA's API or database.

## Setup
1. Update HA Analyst Engine to v1.2.1 first. It exports reports on the next daily run; an existing same-day report will not automatically re-export.
2. Install this app from the same Home Assistant GitHub repository.
3. In Configuration set a cryptographically random 32+ character `api_key`, and optionally a new Tailscale auth key for this separate node. Never paste keys into chat or GitHub.
4. Keep `enable_public_funnel=false`. Startup must log `Report MCP ready ... Funnel OFF`.
5. This release **refuses** public Funnel activation. This prevents premature exposure before a full client authentication test.
6. Once the API-key MCP handshake and transport compatibility are verified in a later release, publish only this MCP service over Tailscale Funnel. Use the same key in the plugin connection settings via a supported secure API-key flow; never hard-code it in plugin source.

## Security / limitations
- Only `get_latest_report`, `list_report_dates`, and `get_report_by_date` are exposed.
- No HA control endpoints, Supervisor token, YAML, state writes or filesystem traversal.
- HTTP bearer key protects reads; loopback-only listener; fail-closed public exposure.
- Reports may include sensitive home occupancy and temperature information; protect the key.
- This is a minimal stateless MCP JSON-RPC implementation; ChatGPT connection compatibility has NOT yet been tested.
- ChatGPT scheduled tasks are not automatically connected merely because this add-on exists.

## v0.1.1 diagnostics
Startup checks unauthenticated and invalid-key requests (401), authenticated tools/list (3), authenticated latest report read, blocked path (404). Logs report date/status only. Funnel remains disabled.
