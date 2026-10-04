"""Prepare a pinned operator-only, read-only ADMIN diagnostic export."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

def main() -> None:
    root = Path(__file__).resolve().parents[2]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    for name in ("operations/admin-diagnostics/build.py", "operations/admin-diagnostics/inspect_recent.py"):
        if subprocess.check_output(["git", "show", commit+":"+name], cwd=root) != (root/name).read_bytes():
            raise ValueError("UNCOMMITTED_DIAGNOSTIC_SOURCE")
    source = (Path(__file__).parent/"inspect_recent.py").read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    parent = Path("/home/arvis/goalvision-operations")
    package = parent/("admin-diagnostic-"+commit[:7]+"-20261004")
    wrapper = parent/"admin-check-20261004.sh"
    if wrapper.exists():
        raise ValueError("EXISTING_WRAPPER_REVIEW_REQUIRED")
    package.mkdir(mode=0o700, exist_ok=False)
    target = package/"inspect_recent.py"
    target.write_bytes(source)
    target.chmod(0o600)
    pinned = """import hashlib,pathlib,sys
p=pathlib.Path(sys.argv[1])
if any(x.is_symlink() for x in (p,*p.parents)):
    raise SystemExit('DIAGNOSTIC_SOURCE_SYMLINK')
data=p.read_bytes()
if hashlib.sha256(data).hexdigest()!=sys.argv[2]:
    raise SystemExit('PINNED_DIAGNOSTIC_HASH_MISMATCH')
sys.argv=[str(p)]
exec(compile(data,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
"""
    command = " ".join(shlex.quote(value) for value in
                       ("/usr/bin/python3", "-I", "-B", "-c", pinned, str(target), digest))
    shell = """#!/bin/bash
set -eu
umask 077
sudo -v
gv_report=$(mktemp /home/arvis/goalvision-operations/admin-diagnostic-20261004-XXXXXX.json)
if sudo -n """+command+""" >"$gv_report"; then
    printf 'ADMIN_DIAGNOSTIC_SAVED=%s\\n' "$gv_report"
else
    printf 'ADMIN_DIAGNOSTIC_FAILED=%s\\n' "$gv_report"
    exit 1
fi
"""
    wrapper.write_text(shell)
    wrapper.chmod(0o700)
    subprocess.run(["bash", "-n", str(wrapper)], check=True)
    metadata = {"source_commit": commit, "inspect_sha256": digest,
                "wrapper": str(wrapper), "wrapper_sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest(),
                "mode": "OPERATOR_ONLY_READ_ONLY", "private_admin_database_read": False,
                "provider_calls": 0, "telegram_sends": 0, "monitor_scans": 0}
    (package/"metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True)+"\n")
    print("ADMIN_DIAGNOSTIC_PREPARED="+str(package))
    print("OPERATOR_EXPORT: bash ~/goalvision-operations/admin-check-20261004.sh")

if __name__ == "__main__":
    main()
