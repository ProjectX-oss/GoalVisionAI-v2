"""Build an inert, checksummed discovery-only package from a clean commit."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parents[2]
PACKAGE = Path('/home/arvis/goalvision-operations/prematch-odds-budget-20261001')
spec = importlib.util.spec_from_file_location('odds_update', Path(__file__).with_name('update.py'))
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)

def git(*args):
    return subprocess.check_output(['git', '-C', str(SOURCE), *args]).decode().strip()

if git('status', '--porcelain'):
    raise SystemExit('CLEAN_COMMIT_REQUIRED')
commit = git('rev-parse', 'HEAD')
for name in update.FILES:
    expected = subprocess.check_output(['git', '-C', str(SOURCE), 'show', 'fc4a740:' + name])
    if hashlib.sha256(expected).hexdigest() != update.sha(update.BASE / 'application' / name):
        raise SystemExit('BASE_MODULE_DIFFERS_FROM_REVIEWED_FC4A740:' + name)
PACKAGE.mkdir()  # never overwrite an existing operator package
shutil.copyfile(Path(__file__).with_name('update.py'), PACKAGE / 'update.py')
for name in update.FILES:
    target = PACKAGE / 'overlay' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE / name, target)
shutil.copyfile(SOURCE / 'docs/operations/PREMATCH_ODDS_PAGE_BUDGET_20261001.md',
                PACKAGE / 'RUNBOOK.md')
meta = dict(source_commit=commit, source_path=str(SOURCE), base_release=str(update.BASE),
            base_manifest=update.tree(update.BASE / 'application'),
            files={name:update.sha(PACKAGE / 'overlay' / name) for name in update.FILES},
            updater_sha256=update.sha(PACKAGE / 'update.py'),
            constraints=dict(manual_provider_calls=0, test_telegram_sends=0,
                             daily_results_reserve=100, maximum_requested_cycle_calls=400))
(PACKAGE / 'metadata.json').write_text(json.dumps(meta, sort_keys=True, indent=2) + '\n')
paths = sorted(p for p in PACKAGE.rglob('*') if p.is_file())
(PACKAGE / 'SHA256SUMS').write_text(''.join(
    update.sha(p) + '  ' + str(p.relative_to(PACKAGE)) + '\n' for p in paths))
update.validate(PACKAGE)
print('PACKAGE_VALIDATED=' + str(PACKAGE))
print('SOURCE_COMMIT=' + commit)
