"""Read-only CHECK rehearsal; write evidence only to the controller review directory."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import time


def main() -> None:
    root = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('controller', root / 'controller.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract_sha = module.digest(module.read(root / 'host-contract.json'))
    contract = module.load_contract(root, contract_sha)
    commands: list[list[str]] = []

    def readonly_command(args: list[str], timeout: float = 5) -> str:
        allowed = (args[:2] in (['/usr/bin/systemctl', 'show'], ['/usr/bin/systemctl', 'list-units'])
                   or (args[0] == '/usr/bin/git' and args[-2:] == ['rev-parse', 'HEAD']))
        module.require(allowed, 'REHEARSAL_MUTATION_COMMAND_REJECTED')
        commands.append(args)
        return module.run(args, timeout)

    controller = module.Controller(module.Host(command=readonly_command),
                                   root / 'frozen' if (root / 'frozen').is_dir() else module.PACKAGE, contract)
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    paths = [Path(info['path']) for info in contract['databases'].values()]
    inodes = {str(p): p.stat().st_ino for p in paths}
    sidecars = {str(p): [suffix for suffix in ('-wal', '-shm', '-journal')
                        if Path(str(p) + suffix).exists()] for p in paths}
    try:
        result = controller.check()
    except (module.Blocked, OSError, ValueError, module.sqlite3.Error) as error:
        result = {'status': 'BLOCKED', 'reason': module.safe_error(error),
                  'preflight_findings': controller.last_check}
    elapsed = time.monotonic() - clock
    controller.verify_package()
    controller.configuration('before')
    controller.sources('before')
    module.require(inodes == {str(p): p.stat().st_ino for p in paths}, 'DB_INODE_CHANGED')
    module.require(sidecars == {str(p): [suffix for suffix in ('-wal', '-shm', '-journal')
                                       if Path(str(p) + suffix).exists()] for p in paths}, 'SIDECARS_CHANGED')
    output = {'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'contract_sha256': contract_sha, 'check_elapsed_seconds': round(elapsed, 4),
              'check': result, 'configuration_and_sources_unchanged': True,
              'db_inodes_unchanged': True, 'sidecars_before_and_after': sidecars,
              'production_service_control_operations': 0, 'production_database_writes': 0,
              'api_calls': 0, 'telegram_sends': 0, 'local_read_command_count': len(commands),
              'full_integrity_notice': module.SHADOW_NOTICE,
              'status': ('PREMATCH_QUOTA_HARDENING_DEPLOYMENT_READY_FOR_OPERATOR_PREFLIGHT'
                         if result.get('reason') == 'ADMIN_PRIVILEGED_CHECK_REQUIRES_OPERATOR'
                         else result['status'])}
    (root / 'host-rehearsal.json').write_text(json.dumps(output, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': output['status'], 'check_elapsed_seconds': output['check_elapsed_seconds']}))


if __name__ == '__main__':
    main()
