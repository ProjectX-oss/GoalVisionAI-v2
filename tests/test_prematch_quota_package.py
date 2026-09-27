from pathlib import Path
import hashlib
import json
import runpy
import pytest

verify = runpy.run_path(str(Path(__file__).parents[1]/'operations/quota-hardening/verify_package.py'))['verify']


def package(tmp_path):
    (tmp_path/'payload').write_bytes(b'reviewed')
    doc = {'application_commit': 'synthetic', 'files': {'payload': hashlib.sha256(b'reviewed').hexdigest()}}
    (tmp_path/'manifest.json').write_text(json.dumps(doc))
    return hashlib.sha256((tmp_path/'manifest.json').read_bytes()).hexdigest()


def test_exact_package_is_inert(tmp_path):
    digest = package(tmp_path)
    assert verify(tmp_path, digest) == {'status': 'VERIFIED', 'files': 1, 'application_commit': 'synthetic', 'installation_executed': False}


@pytest.mark.parametrize('mutation', ['manifest', 'payload', 'extra', 'symlink'])
def test_package_rejects_drift(tmp_path, mutation):
    digest = package(tmp_path)
    if mutation == 'manifest':
        (tmp_path/'manifest.json').write_text('{}')
    elif mutation == 'payload':
        (tmp_path/'payload').write_bytes(b'changed')
    elif mutation == 'extra':
        (tmp_path/'extra').write_text('unexpected')
    else:
        (tmp_path/'payload').unlink()
        (tmp_path/'payload').symlink_to('/etc/passwd')
    with pytest.raises(ValueError):
        verify(tmp_path, digest)
