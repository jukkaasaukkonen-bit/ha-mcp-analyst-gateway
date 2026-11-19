# HA Report MCP v0.3.0 — local security review build

**Not production ready; Funnel hard-disabled.** This package is for review and controlled local integration testing only. Do not overwrite the existing working v0.1.1 Home Assistant app.

Changes: ChatGPT-domain-only dynamic client registration; PKCE S256; one-time authorization codes; 15-minute access tokens; rotating 30-day refresh tokens; hashed tokens in SQLite; explicit reports:read scope; MCP protected-resource discovery; Origin check; strict JSON-RPC parsing and request size limits.

Test with `python3 -m unittest discover -s tests -v` on a machine with Python 3.11+.

Unverified / deployment blockers:
- Live GitHub login and ChatGPT authorization flow, including dynamic client registration compatibility.
- ChatGPT MCP transport and protocol version negotiation, streaming behavior and any required resource metadata URLs.
- Secure HTTPS ingress / Funnel integration, session/consent UI, rate limits, OAuth CSRF and authorization server security review.
- No proof that scheduled ChatGPT tasks can access connected MCP tools.
- GitHub numeric account ID must be obtained from GitHub via a trusted lookup, never guessed; keep client secret out of repository.

**Do not set `enable_public_funnel: true`**. No HA control tools are exposed.
