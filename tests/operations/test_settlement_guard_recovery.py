"""Offline dependency and predecessor-recovery regressions; all writes use fixtures."""
from contextlib import redirect_stdout
import copy
import fcntl
import hashlib
import io
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_settlement_runtime_guard as fixtures

c, g, ROOT = fixtures.c, fixtures.g, fixtures.ROOT
REAL_LOCKED = c.locked
EMPTY_EXEC_KEYS = ('ExecCondition', 'ExecStartPre', 'ExecStartPost', 'ExecStop', 'ExecStopPost')


class DependencyTests(unittest.TestCase):
    setUp = fixtures.TransactionTests.setUp

    def test_exact_allowlist(self):
        self.assertEqual(c.DEPENDENCY_KEYS,
                         {'After', 'Before', 'Requires', 'Wants', 'OnFailure', 'OnSuccess'})

    def test_all_six_allow_permutations_and_duplicate_whitespace_tokens(self):
        for key in c.DEPENDENCY_KEYS:
            with self.subTest(key=key):
                self.pin['units'][c.SERVICE]['stable'][key] = 'alpha.service beta.target'
                self.host.props[c.SERVICE][key] = '\tbeta.target  alpha.service alpha.service\n'
                self.assertEqual(c.inspect(self.host, False)['pins'], 'PASS')

    def test_all_six_reject_missing_added_changed_and_substring_members(self):
        for key in c.DEPENDENCY_KEYS:
            self.pin['units'][c.SERVICE]['stable'][key] = 'alpha.service beta.target'
            for actual in ('alpha.service', 'alpha.service beta.target extra.service',
                           'alpha.service gamma.target', 'alpha.service beta.target.extra'):
                with self.subTest(key=key, actual=actual):
                    self.host.props[c.SERVICE][key] = actual
                    with self.assertRaisesRegex(ValueError, 'UNIT_PROPERTY_DRIFT_'+key):
                        c.inspect(self.host, False)
            self.host.props[c.SERVICE][key] = 'alpha.service beta.target'

    def test_empty_sets_and_missing_property_fail_closed(self):
        for key in c.DEPENDENCY_KEYS:
            self.assertTrue(c.property_equal(key, '', ' \t'))
            self.assertFalse(c.property_equal(key, '', 'alpha.service'))
            self.assertFalse(c.property_equal(key, 'alpha.service', ''))
        self.host.props[c.SERVICE].pop('OnFailure')
        with self.assertRaisesRegex(ValueError, 'UNIT_PROPERTY_DRIFT_OnFailure'):
            c.inspect(self.host, False)

    def test_every_other_pinned_property_still_exact(self):
        for key, expected in self.pin['units'][c.SERVICE]['stable'].items():
            if key in c.DEPENDENCY_KEYS:
                continue
            with self.subTest(key=key):
                self.assertFalse(c.property_equal(key, expected+' ', expected))
                self.host.props[c.SERVICE][key] = expected+' changed'
                with self.assertRaises(ValueError):
                    c.inspect(self.host, False)
                self.host.props[c.SERVICE][key] = expected
        for key in ('ExecStart', 'EnvironmentFiles', 'CapabilityBoundingSet', 'TimersCalendar'):
            self.assertFalse(c.property_equal(key, 'beta alpha', 'alpha beta'))

    def test_operator_reported_after_permutation(self):
        self.host.props[c.SERVICE]['After'] = (
            '-.mount basic.target goalvision-lab-combo-settle.timer network-online.target '
            'sysinit.target system.slice systemd-journald.socket')
        self.assertEqual(c.inspect(self.host, False)['pins'], 'PASS')


class StablePropertyTests(unittest.TestCase):
    setUp = fixtures.TransactionTests.setUp

    def test_each_omitted_empty_exec_property_passes(self):
        for key in EMPTY_EXEC_KEYS:
            with self.subTest(key=key):
                self.assertEqual(self.pin['units'][c.SERVICE]['stable'][key], '')
                original = self.host.props[c.SERVICE].pop(key)
                self.assertEqual(c.inspect(self.host, False)['pins'], 'PASS')
                self.host.props[c.SERVICE][key] = original

    def test_each_unexpected_nonempty_exec_property_fails(self):
        for key in EMPTY_EXEC_KEYS:
            for actual in ('/bin/false', ' \t'):
                with self.subTest(key=key, actual=actual):
                    self.host.props[c.SERVICE][key] = actual
                    with self.assertRaisesRegex(ValueError, 'UNIT_PROPERTY_DRIFT_'+key):
                        c.inspect(self.host, False)
                    self.host.props[c.SERVICE][key] = ''

    def test_all_other_stable_properties_retain_absent_and_empty_semantics(self):
        for unit, entry in self.pin['units'].items():
            for key, expected in entry['stable'].items():
                if key in c.DEPENDENCY_KEYS:
                    continue
                for absent in (True, False):
                    with self.subTest(unit=unit, key=key, absent=absent), \
                            patch.dict(self.host.props[unit], {}):
                        self.host.props[unit].pop(key)
                        if not absent:
                            self.host.props[unit][key] = ''
                        if expected:
                            code = 'UNIT_NOT_LOADED' if key == 'LoadState' else 'UNIT_PROPERTY_DRIFT_'+key
                            with self.assertRaisesRegex(ValueError, code):
                                c.inspect(self.host, False)
                        else:
                            self.assertEqual(c.inspect(self.host, False)['pins'], 'PASS')

    def test_all_six_dependencies_require_presence_even_when_pinned_empty(self):
        for key in c.DEPENDENCY_KEYS:
            for expected in ('', 'alpha.service'):
                with self.subTest(key=key, expected=expected):
                    original = self.pin['units'][c.SERVICE]['stable'][key]
                    self.pin['units'][c.SERVICE]['stable'][key] = expected
                    actual = self.host.props[c.SERVICE].pop(key)
                    with self.assertRaisesRegex(ValueError, 'UNIT_PROPERTY_DRIFT_'+key):
                        c.inspect(self.host, False)
                    self.pin['units'][c.SERVICE]['stable'][key] = original
                    self.host.props[c.SERVICE][key] = actual


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        fixtures.TransactionTests.setUp(self)
        # Keep the exact production payload while redirecting every file to /tmp.
        wrapper = ('/usr/bin/python3', '-I', '-S',
                   '/opt/goalvision-settlement-guard-v1/runtime_guard.py')
        self.patch('wrapped_argv', lambda: wrapper)
        c.change(self.host, 'install', c.PREDECESSOR_MANIFEST)
        tx = c.transaction()
        tx['phase'] = 'installing'
        del tx['installed_at']
        c.save(tx)
        self.host.calls.clear()
        for unit, props in self.host.props.items():
            if unit.endswith('.timer'):
                props.update(ActiveState='active', SubState='waiting')
        self.host.props[c.SERVICE]['After'] = ' '.join(reversed(
            self.host.props[c.SERVICE]['After'].split()))
        self.admin = c.STATE/'admin.json'
        self.admin.write_text('{"sender":{"enabled":false}}')
        self.stagger = c.STATE/'stagger.json'
        self.stagger.write_text(json.dumps({'phase': 'installed', 'manifest':
            '61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598'}))
        self.patch('ADMIN_CONFIG', self.admin)
        self.patch('STAGGER_RECEIPT', self.stagger)
        self.host.protected = c.Host().protected
        for module, name in ((socket, 'socket'), (socket, 'create_connection'),
                             (sqlite3, 'connect'), (c.subprocess, 'run')):
            p = patch.object(module, name, side_effect=AssertionError('EXTERNAL_EFFECT'))
            p.start(); self.addCleanup(p.stop)

    def patch(self, key, value):
        p = patch.object(c, key, value)
        p.start(); self.addCleanup(p.stop)

    def snapshot(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode)
                for p in c.STATE.parent.rglob('*') if p.is_file()}

    def refused(self, code):
        before = self.snapshot()
        for finalize in (False, True):
            with self.assertRaisesRegex(ValueError, code):
                c.recover(self.host, self.digest, finalize)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.host.calls, [])

    def test_preflight_is_read_only_and_full_inspection(self):
        before = self.snapshot()
        with patch.object(c, 'locked', side_effect=AssertionError('LOCK_WRITE')):
            report = c.recover(self.host, self.digest)
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual(report['predecessor_manifest'], c.PREDECESSOR_MANIFEST)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.host.calls, [])

    def test_finalize_preserves_receipt_and_only_writes_transaction(self):
        raw = (c.STATE/'transaction.json').read_text()
        before = self.snapshot()
        tx = c.recover(self.host, self.digest, True)
        self.assertEqual(tx['manifest'], c.PREDECESSOR_MANIFEST)
        self.assertEqual(tx['original_argv'], list(g.SETTLEMENT_ARGV))
        self.assertEqual(tx['phase'], 'installed')
        self.assertEqual(tx['recovery']['predecessor_receipt'], raw)
        self.assertEqual(tx['recovery']['predecessor_receipt_sha256'],
                         hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(tx['installed_at'], tx['recovery']['recovered_at'])
        c.authorize_transaction(tx, self.digest)
        after = self.snapshot()
        self.assertEqual(set(before), set(after))
        self.assertEqual([p for p in before if before[p] != after[p]],
                         [str(c.STATE/'transaction.json')])
        self.assertEqual(self.host.calls, [])
        self.refused('RECOVERY_INSTALLING_REQUIRED')

    def test_unknown_manifest_and_all_other_phases_refused(self):
        original = c.transaction()
        for field, value, code in [('manifest', 'b'*64, 'PREDECESSOR_MISMATCH')]+[
                ('phase', phase, 'INSTALLING_REQUIRED') for phase in
                ('installed', 'rolling_back', 'rolled_back', '', None)]:
            with self.subTest(field=field, value=value):
                c.save({**original, field: value})
                self.refused(code)
        c.save(original)
        for field, value in (('original_argv', ['/bin/false']), ('recovery', {}),
                             ('installed_at', '2026-09-29T00:00:00+00:00')):
            c.save({**original, field: value})
            self.refused('ORIGINAL_ARGV_DRIFT|RECEIPT_AMBIGUOUS')

    def test_exact_installed_artifact_hashes_required(self):
        for path, code in ((c.route(), 'RECOVERY_ROUTING_TAMPER'),
                           (c.RELEASE/'runtime_guard.py', 'RECOVERY_GUARD_TAMPER')):
            original = path.read_bytes()
            path.chmod(0o644); path.write_bytes(original+b'\n')
            self.refused(code)
            path.write_bytes(original)

    def test_package_predecessor_baseline_and_runtime_hashes_required(self):
        for key, code in (('PREDECESSOR_BASELINE', 'RECOVERY_BASELINE_DRIFT'),
                          ('PREDECESSOR_GUARD', 'RECOVERY_PACKAGE_GUARD_DRIFT')):
            with patch.object(c, key, '0'*64):
                self.refused(code)

    def test_loaded_wrapper_reload_and_idle_are_mandatory(self):
        props = self.host.props[c.SERVICE]
        for key, value, code in (
                ('ExecStart', self.host.exec_text(g.SETTLEMENT_ARGV), 'EXECSTART_DRIFT'),
                ('ExecStart', self.host.exec_text((*c.wrapped_argv(), '--extra')), 'EXECSTART_DRIFT'),
                ('ExecStart', self.host.exec_text(c.wrapped_argv()).replace(
                    'path=/usr/bin/python3', 'path=/bin/false'), 'EXECSTART_DRIFT'),
                ('ExecStart', self.host.exec_text(c.wrapped_argv())+' '+
                    self.host.exec_text(['/bin/false']), 'EXECSTART_DRIFT'),
                ('NeedDaemonReload', 'yes', 'DAEMON_RELOAD_DRIFT'),
                ('ActiveState', 'active', 'SETTLEMENT_NOT_IDLE'),
                ('ActiveState', 'failed', 'SETTLEMENT_NOT_IDLE'),
                ('SubState', 'exited', 'SETTLEMENT_NOT_IDLE')):
            old = props[key]; props[key] = value
            self.refused(code)
            props[key] = old

    def test_timer_state_and_calendar_pins_required(self):
        props = self.host.props[g.TIMER]
        for key, value, code in (('ActiveState', 'inactive', 'TIMER_STATE_DRIFT'),
                ('SubState', 'elapsed', 'TIMER_STATE_DRIFT'),
                ('TimersCalendar', '{ OnCalendar=changed ; next_elapse=n/a }', 'CALENDAR_DRIFT'),
                ('UnitFileState', 'disabled', 'UNIT_PROPERTY_DRIFT')):
            old = props[key]; props[key] = value
            self.refused(code)
            props[key] = old

    def test_admin_disabled_and_exact_stagger_installed_required(self):
        self.admin.write_text('{"sender":{"enabled":true}}')
        self.refused('ADMIN_DISABLED_REQUIRED')
        self.admin.write_text('{"sender":{"enabled":false}}')
        original = json.loads(self.stagger.read_text())
        for field, value in (('phase', 'installing'), ('manifest', 'b'*64)):
            self.stagger.write_text(json.dumps({**original, field: value}))
            self.refused('STAGGER_V4_INSTALLED_REQUIRED')

    def test_complete_inspection_rejects_unit_environment_sandbox_and_dependency_drift(self):
        props = self.host.props[c.SERVICE]
        for key in ('After', 'Before', 'Requires', 'Wants', 'OnFailure', 'OnSuccess',
                    'EnvironmentFiles', 'Environment_sha256', 'NoNewPrivileges',
                    'ProtectSystem', 'CapabilityBoundingSet', 'TimeoutStartUSec'):
            old = props[key]; props[key] = old+' extra'
            self.refused('UNIT_PROPERTY_DRIFT_'+key)
            props[key] = old
        unit = Path(next(iter(self.pin['units'][g.DISCOVERY]['files_sha256'])))
        unit.write_text('drift')
        self.refused('UNIT_HASH_DRIFT')

    def test_environment_file_foreign_dropin_and_inventory_drift(self):
        env = c.STATE/'release.env'; env.write_text('fixture')
        self.pin['environment_files_sha256'][str(env)] = c.sha(env)
        env.write_text('changed')
        self.refused('ENVIRONMENT_FILE_DRIFT')
        self.pin['environment_files_sha256'].clear()
        extra = c.route().parent/'foreign.conf'; extra.write_text('[Service]\n')
        self.refused('UNLOADED_DROPIN_DRIFT'); extra.unlink()
        (c.RELEASE/'extra').touch()
        self.refused('RELEASE_INVENTORY_DRIFT')

    def test_symlink_and_ownership_rejected(self):
        with patch.object(c, 'require_root_owned', side_effect=ValueError('OWNER_MODE_DRIFT')):
            self.refused('OWNER_MODE_DRIFT')
        route = c.route(); data = route.read_bytes(); route.unlink()
        target = c.STATE/'target'; target.write_bytes(data); route.symlink_to(target)
        self.refused('SYMLINK_REFUSED')

    def test_state_change_during_inspection_refuses_finalization(self):
        def changed():
            c.Host().protected()
            self.host.props[c.SERVICE]['ActiveState'] = 'activating'
        self.host.protected = changed
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'SETTLEMENT_NOT_IDLE'):
            c.recover(self.host, self.digest, True)
        self.assertEqual(before, self.snapshot())

    def test_receipt_change_during_inspection_refuses_finalization(self):
        def changed():
            c.Host().protected()
            c.save({**c.transaction(), 'unexpected': 'change'})
        self.host.protected = changed
        with self.assertRaisesRegex(ValueError, 'RECOVERY_RECEIPT_CHANGED'):
            c.recover(self.host, self.digest, True)
        self.assertEqual(c.transaction()['phase'], 'installing')
        self.assertEqual(self.host.calls, [])

    def test_normal_commands_require_valid_recovery_linkage(self):
        with self.assertRaisesRegex(ValueError, 'TRANSACTION_PACKAGE_MISMATCH'):
            c.authorize_transaction(c.transaction(), self.digest)
        tx = c.recover(self.host, self.digest, True)
        for key, value in (('manifest', 'b'*64), ('schema', 'unknown'),
                           ('predecessor_receipt', '{}'), ('predecessor_receipt_sha256', '0'*64),
                           ('recovered_at', '2020-01-01T00:00:00+00:00')):
            candidate = copy.deepcopy(tx); candidate['recovery'][key] = value
            with self.assertRaises(ValueError):
                c.authorize_transaction(candidate, self.digest)
        for key, value in (('manifest', 'b'*64), ('phase', 'installing'),
                           ('original_argv', ['/bin/false'])):
            with self.assertRaises(ValueError):
                c.authorize_transaction({**tx, key: value}, self.digest)
        with self.assertRaisesRegex(ValueError, 'PACKAGE_MISMATCH'):
            c.authorize_transaction(tx, 'b'*64)

    def cli(self, action, *options):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['control.py', action, '--manifest-sha256',
                self.digest, *options]), patch.object(c, 'Host', return_value=self.host), \
                patch.object(c, 'verify_package') as verify, redirect_stdout(output):
            status = c.main()
        verify.assert_called_once_with(c.PACKAGE, self.digest)
        return status, json.loads(output.getvalue())

    def test_cli_preflight_finalize_status_evidence_and_exact_rollback(self):
        original = list(g.SETTLEMENT_ARGV)
        self.assertEqual(self.cli('recovery-preflight')[1]['phase'], 'installing')
        self.assertEqual(self.cli('recover-installing')[1]['phase'], 'installed')
        status, report = self.cli('status')
        self.assertEqual(status, 0)
        self.assertEqual(report['manifest'], c.PREDECESSOR_MANIFEST)
        self.assertEqual(report['recovery']['manifest'], self.digest)
        with patch.object(fixtures.e, 'evidence', return_value={'verdict': 'PASS'}) as evidence:
            self.assertEqual(self.cli('evidence')[0], 0)
            evidence.assert_called_once_with(self.host, c.transaction()['installed_at'])
            with self.assertRaisesRegex(ValueError, 'PREINSTALL_EVIDENCE_REFUSED'):
                self.cli('evidence', '--since', '2000-01-01T00:00:00+00:00')
        self.assertEqual(self.host.calls, [])
        self.assertEqual(self.cli('rollback')[1]['phase'], 'rolled_back')
        self.assertEqual(c.exec_argv(self.host.props[c.SERVICE]['ExecStart']), ' '.join(original))
        self.assertEqual(c.transaction()['original_argv'], original)
        self.assertEqual(c.transaction()['manifest'], c.PREDECESSOR_MANIFEST)
        self.assertFalse(c.route().exists()); self.assertFalse(c.RELEASE.exists())
        self.assertEqual(self.host.calls, ['daemon-reload'])
        self.assertEqual(self.cli('status')[1]['phase'], 'rolled_back')
        self.cli('rollback')
        self.assertEqual(self.host.calls, ['daemon-reload'])
        with self.assertRaisesRegex(ValueError, 'REINSTALL_REFUSED'):
            c.change(self.host, 'install', self.digest)

    def test_recovered_rollback_reload_failure_remains_retryable(self):
        c.recover(self.host, self.digest, True)
        self.host.reload_error = True
        with self.assertRaises(OSError):
            c.change(self.host, 'rollback', self.digest)
        self.assertEqual(c.transaction()['phase'], 'rolling_back')
        tx = c.change(self.host, 'rollback', self.digest)
        self.assertEqual(tx['phase'], 'rolled_back')
        self.assertEqual(c.exec_argv(self.host.props[c.SERVICE]['ExecStart']),
                         ' '.join(g.SETTLEMENT_ARGV))

    def test_real_host_adapter_uses_only_systemctl_show_during_recovery(self):
        calls = []
        def show_only(argv, **kwargs):
            self.assertEqual(argv[:2], ['/usr/bin/systemctl', 'show'])
            self.assertEqual(len(argv), 4)
            self.assertTrue(argv[3].startswith('--property='))
            calls.append(argv)
            props = self.host.show(argv[2])
            props.pop('Environment_sha256', None)
            props['Environment'] = ''
            return subprocess.CompletedProcess(argv, 0,
                '\n'.join(k+'='+v for k, v in props.items()), '')
        with patch.object(c.subprocess, 'run', side_effect=show_only):
            tx = c.recover(c.Host(), self.digest, True)
        self.assertEqual(tx['phase'], 'installed')
        self.assertEqual({argv[2] for argv in calls}, set(self.pin['units']))

    def test_production_show_fixture_omits_all_five_empty_exec_properties(self):
        calls = []
        def show_only(argv, **kwargs):
            self.assertEqual(argv[:2], ['/usr/bin/systemctl', 'show'])
            self.assertEqual(len(argv), 4)
            self.assertTrue(argv[3].startswith('--property='))
            calls.append(argv)
            props = self.host.show(argv[2])
            props.pop('Environment_sha256', None)
            props['Environment'] = ''
            if argv[2] == c.SERVICE:
                for key in EMPTY_EXEC_KEYS:
                    self.assertEqual(props.pop(key), '')
            output = '\n'.join(k+'='+v for k, v in props.items())
            if argv[2] == c.SERVICE:
                self.assertFalse(any(line.startswith(EMPTY_EXEC_KEYS)
                                     for line in output.splitlines()))
            return subprocess.CompletedProcess(argv, 0, output, '')

        before = self.snapshot()
        with patch.object(c.subprocess, 'run', side_effect=show_only):
            host = c.Host()
            self.assertTrue(all(key not in host.show(c.SERVICE) for key in EMPTY_EXEC_KEYS))
            with patch.object(c, 'locked', side_effect=AssertionError('LOCK_WRITE')):
                report = c.recover(host, self.digest)
            self.assertEqual(report['verdict'], 'PASS')
            self.assertEqual(report['phase'], 'installing')
            self.assertEqual(before, self.snapshot())
            self.assertEqual(c.recover(host, self.digest, True)['phase'], 'installed')
        after = self.snapshot()
        self.assertEqual(set(before), set(after))
        self.assertEqual([p for p in before if before[p] != after[p]],
                         [str(c.STATE/'transaction.json')])
        self.assertEqual(self.host.calls, [])
        self.assertEqual({argv[2] for argv in calls}, set(self.pin['units']))

    def test_recovery_rejects_each_unexpected_nonempty_exec_property(self):
        for key in EMPTY_EXEC_KEYS:
            with self.subTest(key=key):
                self.host.props[c.SERVICE][key] = '/bin/false'
                self.refused('UNIT_PROPERTY_DRIFT_'+key)
                self.host.props[c.SERVICE][key] = ''

    def test_finalization_uses_real_exclusive_lock(self):
        lock = c.STATE/'lock'
        with lock.open('a') as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = self.snapshot()
            with patch.object(c, 'locked', REAL_LOCKED), patch.object(c.os, 'geteuid', return_value=0):
                with self.assertRaises(BlockingIOError):
                    c.recover(self.host, self.digest, True)
            self.assertEqual(before, self.snapshot())
        with patch.object(c, 'locked', REAL_LOCKED), patch.object(c.os, 'geteuid', return_value=0):
            self.assertEqual(c.recover(self.host, self.digest, True)['phase'], 'installed')

    def test_invalid_package_is_rejected_before_host_or_receipt_access(self):
        with patch.object(sys, 'argv', ['control.py', 'recover-installing',
                '--manifest-sha256', '0'*64]), patch.object(c, 'Host') as host, \
                patch.object(c, 'transaction') as receipt:
            with self.assertRaisesRegex(ValueError, 'MANIFEST_TAMPER'):
                c.main()
        host.assert_not_called(); receipt.assert_not_called()

    def test_malformed_provenance_fails_closed(self):
        tx = c.recover(self.host, self.digest, True)
        for proof in (None, [], 'invalid', {**tx['recovery'], 'predecessor_receipt': []},
                      {**tx['recovery'], 'recovered_at': None}):
            with self.assertRaises(ValueError):
                c.authorize_transaction({**tx, 'recovery': proof}, self.digest)

    def test_atomic_failure_leaves_original_receipt_retryable(self):
        before = self.snapshot()
        with patch.object(c.os, 'replace', side_effect=OSError('injected write failure')):
            with self.assertRaises(OSError):
                c.recover(self.host, self.digest, True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(c.recover(self.host, self.digest, True)['phase'], 'installed')


if __name__ == '__main__':
    unittest.main()
