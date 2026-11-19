# HA Analyst Engine v1.1.0

This version extends the existing v1.0 Home Assistant app, keeping `/data/analyst/learning.sqlite3` intact across upgrades.

- Read-only `/api/states` sampling at configurable intervals.
- 24-hour sampling coverage and provisional/AMBER reports when less than 75% of expected samples exist.
- 7-day sampled temperature trends and monotonic counter deltas.
- Local SQLite observation and report history.
- At 08:00 Europe/Helsinki, writes a JSON and text report and, by default, a **Home Assistant persistent notification**.
- The **only HA write** is an optional POST to `persistent_notification/create`; this is not device control. Set `notify_persistent: false` to disable it.
- Notifications appear in the HA notification interface; they are **not** phone push notifications and do not reach ChatGPT automatically.
- No HA system log, Recorder history backfill, automation traces or verified savings attribution yet. Do not treat GREEN as a full-system audit.

## Upgrade
Replace **only** the existing `ha_analyst_engine/` directory in your GitHub Desktop clone with this archive's `ha_analyst_engine/` directory. Keep the existing `ha_mcp_analyst_gateway/`, `repository.yaml`, and root `README.md`. Commit and push. Home Assistant > Settings > Apps > Install app > Check for updates > Update HA Analyst Engine to v1.1.0.

## Validate
Look for `[START]`, `[SAMPLE]`, `[REPORT]`, and `[NOTIFY]` after the next 08:00 report. If `[NOTIFY_ERROR]` occurs, report the error text without secrets. Existing 19.11 report is preserved; no retroactive duplicate notification is sent for that day.
