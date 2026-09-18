# Future deployment and rollback plan — NOT EXECUTED

This plan accompanies the 2026-09-18 no-send audit. The audited implementation is
`0ceaa7d23f9a5f49cfa47247f7370eeb53986b09`. **It is not an authorization to deploy.**
The provider-readiness report determines whether the prerequisites below exist.
An absent prerequisite is a stop condition, not permission to invent an artifact,
bookmaker, timestamp, or successful smoke result.

## Paths and prerequisites

- Runtime/credentials: `/home/arvis/GoalVisionAI` (preserve `.env`).
- Accepted discovery imports: `/home/arvis/GoalVisionAI-throughput`, commit
  `0c4f316248e55f504b780cdef4e25165b800a779`; preserve this rollback checkout.
- Python: `/home/arvis/GoalVisionAI/.venv/bin/python`.
- Publication ledger: `/home/arvis/GoalVisionAI/var/lab_combo/ledger.db`.
- Proposed new runtime DB: `/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db`.
- Discovery unit: `goalvision-lab-v2-discover.service` / `.timer`.
- Existing settlement: `goalvision-lab-combo-settle.service` / `.timer`.
  Its current interpreter uses the main runtime checkout, not the throughput
  checkout. Do not silently replace it while deploying discovery.
- Proposed new units: `goalvision-live-lab.service` / `.timer`,
  `goalvision-adaptive-learning.service` / `.timer`. These are names for a future
  reviewed operator package; this audit neither supplies nor installs units.

Before any production cutover, supply a separately reviewed release addressing
all mandatory blockers. In particular, provide compatible, reviewed PREMATCH and
LIVE baseline artifacts, their known fingerprints and reproduction inputs; an
explicit common-quota settlement integration; and preflight accounting. The
current CLI alone cannot accomplish those missing integrations. Prepare reviewed
unit files and offline/no-send smoke scripts in an operator package. Do not
start LIVE when bookmaker or origin evidence remains unavailable.

The package paths below are **required future inputs, not files created by this
audit**. Requiring them explicitly makes the deployment sequence stop safely
until an operator has produced and reviewed them. The status preflight must be
included in conservative shared accounting before claiming strict cross-process
minute-limit guarantees. All provider consumers using the same account must
participate or have a separately bounded reservation; binding two workers alone
does not govern unbound clients.

## Command sequence for a separately authorized operator task

Run as `arvis` with approved sudo access, after all prerequisites have passed.
The environment variables must identify the reviewed release and package, never
credentials. No command below was executed by this audit.

```bash
set -euo pipefail
: "${GV_REVIEWED_SHA:?reviewed release commit required}"
: "${GV_OPERATOR_PACKAGE:?absolute reviewed operator package required}"
: "${GV_PREMATCH_ARTIFACT_FP:?reviewed embedded artifact fingerprint required}"
: "${GV_LIVE_ARTIFACT_FP:?reviewed embedded artifact fingerprint required}"
GV_BASE=/home/arvis/GoalVisionAI
GV_PY="$GV_BASE/.venv/bin/python"
GV_RELEASE="/home/arvis/GoalVisionAI-release-$GV_REVIEWED_SHA"
GV_DB="$GV_BASE/var/adaptive_lab/audit.db"
GV_LEDGER="$GV_BASE/var/lab_combo/ledger.db"
GV_BACKUP="/home/arvis/goalvision-deploy-backup-$(date -u +%Y%m%dT%H%M%SZ)"
export GV_PREMATCH_ARTIFACT_FP GV_LIVE_ARTIFACT_FP GV_DB GV_OPERATOR_PACKAGE
for item in prematch-bootstrap.json live-bootstrap.json bootstrap-reproduction.py offline-smoke.py live-no-send-smoke.py prematch-no-send-smoke.py combo-no-send-smoke.py verify-official-unchanged.py units/goalvision-lab-v2-discover.service units/goalvision-lab-combo-settle.service units/goalvision-live-lab.service units/goalvision-live-lab.timer units/goalvision-adaptive-learning.service units/goalvision-adaptive-learning.timer; do
  test -f "$GV_OPERATOR_PACKAGE/$item"
done
# The package must explicitly certify actual provider provenance and market mapping.
test -f "$GV_OPERATOR_PACKAGE/LIVE_PROVIDER_READY.reviewed"
umask 077
mkdir -p "$GV_BACKUP"
systemctl cat goalvision-lab-v2-discover.service goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.service goalvision-lab-combo-settle.timer > "$GV_BACKUP/units-effective.txt"
systemctl show goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer -p ActiveState -p UnitFileState > "$GV_BACKUP/timer-state.txt"
cp -a /etc/systemd/system/goalvision-lab-v2-discover.service /etc/systemd/system/goalvision-lab-v2-discover.timer /etc/systemd/system/goalvision-lab-combo-settle.service /etc/systemd/system/goalvision-lab-combo-settle.timer "$GV_BACKUP/"
git -C /home/arvis/GoalVisionAI-throughput rev-parse HEAD > "$GV_BACKUP/accepted-head.txt"
sha256sum "$GV_BASE/.env" "$GV_BACKUP/"*.service "$GV_BACKUP/"*.timer > "$GV_BACKUP/files.sha256"
# Stop only these required schedules; wait for in-flight executions to finish.
sudo systemctl stop goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer
while systemctl is-active --quiet goalvision-lab-v2-discover.service || systemctl is-active --quiet goalvision-lab-combo-settle.service; do sleep 5; done
export GV_BACKUP GV_LEDGER GV_BASE
"$GV_PY" - <<'PY'
import os, sqlite3
from pathlib import Path
source = Path(os.environ['GV_LEDGER'])
with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src:
    src.execute('PRAGMA query_only=ON')
    with sqlite3.connect(Path(os.environ['GV_BACKUP'])/'lab-ledger.db') as dst:
        src.backup(dst)
# The discovery shadow and analysis DBs also hold existing Lab evidence.
for relative, name in [('var/lab_v2/shadow.db','lab-v2-shadow.db'),
                       ('var/lab_combo/analysis.db','lab-analysis.db')]:
    source=Path(os.environ['GV_BASE'])/relative
    assert source.exists(), str(source)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src:
        src.execute('PRAGMA query_only=ON')
        with sqlite3.connect(Path(os.environ['GV_BACKUP'])/name) as dst:
            src.backup(dst)
# Inventory and back up every existing dedicated adaptive DB before migrating.
p=Path(os.environ['GV_DB'])
if p.exists():
    with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as src:
        src.execute('PRAGMA query_only=ON')
        with sqlite3.connect(Path(os.environ['GV_BACKUP'])/'adaptive-before.db') as dst:
            src.backup(dst)
PY
sha256sum "$GV_BACKUP/"*.db > "$GV_BACKUP/databases.sha256"
git -C "$GV_BASE" worktree add --detach "$GV_RELEASE" "$GV_REVIEWED_SHA"
export PYTHONPATH="$GV_RELEASE"
mkdir -p "$(dirname "$GV_DB")"
cd "$GV_BASE"
"$GV_PY" -P -m app.adaptive_lab.worker initialize --database "$GV_DB" --enable-lab-automation
# Reproduce BOTH reviewed baseline artifacts before activating either.
"$GV_PY" -P "$GV_OPERATOR_PACKAGE/bootstrap-reproduction.py"
"$GV_PY" -P - <<'PY'
import json,os
from pathlib import Path
from datetime import datetime,timezone
from app.adaptive_lab.models import validate_artifact
from app.adaptive_lab.repository import AuditRepository
from app.adaptive_lab.governance import Governance
repo=AuditRepository(os.environ['GV_DB'])
try:
    artifacts=[]
    for stream in ('PREMATCH','LIVE'):
        a=json.loads((Path(os.environ['GV_OPERATOR_PACKAGE'])/(stream.lower()+'-bootstrap.json')).read_text())
        validate_artifact(a)
        assert a['stream']==stream
        assert a['artifact_fingerprint']==os.environ['GV_'+stream+'_ARTIFACT_FP']
        assert repo.champion(stream) is None
        artifacts.append(a)
    with repo.transaction():
        for a in artifacts: Governance(repo).bootstrap(a,now=datetime.now(timezone.utc))
    assert list(repo.connection.execute('PRAGMA foreign_key_check'))==[]
    assert repo.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
finally: repo.close()
PY
# PREMATCH --adaptive-database and LIVE --database must resolve to GV_DB.
# Reviewed settlement integration must bind SharedQuota and SETTLEMENT category.
# No-send scripts must copy source evidence into scratch DBs, construct no Telegram
# transport, use bounded current provider requests, and never train real models.
"$GV_PY" -P "$GV_OPERATOR_PACKAGE/offline-smoke.py"
"$GV_PY" -P "$GV_OPERATOR_PACKAGE/live-no-send-smoke.py"
"$GV_PY" -P "$GV_OPERATOR_PACKAGE/prematch-no-send-smoke.py"
"$GV_PY" -P "$GV_OPERATOR_PACKAGE/combo-no-send-smoke.py"
"$GV_PY" -P "$GV_OPERATOR_PACKAGE/verify-official-unchanged.py"
# Unit review must confirm exact release PYTHONPATH and common DB, existing LAB
# destination only, bounded calls, and no Official service changes.
sudo install -m 0644 "$GV_OPERATOR_PACKAGE/units/goalvision-lab-v2-discover.service" /etc/systemd/system/
sudo install -m 0644 "$GV_OPERATOR_PACKAGE/units/goalvision-lab-combo-settle.service" /etc/systemd/system/
sudo install -m 0644 "$GV_OPERATOR_PACKAGE/units/goalvision-live-lab.service" "$GV_OPERATOR_PACKAGE/units/goalvision-live-lab.timer" /etc/systemd/system/
sudo install -m 0644 "$GV_OPERATOR_PACKAGE/units/goalvision-adaptive-learning.service" "$GV_OPERATOR_PACKAGE/units/goalvision-adaptive-learning.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer
sudo systemctl enable --now goalvision-live-lab.timer goalvision-adaptive-learning.timer
systemctl list-timers goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer goalvision-live-lab.timer goalvision-adaptive-learning.timer --all
systemctl show goalvision-live-lab.timer goalvision-adaptive-learning.timer -p NextElapseUSecRealtime -p ActiveState -p UnitFileState
"$GV_PY" -P -m app.adaptive_lab live status --database "$GV_DB" --json
"$GV_PY" -P -m app.adaptive_lab learning champion --database "$GV_DB" --json
"$GV_PY" -P -m app.adaptive_lab live champion --database "$GV_DB" --json
# Read new publication receipts to verify the fixed existing LAB chat only.
# Inspect unknown claims; never resend merely because a receipt is absent.
```

Back up the existing Lab V2 discovery evidence DB(s), in addition to the ledger,
using the same SQLite backup procedure after inventorying the actual runtime
`var/lab_v2` database paths. Record their hashes. Do not copy a live SQLite
main file alone while ignoring its WAL. Official databases require no migration.
The sequence remains conditional: there is no safe turnkey production command
that can create currently missing reviewed model/provider capability.

## Emergency rollback commands

Use the backup directory recorded during that deployment. For provider failure,
artifact failure, adaptive DB failure, quota failure, or a publication anomaly,
contain new work first and preserve every evidence/claim database:

```bash
set -euo pipefail
: "${GV_BACKUP:?deployment backup directory required}"
sudo systemctl stop goalvision-live-lab.timer goalvision-adaptive-learning.timer
sudo systemctl disable goalvision-live-lab.timer goalvision-adaptive-learning.timer
sudo systemctl stop goalvision-live-lab.service goalvision-adaptive-learning.service
# If adaptive PREMATCH behavior or shared quota is implicated, restore accepted units.
sudo systemctl stop goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer
while systemctl is-active --quiet goalvision-lab-v2-discover.service || systemctl is-active --quiet goalvision-lab-combo-settle.service; do sleep 5; done
sudo install -m 0644 "$GV_BACKUP/goalvision-lab-v2-discover.service" /etc/systemd/system/
sudo install -m 0644 "$GV_BACKUP/goalvision-lab-v2-discover.timer" /etc/systemd/system/
sudo install -m 0644 "$GV_BACKUP/goalvision-lab-combo-settle.service" /etc/systemd/system/
sudo install -m 0644 "$GV_BACKUP/goalvision-lab-combo-settle.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer
systemctl is-enabled goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer
systemctl is-active goalvision-lab-v2-discover.timer goalvision-lab-combo-settle.timer
git -C /home/arvis/GoalVisionAI-throughput rev-parse HEAD
```

- **LIVE failure only:** stop/disable the new LIVE timer/service; PREMATCH and
  combo can continue if their registry/quota integrity is unaffected.
- **Adaptive DB failure:** detach adaptive PREMATCH integration by restoring the
  accepted unit. Preserve corrupt DB, WAL and SHM for forensic recovery; rebuild
  in a new path from a verified backup plus later append-only evidence. Do not
  overwrite current forward history with an older backup.
- **Quota failure:** stop new API consumers, restore accepted workers, inspect
  real provider headers. Do not reset durable counters to regain allowance.
- **Artifact failure:** a verified predecessor permits `Governance.rollback` with
  an actual failing input incident; it recomputes the failure. With no verified
  predecessor, publication remains blocked. Never synthesize an incident or edit
  champion pointers by SQL. Restore the accepted service as above if needed.
- **Telegram anomaly:** stop the new publisher immediately. In-flight or unknown
  claims require reconciliation against actual Lab receipts; do not automatically
  retry. Retain predictions, claims, results and losses. Official services,
  destinations and bankrolls remain untouched.

Expected first bootstrap has `previous_generation=None`; rollback to the accepted
non-registry baseline is an operator service rollback, not a model-pointer action.
After a later promotion, the first registered artifact becomes the retained
verified predecessor. Distinguish these two rollback mechanisms.
