"""Operator-only installation of new ADMIN files; never pause or edit PREMATCH."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import pwd
import shutil
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reviewed-install-disabled-sender', action='store_true', required=True)
    parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run only in a separately approved root operator session; no sudo escalation is attempted.')
    root = Path(__file__).resolve().parent
    if subprocess.run(['/usr/bin/python3', '-I', str(root/'package_check.py')], check=False).returncode:
        raise SystemExit('Package or loaded-state drift blocks installation; do not refresh PREMATCH manifests.')
    account = pwd.getpwnam('goalvision-admin-alerts')
    target = Path('/opt/goalvision-admin-alerts')
    config = Path('/etc/goalvision-admin-alerts')
    unit_root = Path('/etc/systemd/system')
    units = ('goalvision-admin-alerts.service', 'goalvision-admin-alerts.timer')
    if target.exists() or config.exists() or any((unit_root/name).exists() for name in units):
        raise SystemExit('An ADMIN installation already exists. Review/resume manually; never overwrite it.')
    # Paths to which the operator must grant dedicated read access before installation.
    for source in ('/var/log/goalvision-prematch/discovery-output.log',
                   '/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db',
                   '/home/arvis/GoalVisionAI/var/lab_combo/ledger.db'):
        subprocess.run(['/usr/sbin/runuser', '-u', account.pw_name, '--', '/usr/bin/test', '-r', source], check=True)
    shutil.copytree(root, target, ignore=shutil.ignore_patterns('__pycache__'))
    config.mkdir(mode=0o750)
    os.chown(config, 0, account.pw_gid)
    shutil.copyfile(root/'admin-alerts.json', config/'admin-alerts.json')
    os.chown(config/'admin-alerts.json', 0, account.pw_gid)
    os.chmod(config/'admin-alerts.json', 0o640)
    for name in units:
        shutil.copyfile(root/name, unit_root/name)
        os.chmod(unit_root/name, 0o644)
    os.chmod(target/'disable-admin-alerts', 0o755)
    # Loaded-state drift was checked for ALL loaded services/timers, not only PREMATCH.
    subprocess.run(['/usr/bin/systemctl', 'daemon-reload'], check=True)
    subprocess.run(['/usr/bin/systemctl', 'enable', '--now', 'goalvision-admin-alerts.timer'], check=True)
    print('ADMIN timer installed with sender disabled. No PREMATCH control command was executed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
