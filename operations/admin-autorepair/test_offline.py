"""Complete repair/ADMIN regression gate with a process-local real-network guard."""
import argparse
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pytest


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--adjacent',action='store_true')
    args=parser.parse_args()
    attempts=[]
    def forbidden(*args: object, **kwargs: object) -> None:
        attempts.append(True)
        raise AssertionError('REAL_NETWORK_FORBIDDEN')
    paths=['tests/admin_alerts','tests/admin_autorepair']
    if args.adjacent:
        paths+=['tests/test_lab_v2_shadow.py','tests/adaptive_lab/test_quota_cli.py']
    with patch.object(socket.socket,'connect',side_effect=forbidden), patch.object(socket,'create_connection',side_effect=forbidden):
        code=pytest.main(['-q',*paths])
    summary={'exit_code':int(code),'real_network_attempts':len(attempts),'real_codex_calls':0,
             'provider_calls':0,'telegram_calls':0,'test_paths':paths}
    args.output.write_text(json.dumps(summary,indent=2)+'\n')
    return int(code) if code else int(bool(attempts))


if __name__=='__main__':
    raise SystemExit(main())
