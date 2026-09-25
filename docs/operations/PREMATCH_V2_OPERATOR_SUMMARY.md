# PREMATCH current operator summary — reviewed hardening upgrade

**UPGRADE_PACKAGE_READY_FOR_REVIEW. New picks remain disabled.**

The V2 system is already installed at `/home/arvis/GoalVisionAI-prematch-release-installer-v2-20260925`,
commit `3d99f7dd5348e1440cb6c41eb9d91106c2a0b815`. Discovery has no `--send`; observation and
labels remain enabled. Settlement's separate `--send` stays unchanged.
All four relevant timers were active/enabled at inspection. The former summary's
first-installation-pending statement was stale; old packages remain comparison artifacts.

- Operations branch: `codex/prematch-reviewed-hardening-upgrade`
- Operations worktree: `/home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade`
- Accepted application: `a7cb28ba5fcd87ada8ed8f4e78a18e0cec6021f2`
- Proposed release: `/home/arvis/GoalVisionAI-prematch-release-reviewed-hardening-a7cb28b-20260925`
- Proposed application tree: `333405e4cf5d4ae0ab61f1341ef1cb5fa4e355ea`
- New versioned package: `/home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925`
- Report: `/home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade/docs/operations/PREMATCH_REVIEWED_HARDENING_UPGRADE.md`
- Manifest SHA-256: `10afc86a3da97dd24ee961010433dd455b53e644469060049def20bfa906a7b7`
- Focused validation: **243 passed**; staged systemd syntax passed; disposable output
  rotation and complete persistence-failure facts verified. No live transport/provider calls.

After review, the operator's ONE-LINE installation command is:

```bash
sudo /home/arvis/GoalVisionAI/.venv/bin/python -E -B /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/upgrade_prematch_reviewed.py /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/manifest.json upgrade --sha256 10afc86a3da97dd24ee961010433dd455b53e644469060049def20bfa906a7b7
```

**NOT EXECUTED.** Installation, first scheduled no-send tick on the new release,
and publication re-enablement are three separate outstanding states. Do not invoke
a manual discovery/publication/settlement cycle. Do not use old `apply`/pre-V2 rollback.
The upgrade preserves quota 400/reserve 100, credential paths, cadence and disabled
capabilities; gates/drains all four compatible services; restores exact prior compatible
configuration on failure. No shared release configuration or database history changes.

Read-only configuration check:

```bash
/home/arvis/GoalVisionAI/.venv/bin/python -E -B /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/upgrade_prematch_reviewed.py /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/manifest.json check --sha256 10afc86a3da97dd24ee961010433dd455b53e644469060049def20bfa906a7b7
```

After installation expect `upgraded`, `new_picks=false`, observation/labels unchanged,
and no pending journal. Observe the next scheduled tick separately; exit code 0 alone
is not proof of successful delivery. Protected output is proposed at
`/var/log/goalvision-prematch/discovery-output.log` (root:arvis 0640, directory 0750),
with existing daily logrotate, 8 MiB rotation-time threshold and 14 retained rotations.
The threshold is not a hard cap between checks. Required delivery facts are not clipped.

Compatible recovery (keeps new picks disabled; no database rollback):

```bash
sudo /home/arvis/GoalVisionAI/.venv/bin/python -E -B /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/upgrade_prematch_reviewed.py /home/arvis/goalvision-operations/prematch-reviewed-hardening-upgrade-v1-20260925/manifest.json recover --sha256 10afc86a3da97dd24ee961010433dd455b53e644469060049def20bfa906a7b7
```

If restoration fails, retain the recovery journal and start gates; review the failure
and use this same recovery command. Logs remain preserved. After upgrade, the same
pinned installer supports `disable-new-picks` and `disable-data-labels`; neither can
re-enable a disabled capability. Details/checksums are in the report and package.

Bounded history at `2026-09-25T19:50:22.920487+00:00`: no outstanding unreceipted claims,
unknown outcomes or acknowledged-unpersisted facts found; 53 confirmed singles and 8
combos, with three singles/one combo pending settlement. Registry 4 verified; observation
stores passed SQLite checks. Old discarded stdout limits negative evidence.
Real unresolved delivery, if found later, requires separate reviewed resolution and
blocks future re-enablement; safe settlement/observation should continue.

Later re-enable requires separate authorization, installed-release verification,
a verified scheduled no-send tick, protected readable/rotated output, refreshed delivery
history review, and fresh accepted publication decisions. No new model/threshold phase.

No sudo execution, deployment, service restart, manual cycle, Telegram message,
publication enablement, migration, push or merge occurred in this preparation.
