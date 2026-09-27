"""Build inert application payloads, exact configuration proposals and rollback bytes.

No installation, systemd administration, DB access, credential reads or networking.
The source commit must already be committed. Output directories are never reused.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

BASE = '23e57e9c48f321b8ee5f67bd536fbb2b264f6cb0'
RESEARCH_BASE = '363f567'
ADMIN_BASE = 'd811177fdd11e25b087f036584d33c0e0328906b'
RESEARCH_FILES = tuple('app/adaptive_lab/'+name for name in
    ('repository.py', 'observations.py', 'automl.py', 'governance.py', 'prepared.py'))
ALLOWED = {*RESEARCH_FILES, 'app/adaptive_lab/quota.py', 'app/adaptive_lab/weekly.py',
           'app/football/client.py', 'app/lab_v2_shadow/runner.py', 'app/lab_v2_shadow/cli.py'}
SERVICES = ('goalvision-lab-v2-discover.service', 'goalvision-lab-combo-settle.service',
            'goalvision-adaptive-learning-observer.service', 'goalvision-lab-weekly-stats.service')
ACCEPTED_PACKAGE = Path('/home/arvis/goalvision-operations/lab-v2-public-message-upgrade-v2-20260926')


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', *args])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def files_at(commit: str) -> dict[str, bytes]:
    data = git('archive', commit, 'app', 'requirements.txt')
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        return {member.name: archive.extractfile(member).read() for member in archive if member.isfile()}


def write_tree(root: Path, values: dict[str, bytes]) -> None:
    for name, data in values.items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--admin-commit', required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    commit = git('rev-parse', args.commit).decode().strip()
    research_base = git('rev-parse', RESEARCH_BASE).decode().strip()
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, commit], check=True)
    baseline = files_at(BASE)
    application = files_at(commit)
    changed = sorted(k for k in baseline.keys() | application.keys() if baseline.get(k) != application.get(k))
    if set(changed) != ALLOWED:
        raise ValueError('UNREVIEWED_APPLICATION_FILES')
    research_original = files_at(research_base)
    research = {**research_original, **{k: application[k] for k in RESEARCH_FILES}}
    for name, data in research_original.items():
        assert (Path('/home/arvis/GoalVisionAI-prematch-release-363f567')/name).read_bytes() == data
    for name, data in baseline.items():
        assert (Path('/home/arvis/GoalVisionAI-prematch-release-public-message-v2-20260926')/name).read_bytes() == data
    for name in ('app/adaptive_lab/policy.py', 'app/adaptive_lab/models.py', 'app/lab_v2_shadow/quota.py'):
        assert baseline[name] == application[name]
        assert research_original[name] == research[name]
    admin = git('diff', ADMIN_BASE, args.admin_commit, '--', 'app/admin_alerts/rules.py')
    assert git('diff', '--name-only', ADMIN_BASE, args.admin_commit, '--', 'app').decode().splitlines() == ['app/admin_alerts/rules.py']
    accepted = json.loads((ACCEPTED_PACKAGE/'manifest.json').read_text())
    configuration = []
    output.mkdir()
    write_tree(output/'application', application)
    write_tree(output/'research', research)
    write_tree(output, {'verify_package.py': git('show', commit+':operations/quota-hardening/verify_package.py'),
                        'REVIEW.md': git('show', commit+':operations/quota-hardening/REVIEW.md')})
    write_tree(output, {'release.env': ('PYTHONPATH='+str(output/'application')+'\n').encode(),
                       'research.env': ('PYTHONPATH='+str(output/'research')+'\n').encode(),
                       'admin-code-mapping.patch': admin})
    for service in SERVICES:
        target = Path('/etc/systemd/system')/(service+'.d')/'90-reviewed-prematch-v2.conf'
        reviewed = ACCEPTED_PACKAGE/(service+'.proposed')
        before = reviewed.read_bytes()
        assert sha(before) == accepted['payload_sha256'][str(reviewed)]
        assert target.read_bytes() == before
        after = before.replace(str(ACCEPTED_PACKAGE/'release.env').encode(), str(output/'release.env').encode())
        assert before != after
        write_tree(output/'configuration', {service+'.before': before, service+'.proposed': after})
        configuration.append({'service': service, 'target': str(target), 'before_sha256': sha(before),
                              'after_sha256': sha(after), 'before': 'configuration/'+service+'.before',
                              'after': 'configuration/'+service+'.proposed'})
    service = 'goalvision-adaptive-learning.service'
    target = Path('/etc/systemd/system')/(service+'.d')/'90-quota-lock-hardening.conf'
    assert not target.exists()
    after = ('[Service]\nEnvironmentFile=\nEnvironmentFile='+str(output/'research.env')+'\n').encode()
    write_tree(output/'configuration', {service+'.proposed': after})
    configuration.append({'service': service, 'target': str(target), 'before_sha256': None,
                          'before': None, 'after_sha256': sha(after),
                          'after': 'configuration/'+service+'.proposed'})
    manifest = {'version': 1, 'purpose': 'PREPARED_ONLY_NO_AUTOMATIC_INSTALLATION',
                'application_base': BASE, 'application_commit': commit,
                'research_base': research_base, 'research_overlay_files': list(RESEARCH_FILES),
                'admin_base': ADMIN_BASE, 'admin_mapping_commit': args.admin_commit,
                'application_changed_files': changed, 'configuration': configuration,
                'source_hashes': {'application': {n: sha(v) for n,v in baseline.items()},
                                  'research': {n: sha(v) for n,v in research_original.items()}},
                'policy_model_schema_timer_changes': False, 'publication_state_preserved': True,
                'rollback_drain_seconds': 60, 'live_database_restore': False,
                'files': {str(p.relative_to(output)): sha(p.read_bytes()) for p in output.rglob('*') if p.is_file()}}
    (output/'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)+'\n')
    print(json.dumps({'package': str(output), 'manifest_sha256': sha((output/'manifest.json').read_bytes()),
                      'application_commit': commit, 'files': len(manifest['files'])}, sort_keys=True))


if __name__ == '__main__':
    main()
