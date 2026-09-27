# PREMATCH ADMIN alerts v1 — operator summary

**ADMIN_ALERTS_V1_READY_FOR_REVIEW. Software prepared; sender disabled; monitor not installed.**

- Branch: `codex/prematch-admin-alerts`, based on installed application `23e57e9c48f321b8ee5f67bd536fbb2b264f6cb0`.
- Verified configured capabilities: new picks, observation and labels all enabled. Nightly learning retains its separately configured `363f567` release.
- PREMATCH services/configuration/application unchanged; LIVE remains parked. No pause, sudo, deployment, football API calls or Telegram sends.
- Tests: 72 monitor tests + 66 relevant PREMATCH regressions passed. Service template verification and final payload/loaded-drift check passed.
- One host rehearsal: 0.0845 seconds, no-send, existing sources only. Producers were active at the schedule boundary; stdout empty; claim review deferred. Transient-deadline warning correction was tested offline without another host scan.
- Final package: `/home/arvis/goalvision-operations/prematch-admin-alerts-package-v1-final`. The unsuffixed development package is superseded.
- SHA256SUMS SHA-256: `3a27a9f75996698a5576cff2f3e889d3a5c20d091fb0c891de704b462ac9b7a0`.
- Handoff and fixed one-line check/install/disable commands: `/home/arvis/goalvision-operations/prematch-admin-alerts/docs/operations/PREMATCH_ADMIN_ALERTS_V1.md`.
- Sanitized rehearsal report: `/home/arvis/goalvision-operations/prematch-admin-alerts-rehearsal/incident-report.json`.
- Remaining prerequisites: dedicated ADMIN token/bot identity/private chat and confirmed `/start`; dedicated non-root account and read grants; separate reviewed installation and sender enablement. None was invented or borrowed from Lab/LIVE.
- Delivery is bounded at-least-once with stable incident IDs; duplicates are possible. Total host/network failure cannot be announced by this local monitor.
