# HA MCP Analyst Gateway v0.2.1

**Experimental; not production-security audited.** This add-on exposes only `/api/mcp` through its own Tailscale node. It never bundles an HA access token, but the public MCP endpoint still depends on Home Assistant's own authentication and read-only tool restrictions.

## Installation
1. Upload the contents of this repository to a public GitHub repository, preserving `repository.yaml` at its root and the `ha_mcp_analyst_gateway` directory.
2. In Home Assistant Settings > Apps > Install app > menu > Repositories, add the GitHub repository URL.
3. Refresh the store, select HA MCP Analyst Gateway and install.
4. Leave `enable_public_funnel: false` initially. Configure a Tailscale auth key **inside the app only**; never put it in GitHub, chat, screenshots or logs.
5. Start and inspect logs. Verify that the gateway can join Tailscale and that the HA MCP upstream is reachable.
6. Verify the Home Assistant MCP Server is configured read-only and requires authentication. Confirm an unauthenticated request fails.
7. Only then explicitly enable `enable_public_funnel` and restart; review the public endpoint and test authentication again.
8. Connect the endpoint to ChatGPT only after verifying authorization and available tools. The ChatGPT scheduled tasks do not automatically inherit a plugin connection; verify scheduled access separately.

## Security / caveats
- The public route is `/api/mcp` only; other paths return 404.
- Tailscale Funnel is public internet access, not a private Tailnet-only service.
- An administrator-authenticated HA MCP connection may expose sensitive home data. Read-only reduces write risk but does not remove confidentiality risk.
- This version assumes Home Assistant is reachable at `homeassistant:8123` from the add-on container. Test this before enabling Funnel.
- The gateway does not implement separate OAuth for ChatGPT. HA's native MCP authentication requirements must be satisfied by the client. If ChatGPT cannot authenticate using its supported connection flow, do not weaken authentication: use a properly authenticated MCP broker instead.
- `tailscaled` runs in userspace networking mode. Funnel support must be confirmed in this environment.
- Do not grant the AI any write tools or share credentials.

## v0.2.1 test gate
The upstream now follows the allowlisted `backend_url` option. Default is `http://supervisor/core/api/mcp`.
The Terminal & SSH `401` test only proves the endpoint is reachable **from that container**, not from this gateway.
Before enabling Funnel, verify the gateway's own upstream connectivity and MCP authorization.
**Do not inject SUPERVISOR_TOKEN or another administrator credential into public requests.**
If the Supervisor route requires a Supervisor token and fails with 401, stop and redesign the backend authentication rather than weakening it.
