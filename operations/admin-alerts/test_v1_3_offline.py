"""Run only ADMIN tests with an explicit real-network guard and save a summary."""
import argparse
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    attempts=[]
    def forbidden(*args: object, **kwargs: object) -> None:
        attempts.append(True)
        raise AssertionError('REAL_NETWORK_FORBIDDEN')
    suite=unittest.defaultTestLoader.discover('tests/admin_alerts',pattern='test_*.py')
    with patch.object(socket.socket,'connect',side_effect=forbidden), patch.object(socket,'create_connection',side_effect=forbidden):
        result=unittest.TextTestRunner(verbosity=1).run(suite)
    summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'real_network_attempts':len(attempts),'telegram_sends':0,'football_api_calls':0,
             'scope':'ADMIN_ONLY_FAKE_TRANSPORT','passed':result.wasSuccessful() and not attempts}
    args.output.write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n')
    return 0 if summary['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
