# Forward-Test Weekly Operations Runbook

This runbook is subordinate to `AGENTS.md`, `PRODUCT_RULES.md`, and
`docs/forward_test_monitoring.md`.

The safe sequence is: isolated database hash → offline health → unresolved
queue → per-observation audits → weekly and cumulative reports → exact
reproduction → new export directory → human review. Stop on corruption.

Never interpret an acknowledgement as a data repair. Never omit a losing,
void, blocked, no-selection, unpublished, or pending record. Never call a
provider merely to generate a report. Never send the Telegram preview from this
tool. The operator retains separate authorization responsibility for any Lab
publication.

Expected weekly artifacts are `report.json`, `report.md`,
`telegram-preview.txt`, `observations.csv`, `settlements.csv`, `market.csv`,
`competition.csv`, `bookmaker.csv`, `calibration_bins.csv`,
`data_quality.csv`, `lifecycle.csv`, `unresolved.csv`, and `manifest.json`.
Every file is UTF-8 and the manifest records stable SHA-256 fingerprints.
