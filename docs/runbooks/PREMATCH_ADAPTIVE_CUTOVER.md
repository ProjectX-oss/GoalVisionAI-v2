# Controlled PREMATCH cutover and rollback (NOT executed by the audit)

Only an operator with approved root access may execute this sequence. Use the final release SHA from the signed-off audit report, never a mutable scratch checkout as the service import path. All acceptance gates must pass first. Do not enable any LIVE unit. Existing Lab destinations and normal sending behavior are retained; never send an artificial pick.

The commands below run as arvis except those explicitly prefixed with sudo. `sudo -v` requires the operator's existing authentication, not a password supplied to an AI session. If a command or smoke fails, stop and use the rollback block; do not resume send timers.

## Prepare while current timers continue running

```bash
set -euo pipefail
cd /home/arvis/GoalVisionAI
RELEASE_COMMIT=$(sed -n 's/^FINAL RELEASE COMMIT: //p' /home/arvis/goalvision_prematch_full_quality_autolearning_review.txt | head -1)
test "${#RELEASE_COMMIT}" -eq 40
git cat-file -e "$RELEASE_COMMIT^{commit}"
RELEASE=/home/arvis/GoalVisionAI-prematch-release-$RELEASE_COMMIT
BACKUP=/home/arvis/goalvision-prematch-cutover-backup-$RELEASE_COMMIT
PY=/home/arvis/GoalVisionAI/.venv/bin/python
DB=/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db
sudo -v
# A fresh stable detached release; do not repurpose an existing checkout.
test ! -e "$RELEASE"
test ! -e "$BACKUP"
git worktree add --detach "$RELEASE" "$RELEASE_COMMIT"
mkdir -m 700 "$BACKUP"
export RELEASE BACKUP PY DB
# Preserve effective units and all installed GoalVision files.
systemctl cat goalvision-lab-v2-discover.service goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.service goalvision-lab-combo-settle.timer > "$BACKUP/effective-units.txt"
systemctl show goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer > "$BACKUP/timer-state.txt"
# This reviewed replacement procedure assumes the audited units have no drop-ins.
test -z "$(systemctl show goalvision-lab-v2-discover.service -p DropInPaths --value)"
test -z "$(systemctl show goalvision-lab-combo-settle.service -p DropInPaths --value)"
cp -a /etc/systemd/system/goalvision* "$BACKUP/"
sha256sum /etc/systemd/system/goalvision* /home/arvis/GoalVisionAI/.env > "$BACKUP/hashes-before.txt"
git -C /home/arvis/GoalVisionAI-throughput rev-parse HEAD > "$BACKUP/rollback-head.txt"
git -C /home/arvis/GoalVisionAI-throughput diff --binary > "$BACKUP/rollback-tracked.patch"
test "$(cat "$BACKUP/rollback-head.txt")" = 0c4f316248e55f504b780cdef4e25165b800a779
# Existing adaptive units/configuration require a separately reviewed upgrade procedure.
test ! -e /etc/goalvision-prematch-release.conf
test ! -e /etc/systemd/system/goalvision-adaptive-learning.service
test ! -e /etc/systemd/system/goalvision-adaptive-learning-observer.service
test ! -e /etc/systemd/system/goalvision-lab-weekly-stats.service
# SQLite online backup, never raw-copy a database with an active WAL.
"$PY" - <<'PY'
import os,sqlite3
from pathlib import Path
root=Path('/home/arvis/GoalVisionAI');out=Path(os.environ['BACKUP'])
for name,relative in [('shadow.db','var/lab_v2/shadow.db'),('ledger.db','var/lab_combo/ledger.db'),('analysis.db','var/lab_combo/analysis.db'),('adaptive-before.db','var/adaptive_lab/audit.db')]:
    path=root/relative
    if not path.exists():continue
    source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);source.execute('PRAGMA query_only=ON')
    destination=sqlite3.connect(out/name);source.backup(destination)
    assert destination.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    destination.close();source.close()
PY
sha256sum "$BACKUP"/*.db > "$BACKUP/database-hashes.txt"
# Build reviewed replacements in backup workspace before touching installed units.
"$PY" - <<'PY'
import os
from pathlib import Path
b=Path(os.environ['BACKUP']);release=os.environ['RELEASE'];py=os.environ['PY'];db=os.environ['DB']
for name,module,arguments in [('goalvision-lab-v2-discover.service','app.lab_v2_shadow','controlled-cycle --send --max-calls 400 --daily-reserve 1500'),('goalvision-lab-combo-settle.service','app.lab_combo','settle --send')]:
    old=(b/name).read_text();lines=[]
    for line in old.splitlines():
        if line.startswith('Environment=PYTHONPATH='):continue
        if line.startswith('ExecStart='):
            lines.append('EnvironmentFile=/etc/goalvision-prematch-release.conf')
            line=f'ExecStart={py} -P -m {module} {arguments} --adaptive-database {db}'
        lines.append(line)
    (b/('new-'+name)).write_text('\n'.join(lines)+'\n')
(b/'release.conf').write_text('PYTHONPATH='+release+'\n')
PY
```

Check the replacement unit diff before cutover. It must change only import-path isolation and the PREMATCH adaptive DB flag; same runtime, interpreter, Lab destinations, send policy, safety reserve and limits. Both settlement and discovery must share this DB. No `.env` edits.

## Short cutover; keep sending paused until smoke passes

```bash
sudo systemctl stop goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer
# Wait for running oneshots; do not kill an in-flight Telegram publication.
while systemctl is-active --quiet goalvision-lab-v2-discover.service || systemctl is-active --quiet goalvision-lab-combo-settle.service; do sleep 2; done
mkdir -p /home/arvis/GoalVisionAI/var/adaptive_lab
chmod 700 /home/arvis/GoalVisionAI/var/adaptive_lab
export PYTHONPATH="$RELEASE"
# Constructor migrates the dedicated DB to schema 4, with foreign keys/guards.
"$PY" -P -m app.adaptive_lab.prematch bootstrap --database "$DB" --json > "$BACKUP/bootstrap.json"
"$PY" -P -m app.adaptive_lab.prematch observe --database "$DB" --json > "$BACKUP/initial-observer.json"
# Must show EXISTING_PREMATCH_BASELINE_V1; never train a replacement at bootstrap.
"$PY" -P - <<'PY'
import os
from pathlib import Path
from app.adaptive_lab.repository import AuditRepository
from app.adaptive_lab.models import validate_artifact
r=AuditRepository(Path(os.environ['DB']),readonly=True)
assert r.champion('LIVE') is None
champion=r.champion('PREMATCH');a=r.get('model_artifacts',champion['artifact_id'])
validate_artifact(a);assert a['family']=='EXISTING_PREMATCH_BASELINE_V1'
assert list(r.connection.execute('PRAGMA foreign_key_check'))==[]
assert r.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
r.close()
PY
sudo install -m 644 "$BACKUP/release.conf" /etc/goalvision-prematch-release.conf
sudo install -m 644 "$BACKUP/new-goalvision-lab-v2-discover.service" /etc/systemd/system/goalvision-lab-v2-discover.service
sudo install -m 644 "$BACKUP/new-goalvision-lab-combo-settle.service" /etc/systemd/system/goalvision-lab-combo-settle.service
sudo install -m 644 "$RELEASE"/app/adaptive_lab/systemd/goalvision-adaptive-learning* /etc/systemd/system/
sudo install -m 644 "$RELEASE"/app/adaptive_lab/systemd/goalvision-lab-weekly-stats.* /etc/systemd/system/
sudo systemctl daemon-reload
# NO --send. New scratch evidence DB and cache; source ledger/analysis copies.
mkdir -m 700 "$BACKUP/smoke"
"$PY" -P -m app.lab_v2_shadow rehearse --max-calls 30 --horizon-days 1 --daily-reserve 1500 --shadow-database "$BACKUP/smoke/shadow.db" --analysis-database "$BACKUP/analysis.db" --ledger "$BACKUP/ledger.db" --capability-cache "$BACKUP/smoke/capabilities.json" --adaptive-database "$DB" > "$BACKUP/no-send-smoke.json"
# Re-run exact accepted-signal equivalence in an isolated test runtime.
(cd "$RELEASE" && "$PY" -m pytest -q tests/adaptive_lab/test_prematch_autonomy.py -k 'baseline_exact_equivalence or registry_matches_golden') > "$BACKUP/equivalence.txt"
"$PY" -P -m app.adaptive_lab.prematch status --database "$DB" --json > "$BACKUP/health-before-send.json"
# Preview only: current publication-week SINGLE/COMBO totals, no transport or claim.
"$PY" -P -m app.adaptive_lab.weekly_cli --database "$DB" > "$BACKUP/weekly-preview.json"
systemd-analyze calendar 'Sun *-*-* 22:30:00 Europe/Riga'
```

Review no-send output: no terminal error, no publication, no Telegram transport/send, LIVE absent, champion provenance correct, exact equivalence passed. A quota-stopped run is not proof of a successful evaluation; wait for adequate safe quota and rerun while sending remains paused, or roll back. Do not lower reserves. Verify combo result images still resolve from the unchanged runtime and the settlement regression test has passed. Compare `.env`, Official configuration and rollback checkout hashes to pre-cutover values. The automated task must never execute the restore block below before these checks pass.

## Restore only normal existing Lab send behavior

```bash
sudo systemctl start goalvision-adaptive-learning-observer.service
sudo systemctl enable --now goalvision-adaptive-learning-observer.timer goalvision-adaptive-learning.timer goalvision-lab-weekly-stats.timer
sudo systemctl enable --now goalvision-lab-combo-settle.timer goalvision-lab-v2-discover.timer
systemctl show goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer goalvision-adaptive-learning-observer.timer goalvision-adaptive-learning.timer goalvision-lab-weekly-stats.timer -p Id -p UnitFileState -p ActiveState -p LastTriggerUSec -p NextElapseUSecRealtime
systemctl show goalvision-live-lab.timer -p LoadState -p UnitFileState -p ActiveState
"$PY" -P -m app.adaptive_lab.prematch status --database "$DB" --json
```

Verify PUBLICATION WINDOW 09:00–23:00 Europe/Riga, CURRENT WINDOW, NEXT OPEN and NEXT CLOSE, both new-bet blockers (LAB_PUBLICATION_WINDOW_CLOSED and FIXTURE_AFTER_LAB_CUTOFF), and the weekly timer's next Sunday 22:30 Europe/Riga trigger. Do not manually start the sending weekly service as a test. Observe the next natural discovery/settlement/observer triggers and immutable receipts. No test pick, no forced selection. Observer cadence `*:0/30`, daily research `04:15`, system timezone. If no ready market exists, silence is correct only with explicit healthy or degraded coverage diagnostics. Once deployed and these checks pass, ordinary learning needs no manual research/settlement/promotion command; infrastructure failures still require operational repair.

## Exact emergency rollback

Use the same `BACKUP` from the cutover, not a different historical backup. This restores previous discovery code in NO-SEND mode and the previous settlement command because both use shared quota in the new release. Preserve adaptive evidence and published source ledgers. Never restore an older ledger DB over newer real results.

```bash
set -euo pipefail
# Set BACKUP to the exact directory recorded for the active release.
test -f "$BACKUP/goalvision-lab-v2-discover.service"
test -f "$BACKUP/goalvision-lab-combo-settle.service"
sudo systemctl disable --now goalvision-adaptive-learning-observer.timer goalvision-adaptive-learning.timer goalvision-lab-weekly-stats.timer
sudo systemctl stop goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer
while systemctl is-active --quiet goalvision-lab-v2-discover.service || systemctl is-active --quiet goalvision-lab-combo-settle.service || systemctl is-active --quiet goalvision-adaptive-learning-observer.service || systemctl is-active --quiet goalvision-adaptive-learning.service || systemctl is-active --quiet goalvision-lab-weekly-stats.service; do sleep 2; done
# The old baseline has no Riga cutoff: restore it in analysis-only mode.
"$PY" - <<'PY'
import os
from pathlib import Path
b=Path(os.environ['BACKUP'])
s=(b/'goalvision-lab-v2-discover.service').read_text()
lines=[line.replace(' --send','') if line.startswith('ExecStart=') else line for line in s.splitlines()]
(b/'rollback-discovery-no-send.service').write_text('\n'.join(lines)+'\n')
PY
sudo install -m 644 "$BACKUP/rollback-discovery-no-send.service" /etc/systemd/system/goalvision-lab-v2-discover.service
sudo install -m 644 "$BACKUP/goalvision-lab-combo-settle.service" /etc/systemd/system/goalvision-lab-combo-settle.service
sudo systemctl daemon-reload
sudo systemctl enable --now goalvision-lab-combo-settle.timer goalvision-lab-v2-discover.timer
systemctl show goalvision-lab-v2-discover.service goalvision-lab-combo-settle.service -p ExecStart -p Environment -p WorkingDirectory
systemctl show goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer -p ActiveState -p UnitFileState -p NextElapseUSecRealtime
sha256sum /home/arvis/GoalVisionAI/.env
# Leave /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db and release checkout intact.
```

* Adaptive DB or shared-quota failure: use full integration rollback above. Do not bypass quota claims in the new release.
* Model artifact failure: automatic verified-predecessor rollback is attempted; if none is valid, fail closed and use integration rollback. Do not edit artifact rows or drop guards.
* Telegram anomaly: stop the discovery timer first, wait for in-flight sends, inspect immutable claim/receipt status; never replay an ambiguous send automatically. Preserve source ledger and settle existing published picks. Resume only after duplicate/destination integrity is established.
* LIVE engine failure: no LIVE engine is deployed by this release. Keep its timer absent/disabled/inactive; do not invoke its CLI.

The audit can rehearse file transformation/restoration in a disposable directory, but that is not a production systemd rollback test. Do not report an actual cutover/rollback unless it occurred.

The old accepted checkout does not enforce the new night cutoff. The rollback sequence therefore keeps discovery/analysis scheduled but removes --send. Settlement messages continue. Resume new-bet sending only on a reviewed release with the cutoff guard; never claim the old baseline enforces this newly added rule.
