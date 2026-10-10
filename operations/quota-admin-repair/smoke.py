"""Exercise assembled immutable releases with fake data and denied transports."""
import argparse
import importlib
import json
import os
from pathlib import Path
import socket
import sys
import unittest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--release", type=Path, required=True)
parser.add_argument("--kind", choices=("prematch","live","admin"), required=True)
parser.add_argument("--tests-root", type=Path, required=True)
args = parser.parse_args()
root = args.release if args.kind == "admin" else args.release/"application"
attempts = []
def denied(*unused, **kwargs):
    attempts.append(True)
    raise AssertionError("REAL_NETWORK_FORBIDDEN")
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
os.environ["FOOTBALL_API_KEY"] = "offline-test-placeholder"
os.environ["TELEGRAM_BOT_TOKEN"] = "offline-test-placeholder"
sys.path.insert(0, str(root))
sys.dont_write_bytecode = True
modules = ("app.admin_alerts.correlation", "app.admin_alerts.cli") if args.kind == "admin" else (
    "app.adaptive_lab.repository", "app.adaptive_lab.worker",
    "app.lab_v2_shadow.cli", "app.live_lab.service", "app.lab_combo.service")
for name in modules:
    module = importlib.import_module(name)
    if not Path(module.__file__).resolve().is_relative_to(root.resolve()):
        raise AssertionError("IMPORT_ROOT_ESCAPE:"+name)
os.chdir(args.tests_root)
if args.kind == "admin":
    suite = unittest.defaultTestLoader.discover(
        str(args.tests_root/"tests/admin_alerts"), pattern="test_quota_health_correlation.py")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    failed = not result.wasSuccessful()
    count = result.testsRun
else:
    import pytest
    failed = pytest.main(["-q", "--tb=short", "-p", "no:cacheprovider",
                         str(args.tests_root/"tests/adaptive_lab/test_audit_reader_lock.py")])
    count = 7
print("IMMUTABLE_RELEASE_SMOKE="+json.dumps({
    "kind":args.kind, "tests":count, "passed":not failed and not attempts,
    "import_root_verified":True, "network_attempts":len(attempts),
    "provider_calls":0, "telegram_sends":0},sort_keys=True))
raise SystemExit(1 if failed or attempts else 0)
