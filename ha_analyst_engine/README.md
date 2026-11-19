# HA Analyst Engine v1.0.0

Local, **read-only** sampling and daily report generation at 08:00 Europe/Helsinki.
Uses the Home Assistant Supervisor-provided `SUPERVISOR_TOKEN` *inside* the app for GET `/api/states` only.
The token is never logged, sent to ChatGPT or exposed on a port.

- Samples 20 explicitly allowlisted entities every 15 minutes.
- Stores observations in `/data/analyst/learning.sqlite3`.
- Writes `/data/analyst/latest.json` and `latest.txt` daily at 08:00.
- Emits `[REPORT]` summaries to the app's Log tab.
- No service calls, state writes, network listener, Tailscale Funnel or MCP.
- Initial baselines need several days of samples; missing entities are reported, not guessed.
- No Home Assistant logbook, traces, Recorder backfill or verified cost attribution yet.
- **Does not send a personal push message or automatically feed ChatGPT's scheduled tasks.** Delivery is a separate integration.

## Installation
This repository archive is intended to be merged with the *existing* GitHub repository, not to replace its existing `ha_mcp_analyst_gateway/` folder.
Copy the `ha_analyst_engine/` folder into the repository root; retain the existing repository.yaml and existing gateway.
Push via GitHub Desktop. Refresh Home Assistant App Store, install HA Analyst Engine.
Keep the old MCP gateway's Funnel OFF.

## First run
Start the app and look for `[START]` and `[SAMPLE]` in Logs. An `[ERROR]` line means the API permissions or connectivity need correction.
