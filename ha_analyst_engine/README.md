# HA Analyst Engine v1.2.0

Local Home Assistant analytics. Keeps the v1.1 sampling, persistent notifications and existing `/data/analyst/learning.sqlite3` database. Adds offline-tested 1/7/30/90-day trend windows, temperature aggregates, conservative counter deltas, repeated unavailable/unknown detection, and stable learning-hypothesis IDs. All additional analytics use **observed 15-minute samples**, not historical Recorder backfill. Early windows are provisional.

## Safety

No heating or charging control, no HA YAML modifications, no exposed ports, no cloud service. The only existing write action is the v1.1 `persistent_notification.create` report notification. HA state access uses Supervisor token internally, never exported. No MCP or Funnel integration.

## Important limitations

- Existing v1.1 samples and reports are preserved across upgrades, provided Supervisor preserves the app's `/data`.
- Reports are created once per local day at 08:00; updating after 08:00 does not replace that day's report.
- Cycle counter changes are only reported when samples are monotonic. They are observations, not independently audited event counts.
- Financial sensor values are point-in-time readings, **not** independently validated savings. No causal savings claim is made.
- No full HA system log, automation traces, Recorder backfill, or ChatGPT push/delivery yet.
- Learning hypotheses are stored in the SQLite `hypotheses` table and included in the report. This is evidence tracking, not autonomous model retraining.

## Install

In the existing GitHub repository, replace **only** `ha_analyst_engine/` with the folder from this update ZIP. Preserve `ha_mcp_analyst_gateway/`, root `repository.yaml` and root `README.md`. Commit and push with GitHub Desktop, then refresh Home Assistant App Store and update the existing HA Analyst Engine app. Do not uninstall it (uninstall could remove `/data`). Keep the old MCP gateway Funnel OFF.

After updating, look for `[START]` and `[SAMPLE]` in logs. The next daily `[REPORT]` will include the `optimization` object in `/data/analyst/latest.json`. Persistent notification remains enabled when configured.
