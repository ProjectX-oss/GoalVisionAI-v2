"""Build a reviewed operator package from pinned commits and installed releases."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("quota_admin_builder", HERE/"update.py")
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


def git(*args) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True,
                          capture_output=True).stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reader-tests-root", type=Path, required=True)
    parser.add_argument("--admin-tests-root", type=Path, required=True)
    args = parser.parse_args()
    head = git("rev-parse", "HEAD").decode().strip()
    for name in ("update.py","runtime_helpers.py","smoke.py","build.py"):
        if (HERE/name).read_bytes() != git("show", head+":operations/quota-admin-repair/"+name):
            raise ValueError("UNCOMMITTED_PACKAGE_CODE")
    u.h.disabled_worker()
    if u.mode() != "BASE":
        raise ValueError("BUILD_REQUIRES_REVIEWED_BASE_ROUTES")
    package = args.output.resolve()
    package.mkdir(exist_ok=False)
    for name in ("update.py","runtime_helpers.py"):
        shutil.copyfile(HERE/name, package/name)
    for kind, name in u.OVERLAYS.items():
        commit = u.SOURCE_COMMITS[kind]
        source = git("show", commit+":"+name)
        previous = git("show", commit+"^:"+name)
        keys = ("admin",) if kind=="admin" else ("prematch","live")
        for key in keys:
            root = u.BASES[key] if key=="admin" else u.BASES[key]/"application"
            if (root/name).read_bytes() != previous:
                raise ValueError("PATCH_PARENT_DOES_NOT_MATCH_INSTALLED:"+key)
        destination = package/"overlay"/kind/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source)
    meta = {
        "schema":"QUOTA_ADMIN_REPAIR_PACKAGE_V1", "installer_commit":head,
        "source_commits":u.SOURCE_COMMITS,
        "bases":{k:str(v) for k,v in u.BASES.items()},
        "targets":{k:str(v) for k,v in u.TARGETS.items()},
        "scripts":{p:u.h.sha(package/p) for p in ("update.py","runtime_helpers.py")},
        "overlay_hashes":{k:u.h.sha(package/"overlay"/k/v) for k,v in u.OVERLAYS.items()},
        "base_manifests":{k:u.manifest(v if k=="admin" else v/"application") for k,v in u.BASES.items()},
        "base_environments":{k:(v/"release.env").read_text() for k,v in u.BASES.items() if k!="admin"},
        "units":u.configured_units(), "systemd_files":u.configuration_files(),
        "timer_configurations":u.timer_configurations(), "smoke":{"status":"PENDING"},
    }
    results = {}
    with tempfile.TemporaryDirectory(prefix="quota-admin-build-smoke-") as temp:
        for key in u.BASES:
            stage = Path(temp)/key
            stage.mkdir()
            u.assemble(package, meta, key, stage)
            python = "/usr/bin/python3" if key=="admin" else "/home/arvis/GoalVisionAI/.venv/bin/python"
            tests_root = args.admin_tests_root if key=="admin" else args.reader_tests_root
            result = subprocess.run([python,"-I","-B",str(HERE/"smoke.py"),
                "--release",str(stage),"--kind",key,"--tests-root",str(tests_root)],
                capture_output=True,text=True,timeout=60)
            if result.returncode:
                raise ValueError("OFFLINE_RELEASE_SMOKE_FAILED:"+key+":"+result.stdout[-2000:]+result.stderr[-1000:])
            lines = [line for line in result.stdout.splitlines() if line.startswith("IMMUTABLE_RELEASE_SMOKE=")]
            if len(lines) != 1:
                raise ValueError("SMOKE_EVIDENCE_MISSING")
            results[key] = json.loads(lines[0].split("=",1)[1])
            if results[key].get("passed") is not True or results[key].get("network_attempts") != 0:
                raise ValueError("SMOKE_NOT_OFFLINE_PASS")
        meta["smoke"] = {"status":"THREE_RELEASES_OFFLINE_PASS","results":results}
        for key in u.BASES:
            stage = Path(temp)/("final-"+key)
            stage.mkdir()
            u.assemble(package, meta, key, stage)
    (package/"metadata.json").write_text(json.dumps(meta,sort_keys=True,indent=2)+"\n")
    u.validate(package)
    checksums = u.manifest(package)
    (package/"SHA256SUMS").write_text("".join(digest+"  "+name+"\n" for name,digest in checksums.items()))
    print("QUOTA_ADMIN_PACKAGE_PREPARED="+str(package))
    print("METADATA_SHA256="+u.h.sha(package/"metadata.json"))
    print("UPDATER_SHA256="+u.h.sha(package/"update.py"))


if __name__ == "__main__":
    main()
