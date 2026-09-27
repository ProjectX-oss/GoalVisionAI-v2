"""Bounded independent monitor; sending is disabled unless explicitly configured."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import signal
import time

from .delivery import DeliveryError, SenderConfig, Telegram, dispatch
from .model import DISCOVERY, Event, coverage, digest, epoch, identity
from .output_contracts import CONTRACTS, contract_report, expected_document
from .rules import compact
from .sources import command, health_rows, journal, service_rules, systemd, tail, unresolved, weekly_unresolved, invocation_output
from .store import Store, lock

DEFAULT_STATE = Path('/var/lib/goalvision-admin-alerts')


def atomic_json(path: Path, value: dict) -> None:
    """Replace ADMIN report only; crash leaves the previous complete report."""
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def configured_release(path: Path) -> str:
    """Read only PYTHONPATH from explicit trusted env, then tracked commit identity.

    This describes configuration NOW, not historical invocation attribution.
    """
    try:
        lines = path.read_text().splitlines()
        roots = [line.split('=', 1)[1] for line in lines if line.startswith('PYTHONPATH=')]
        if len(roots) != 1 or not roots[0].startswith('/home/arvis/GoalVisionAI-prematch-release-'):
            return 'UNKNOWN'
        commit = command(['git', '-c', 'safe.directory=' + roots[0], '-C', roots[0], 'rev-parse', 'HEAD'], timeout=1, limit=128).strip()
        return commit if len(commit) == 40 and all(c in '0123456789abcdef' for c in commit) else 'UNKNOWN'
    except (OSError, ValueError, TimeoutError):
        return 'UNKNOWN'


def scan(config: dict, root: Path, *, no_send: bool = True) -> dict:
    """One serialized scan. Transactions close before any ADMIN network activity."""
    begin = time.monotonic()
    now = time.time()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    uptime = float(Path('/proc/uptime').read_text().split()[0])
    boot_time = now - uptime
    with lock(root):
        if (root / 'DISABLED').exists():
            return {'status': 'DISABLED', 'telegram_sends': 0, 'football_api_calls': 0}
        store = Store(root)
        try:
            started = store.get('monitor_started', now)
            events = []
            cursors = {'monitor_started': started, 'boot': boot, 'last_scan': now}
            old_boot = store.get('boot')
            last_scan = store.get('last_scan', now)
            if old_boot and (old_boot != boot or now - last_scan > 180):
                events.append(coverage('monitor', now, 'MONITORING_GAP', object_id='monitor-gap'))
            try:
                properties = systemd()
                status_events, states = service_rules(properties, store.get('systemd', {}) if old_boot == boot else {},
                                                     now, boot_time, started, store.get('maintenance', {}))
                events.extend(status_events)
                cursors['systemd'] = states
            except (OSError, ValueError, TimeoutError):
                states = {}
                events.append(coverage('systemd', now, 'READ_UNAVAILABLE'))
            running = states.get(DISCOVERY, {}).get('running', True)
            records, problems, offset, bytes_read = tail(Path(config['stdout']), store.get('stdout', {}), now, running=running)
            cursors['stdout'] = offset
            events.extend(problems)
            for record, reference in records:
                # Old stdout is not a current failure; unresolved ledger evidence is separate.
                stamp = epoch(record.get('evaluated_at_utc'))
                if stamp and stamp < started - 900:
                    continue
                # stdout carries no InvocationID. Never infer it from the latest systemd state.
                events.extend(compact(record, reference, now))
                if stamp and expected_document(DISCOVERY, record):
                    cursors['last_compact_time'] = max(stamp, cursors.get('last_compact_time', store.get('last_compact_time', 0)))
            journal_events, journal_state = journal(store.get('journal', {}), now)
            cursors['journal'] = journal_state
            pending = store.get('pending_completed_evidence', {})
            for event in journal_events:
                if event.debounce > 1:
                    pending[event.signature + event.invocation] = event.document()
                else:
                    events.append(event)
            for key, document in list(pending.items()):
                state = states.get(document['service'], {})
                if state.get('invocation') == document['invocation'] and not state.get('running', True):
                    events.append(Event(**document))
                    del pending[key]
            if len(pending) > 25:
                events.append(coverage('journal', now, 'COMPLETION_ASSOCIATION_UNKNOWN'))
                pending = dict(list(pending.items())[-25:])
            cursors['pending_completed_evidence'] = pending
            discovery = states.get(DISCOVERY, {})
            # Absence is assessable only for discovery's known compact-output contract.
            # A window can prove a record exists, but not assign its release/cycle to an invocation.
            output_time = cursors.get('last_compact_time', store.get('last_compact_time', 0))
            if (discovery and not discovery['running'] and discovery['end'] > max(boot_time, started) and
                    now - discovery['end'] > 180 and output_time < discovery['start']):
                events.append(Event(DISCOVERY, 'MISSING_OUTPUT', discovery['invocation'], discovery['invocation'], now,
                                    'stdout-window', invocation=discovery['invocation'],
                                    facts={'association': 'ASSOCIATION_UNKNOWN', 'contract_version': 1}))
            for unit, state in states.items():
                if (CONTRACTS[unit].source != 'STRUCTURED_JOURNAL_JSON'
                        or state['running'] or state['failed']):
                    continue
                if state.get('standard_output') != 'journal':
                    events.append(coverage('journal', now, 'OUTPUT_CONTRACT_ROUTE_UNKNOWN', object_id=unit + '-output'))
                    continue
                events.append(Event('monitor', 'MONITORING_COVERAGE_DEGRADED', unit + '-output',
                                    'contract-route-available', now, 'journal', healthy=True))
                proof = journal_state.get('output_proofs_v1', {}).get(unit, {}).get(state['invocation'])
                if proof:
                    events.append(Event(unit, 'MISSING_OUTPUT', state['invocation'], state['invocation'], now,
                                        'journal-output', invocation=state['invocation'], healthy=True, facts=proof))
                elif (not store.db.execute("SELECT 1 FROM incidents WHERE service=? AND rule='MISSING_OUTPUT' AND object_id=? AND state='RECOVERED'",
                                          (unit, state['invocation'])).fetchone()
                      and state['invocation'] != 'UNKNOWN' and state['end'] > max(boot_time, started)
                      and now - state['end'] > 180):
                    events.append(Event(unit, 'MISSING_OUTPUT', state['invocation'], state['invocation'], now,
                                        'journal-output', invocation=state['invocation']))
            # Revisit unresolved historical incidents even when the stream cursor passed them.
            # Two per scan, round-robin; NONE and discovery never claim exact recovery.
            after = store.get('output_recheck_after', '')
            candidates = store.db.execute("""SELECT id,service,invocation FROM incidents
                WHERE rule='MISSING_OUTPUT' AND state IN ('OPEN','REPEATED','ESCALATED')
                AND id>? ORDER BY id LIMIT 2""", (after,)).fetchall()
            for row in candidates:
                events.extend(invocation_output(row['service'], row['invocation'], now))
            cursors['output_recheck_after'] = candidates[-1]['id'] if len(candidates) == 2 else ''
            # Expensive indexed diagnostics run at most once per five minutes.
            if now - store.get('last_database_poll', 0) >= 300:
                health_events, health_state = health_rows(Path(config['health_database']), store.get('health', {}), now)
                events.extend(health_events)
                cursors.update(health=health_state, last_database_poll=now)
                if not any(s.get('running', True) for s in states.values()) and len(states) == 5:
                    ledger_events, ledger_state = unresolved(Path(config['ledger_database']), store.get('ledger', {}), now)
                    events.extend(ledger_events)
                    cursors['ledger'] = ledger_state
                    cursors['ledger_deferred_since'] = 0
                    weekly_events, weekly_state = weekly_unresolved(Path(config['health_database']), store.get('weekly', {}), now)
                    events.extend(weekly_events)
                    cursors['weekly'] = weekly_state
                else:
                    deferred = store.get('ledger_deferred_since', 0) or now
                    cursors['ledger_deferred_since'] = deferred
                    if now - deferred >= 900:
                        events.append(coverage('ledger', now, 'CLAIM_REVIEW_DEFERRED_ACTIVE_OR_UNKNOWN_PRODUCER'))
            maintenance = store.get('maintenance', {})
            events = [e for e in events if not any(m.get('scope') in ('all', e.service) and m.get('until', 0) > now
                      for m in maintenance.values())]
            sampled = {'stdout', 'journal', 'systemd'}
            if 'health' in cursors:
                sampled.add('health')
            if 'ledger' in cursors:
                sampled.update(('ledger', 'weekly'))
            for source in sampled:
                if not any(e.rule == 'MONITORING_COVERAGE_DEGRADED' and e.source == source for e in events):
                    events.append(Event('monitor', 'MONITORING_COVERAGE_DEGRADED', source,
                        'read-available-' + digest(cursors.get(source, {})), now, source, healthy=True))
            store.ingest(events, cursors, now)
            store.invalidate_legacy_output(now)
            store.enqueue(now)
            sent = 0
            sender = SenderConfig(**config.get('sender', {}))
            if not no_send and sender.enabled:
                if (root / 'DISABLED').exists():
                    return {'status': 'DISABLED', 'telegram_sends': 0, 'football_api_calls': 0}
                try:
                    sent = dispatch(store, sender, Telegram(sender), now, deadline=begin + 35)
                except (DeliveryError, OSError) as failure:
                    with store.db:
                        store.put('delivery', {'code': failure.code if isinstance(failure, DeliveryError) else 'SECRET_UNAVAILABLE',
                                              'permanent': True, 'next': 0})
                delivery_state = store.get('delivery', {})
                delivery_code = delivery_state.get('code', 'UNKNOWN')
                store.ingest([Event('monitor', 'ADMIN_DELIVERY_DEGRADED', 'admin', delivery_code, now,
                    'admin-transport', facts={'code': delivery_code}, healthy=delivery_code == 'HEALTHY')], {}, now)
            store.retain(now)
            release = configured_release(Path(config['release_environment']))
            report = store.report(release)
            report['output_contracts'] = contract_report()
            report['source_access'] = {e.object_id: {**e.facts, 'read_available': e.healthy} for e in events if e.rule == 'MONITORING_COVERAGE_DEGRADED'}
            report['schedule_evidence'] = {u: s['schedule_evidence'] for u, s in states.items()}
            if cursors.get('ledger_deferred_since'):
                report['source_access']['ledger'] = {'read_available': False, 'reason': 'DEFERRED_ACTIVE_OR_UNKNOWN_PRODUCER',
                                                      'status': 'UNKNOWN'}
            report['admin_delivery'] = store.get('delivery', {'code': 'DISABLED' if no_send or not sender.enabled else 'UNKNOWN'})
            report['scan'] = {'elapsed_seconds': round(time.monotonic() - begin, 4), 'stdout_bytes': bytes_read,
                              'events': len(events), 'telegram_sends': sent, 'football_api_calls': 0, 'no_send': no_send}
            atomic_json(root / 'incident-report.json', report)
            atomic_json(root / 'last-scan.json', report['scan'])
            return report['scan']
        finally:
            store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--no-send', action='store_true')
    parser.add_argument('--suppress-service')
    parser.add_argument('--suppress-hours', type=float, default=1)
    parser.add_argument('--reason')
    args = parser.parse_args(argv)
    os.umask(0o077)
    # Signal bounds unexpected stalls too; systemd adds a second independent limit.
    def expired(signum: int, frame: object) -> None:
        raise TimeoutError('SCAN_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(40)
    try:
        root = args.state.absolute()
        if root.is_symlink() or root != root.resolve() or ('admin-alerts' not in root.name):
            raise ValueError('DEDICATED_ADMIN_STATE_REQUIRED')
        config = json.loads(args.config.read_text())
        if args.suppress_service:
            from .model import UNITS
            if args.suppress_service not in (*UNITS, 'all') or not 0 < args.suppress_hours <= 24 or not args.reason:
                raise ValueError('INVALID_MAINTENANCE')
            with lock(root):
                store = Store(root)
                try:
                    with store.db:
                        value = store.get('maintenance', {})
                        value[args.suppress_service] = {'scope': args.suppress_service,
                            'until': time.time() + args.suppress_hours * 3600, 'reason_reference': digest(args.reason)}
                        store.put('maintenance', value)
                finally:
                    store.close()
            return 0
        print(json.dumps(scan(config, root, no_send=args.no_send), sort_keys=True))
        return 0
    except Exception:
        # Deliberately no traceback/str(exception): transport exceptions can contain tokens.
        print('{"status":"MONITOR_STORAGE_OR_SCAN_DEGRADED","football_api_calls":0}')
        return 1
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    raise SystemExit(main())
