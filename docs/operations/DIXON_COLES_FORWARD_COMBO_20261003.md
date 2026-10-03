# Operator-only constrained model and COMBO shadow

Preparation does not install or run services. This release **does not change published SINGLE or COMBO selection**. It starts a separately declared prospective comparison for the improved solver and COMBO ranking. Real predictive-quality improvement remains unproven.

On the VPS, after receiving the prepared wrapper:

```bash
python3 ~/goalvision-operations/dixon-coles-forward.py
sudo python3 ~/goalvision-operations/dixon-coles-forward.py --apply
```

The first command is read-only preflight. Apply prints DIXON_COLES_FORWARD_COMBO_SHADOW_DEPLOYED and the pinned release path. Only the new timer is enabled; no manual service cycle, provider request or Telegram test send is made.

Schedule: :12:30/:42:30 Europe/Riga, after original research. CPU 25%, nice 10, memory 256 MiB, 45-second worker budget/50-second service limit. Busy/failed/unknown production or original research causes a skip. There is no missed-cycle catch-up. Capture stops at the frozen 2026-10-19T00:00:00Z boundary; existing forecasts continue to be evaluated from existing result facts.

Read back without starting a service:

```bash
systemctl status goalvision-dixon-coles-forward.timer --no-pager
systemctl show goalvision-dixon-coles-forward.service -p WorkingDirectory -p ExecStart -p Nice -p CPUQuotaPerSecUSec -p PrivateNetwork -p ReadWritePaths
python3 -m json.tool /var/lib/goalvision-dixon-coles-forward/latest.json
```

latest.json appears after a natural timer start. COMPLETED confirms execution, not model quality; empty or insufficient COMBO coverage is valid. PENDING and NEEDS_MORE_EVIDENCE remain until genuine outcomes accumulate. BLOCKED/PARTIAL or repeated budget/coverage failures require diagnosis; do not trigger manual cycles or provider calls to fill gaps.

Pause only this new process:

```bash
sudo python3 ~/goalvision-operations/dixon-coles-forward.py --apply --rollback
```

Pause preserves all new state, original research and production. Reapplying the exact package retains the declared cohort. The pinned updater refuses source/environment/route/unit drift, wrong existing cohorts, symlinks and aliases of the old research DB. Original research manifest, unit files and all reviewed original records must remain present. Root preflight additionally verifies ADMIN Codex's disabled config/marker.

Preserved: PREMATCH SINGLE >=1.50 in Lab, COMBO legs >=1.30 in its bot/private period, no combined floor, today-only, quality checks, Reply results, early COMBO loss and remaining legs, all historical statistics/open settlements, calibration/de-vig, champion and Official; LIVE/ADMIN Codex remain disabled. No promotion, production repointing, git push or hidden reset.

Evidence: docs/evidence/dixon_coles_forward_combo_20261003/verification.json and controlled_replay.json. The latter is synthetic and must never be counted as prospective evidence.

Prepared source commit: 1183e356e479a3a4bcc52c7e63d3bc1b61d00a89. Package: `/home/arvis/goalvision-operations/dixon-coles-forward-1183e35-20261003`; 842 application files and 844 checksums passed. Read-only wrapper preflight passed; root ADMIN guard is evaluated by the operator apply. Preparation left the new units/state absent. Package evidence: `docs/evidence/dixon_coles_forward_combo_20261003/package_readback.json`.
