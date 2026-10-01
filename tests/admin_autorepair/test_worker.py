import hashlib
import json
import os
import shlex
from pathlib import Path
import subprocess
import threading
import time

import pytest

from app.admin_alerts.autorepair import bundle
from app.admin_alerts.model import DISCOVERY
from app.admin_autorepair import worker
from app.admin_autorepair.protocol import atomic_json, validate_status


def run_git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL)


@pytest.fixture
def source(tmp_path):
    root = tmp_path/'source'
    root.mkdir()
    run_git(root, 'init', '-q')
    (root/'code.py').write_text('VALUE = 1\n')
    (root/'producer.db').write_bytes(b'untracked synthetic producer state')
    run_git(root, 'add', 'code.py')
    run_git(root, '-c', 'user.name=Test', '-c', 'user.email=test@invalid', 'commit', '-qm', 'fixture')
    return root


def source_hash(root):
    h = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_file():
            h.update(str(path.relative_to(root)).encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def queue(spool, mode='FIX_ALLOWED'):
    value = bundle({'id': 'a'*24, 'episode': 1, 'generation': 1, 'service': DISCOVERY,
        'rule': 'AUTH_FAILURE' if mode == 'DIAGNOSE_ONLY' else 'DATABASE_LOCK', 'severity': 2,
        'invocation': 'UNKNOWN', 'object_id': 'pipeline', 'evidence': '{}'}, time.time())
    atomic_json(spool/'queue'/(value['job_id']+'.json'), value)
    return value


def fake(tmp_path, action='patch'):
    executable = tmp_path/'fake-codex'
    executable.write_text('''#!/usr/bin/python3
import pathlib, sys, time, subprocess, signal
if '--help' in sys.argv:
    print('--approve-for-me --ignore-user-config --ignore-rules --ephemeral')
    raise SystemExit(0)
assert '--sandbox' in sys.argv and any(mode in sys.argv for mode in ('workspace-write','read-only'))
assert '--approve-for-me' in sys.argv
assert '--ephemeral' in sys.argv
assert 'sandbox_workspace_write.network_access=false' in sys.argv
prompt = sys.stdin.read()
assert 'no production' not in prompt or prompt
assert 'DIAGNOSE_ONLY' in prompt and 'NO_CODE_FIX' in prompt
pathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text('synthetic final SECRET_TEXT')
''' + {
        'patch': "pathlib.Path('code.py').write_text('VALUE = 2\\n')\npathlib.Path('new.py').write_text('NEW = True\\n')\n",
        'none': 'pass\n',
        'fail': 'raise SystemExit(9)\n',
        'whitespace': "pathlib.Path('code.py').write_text('VALUE = 2  \\n')\n",
        'ignored': "pathlib.Path('.git/info/exclude').write_text('hidden\\n')\npathlib.Path('hidden').write_text('bad')\n",
        'sleep': "child = subprocess.Popen(['/usr/bin/python3', '-c', 'import time; time.sleep(100)'])\npathlib.Path('child.pid').write_text(str(child.pid))\ntime.sleep(100)\n",
        'brief': 'time.sleep(.6)\n',
    }[action])
    executable.chmod(0o755)
    return executable


def config(spool, source, executable, **kw):
    return worker.Config(source_repos={'ADMIN':str(source), 'PREMATCH':str(source)},
        spool=str(spool), codex=str(executable), heartbeat_seconds=.05, **kw)


@pytest.mark.parametrize('action,outcome,state', [
    ('patch','PATCH_READY','COMPLETED'), ('none','NO_CODE_CHANGE','COMPLETED'),
    ('fail','CODEX_FAILED','FAILED'), ('whitespace','CODEX_FAILED','FAILED')])
def test_worker_result_and_source_untouched(spool, source, tmp_path, action, outcome, state):
    value = queue(spool)
    before = source_hash(source)
    result = worker.run_once(config(spool, source, fake(tmp_path, action)))
    assert result['outcome'] == outcome
    assert result['state'] == state
    assert source_hash(source) == before
    assert (source/'producer.db').read_bytes() == b'untracked synthetic producer state'
    assert (spool/'done'/(value['job_id']+'.json')).exists()
    assert not list((spool/'running').iterdir())
    directory = spool/'jobs'/value['job_id']
    assert (directory/'final-message.txt').exists()
    assert 'SECRET_TEXT' not in json.dumps(result)
    clone = directory/'clone'
    assert not (clone/'producer.db').exists()
    assert not run_git(clone, 'remote')
    assert run_git(clone, 'rev-parse', 'HEAD') == run_git(source, 'rev-parse', 'HEAD')
    assert worker.run_once(config(spool, source, fake(tmp_path)))['state'] == 'IDLE'
    if action == 'patch':
        assert result['changed_files'] == 2
        assert result['diff_check'] == 'PASS'
        assert b'new.py' in (directory/'result.patch').read_bytes()
        assert b'VALUE = 2' in (directory/'result.patch').read_bytes()


@pytest.mark.parametrize('action,expected', [('none','DIAGNOSIS_ONLY'), ('patch','CODEX_FAILED'), ('ignored','CODEX_FAILED')])
def test_diagnose_read_only_enforced_by_result(spool, source, tmp_path, action, expected):
    value = queue(spool, 'DIAGNOSE_ONLY')
    before = source_hash(source)
    result = worker.run_once(config(spool, source, fake(tmp_path, action)))
    invocation = json.loads((spool/'jobs'/value['job_id']/'invocation.json').read_text())
    sandbox_index = invocation['argv'].index('--sandbox') + 1
    assert invocation['argv'][sandbox_index] == 'read-only'
    assert result['outcome'] == expected
    assert source_hash(source) == before
    assert not (spool/'jobs'/value['job_id']/'result.patch').exists()
    if expected == 'CODEX_FAILED':
        assert result['failure'] == 'DIAGNOSE_EDIT'


def test_timeout_kills_descendant(spool, source, tmp_path):
    value = queue(spool)
    started = time.monotonic()
    result = worker.run_once(config(spool, source, fake(tmp_path, 'sleep'), timeout_seconds=.5))
    assert result['outcome'] == 'TIMEOUT'
    assert time.monotonic()-started < 8
    pid = int((spool/'jobs'/value['job_id']/'clone'/'child.pid').read_text())
    stat = Path(f'/proc/{pid}/stat')
    assert not stat.exists() or stat.read_text().split()[2] == 'Z'


def test_heartbeat_progression_and_no_overlap(spool, source, tmp_path, monkeypatch):
    value = queue(spool)
    conf = config(spool, source, fake(tmp_path, 'brief'))
    history = []
    original = worker.publish
    def observe(root, status):
        original(root, status)
        history.append(dict(status))
    monkeypatch.setattr(worker, 'publish', observe)
    results = []
    thread = threading.Thread(target=lambda: results.append(worker.run_once(conf)))
    thread.start()
    for _ in range(100):
        if history:
            break
        time.sleep(.01)
    assert worker.run_once(conf)['state'] == 'BUSY'
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert results[0]['state'] == 'COMPLETED'
    assert history[0]['state'] == 'STARTED'
    assert sum(x['state'] == 'RUNNING' for x in history) >= 2
    assert history[-1]['state'] == 'COMPLETED'
    assert [x['sequence'] for x in history] == list(range(1, len(history)+1))
    for status in history:
        validate_status(status, value)


def test_interrupted_worker_is_not_replayed(spool, source, tmp_path):
    value = queue(spool)
    name = value['job_id']+'.json'
    (spool/'queue'/name).rename(spool/'running'/name)
    conf = config(spool, source, fake(tmp_path, 'patch'))
    assert worker.run_once(conf)['state'] == 'IDLE'
    status = json.loads((spool/'status'/name).read_text())
    assert status['failure'] == 'WORKER_INTERRUPTED'
    assert not list((spool/'jobs').iterdir())
    assert (spool/'done'/name).exists()


def test_environment_has_no_inherited_credentials(monkeypatch):
    monkeypatch.setenv('TELEGRAM_TOKEN', 'secret')
    monkeypatch.setenv('API_KEY', 'secret')
    assert 'secret' not in str(worker.environment())
    assert 'TELEGRAM_TOKEN' not in worker.environment()


def test_bare_snapshot_and_no_hardlinks(spool, source, tmp_path):
    value=queue(spool)
    bare=tmp_path/'reviewed.git'
    original=source_hash(source)
    subprocess.run(['git','clone','--bare','--local','--no-hardlinks',str(source),str(bare)],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    before=source_hash(bare)
    result=worker.run_once(config(spool,bare,fake(tmp_path,'patch')))
    assert result['outcome']=='PATCH_READY'
    assert source_hash(bare)==before
    assert source_hash(source)==original
    clone=spool/'jobs'/value['job_id']/'clone'
    source_inodes = {(p.stat().st_dev, p.stat().st_ino)
                     for p in (bare/'objects').rglob('*') if p.is_file()}
    clone_inodes = {(p.stat().st_dev, p.stat().st_ino)
                    for p in (clone/'.git'/'objects').rglob('*') if p.is_file()}
    assert source_inodes and clone_inodes and source_inodes.isdisjoint(clone_inodes)
    assert not (clone/'.git'/'objects'/'info'/'alternates').exists()
    assert run_git(clone, 'fsck', '--no-reflogs', '--full') == b''


def test_timeout_outcome_survives_unreadable_clone(spool, source, tmp_path, monkeypatch):
    queue(spool)
    original=worker.git
    def git(repo, *args, **kwargs):
        if args and args[0]=='status':
            raise subprocess.CalledProcessError(1,['git','status'])
        return original(repo,*args,**kwargs)
    monkeypatch.setattr(worker,'git',git)
    result=worker.run_once(config(spool,source,fake(tmp_path,'sleep'),timeout_seconds=.5))
    assert result['state']=='TIMEOUT'
    assert result['outcome']=='TIMEOUT'


def test_job_starts_without_requesting_special_permission_bits(spool, source, tmp_path, monkeypatch):
    queue(spool)
    executable = fake(tmp_path, "none")
    original = Path.mkdir
    requested = []
    def restricted(path, mode=0o777, parents=False, exist_ok=False):
        if path.parent == spool / "jobs":
            requested.append(mode)
            if mode & 0o6000:
                raise PermissionError("RestrictSUIDSGID")
        return original(path, mode=mode, parents=parents, exist_ok=exist_ok)
    monkeypatch.setattr(Path, "mkdir", restricted)
    result = worker.run_once(config(spool, source, executable))
    assert result["outcome"] == "NO_CODE_CHANGE"
    assert requested == [0o770]


def test_reviewed_source_trust_reaches_upload_pack(spool, source, tmp_path, monkeypatch):
    # Model Git's separate child ownership check and exercise real Git with
    # spaces/metacharacters. No root, global config or production source needed.
    special = tmp_path / "reviewed source '$()' ;.git"
    source.rename(special)
    before = source_hash(special)
    original = worker.subprocess.run
    seen = []
    def guarded(argv, **kwargs):
        if 'clone' in argv:
            child = next((a.split('=', 1)[1] for a in argv if a.startswith('--upload-pack=')), '')
            child_args = shlex.split(child)
            if '--no-local' not in argv or 'safe.directory='+str(special) not in child_args:
                raise subprocess.CalledProcessError(128, ['git', 'clone'])
            assert child_args == ['/usr/bin/git', '-c', 'safe.directory='+str(special),
                                  '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', 'upload-pack']
            assert 'protocol.allow=never' in argv and 'protocol.file.allow=always' in argv
            assert '--no-recurse-submodules' in argv
            assert not any(a == 'safe.directory=*' for a in argv + child_args)
            seen.append(argv)
        return original(argv, **kwargs)
    monkeypatch.setattr(worker.subprocess, 'run', guarded)
    value = queue(spool, 'DIAGNOSE_ONLY')
    result = worker.run_once(config(spool, special, fake(tmp_path, 'none')))
    assert result['outcome'] == 'DIAGNOSIS_ONLY'
    assert len(seen) == 1 and source_hash(special) == before
    assert not run_git(spool/'jobs'/value['job_id']/'clone', 'remote')


def test_clone_failure_has_bounded_phase_evidence_and_no_retry(spool, source, tmp_path, monkeypatch):
    value = queue(spool, 'DIAGNOSE_ONLY')
    original = worker.git
    def fail(repo, *args, **kwargs):
        if 'clone' in args:
            raise subprocess.CalledProcessError(128, ['SECRET_COMMAND'], stderr=b'SECRET_STDERR')
        return original(repo, *args, **kwargs)
    monkeypatch.setattr(worker, 'git', fail)
    conf = config(spool, source, fake(tmp_path, 'none'))
    result = worker.run_once(conf)
    assert result['failure'] == 'WORKER_ERROR' and result['sequence'] == 3
    evidence = json.loads((spool/'jobs'/value['job_id']/'failure.json').read_text())
    assert evidence == {'phase':'SOURCE_CLONE', 'kind':'SUBPROCESS_ERROR', 'returncode':128}
    assert 'SECRET' not in json.dumps(result) + json.dumps(evidence)
    assert not (spool/'jobs'/value['job_id']/'invocation.json').exists()
    assert worker.run_once(conf)['state'] == 'IDLE'
