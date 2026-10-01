"""Operator can distinguish active work, proposed patches and required action."""
import pytest
from app.admin_alerts.operator_jobs import message

BUNDLE = {'incident_id': 'a'*24, 'job_id': 'b'*24, 'target': 'PREMATCH', 'mode': 'FIX_ALLOWED'}
STATUS = {'outcome': '', 'changed_files': 0, 'elapsed_seconds': 605, 'failure': ''}


@pytest.mark.parametrize('kind,outcome,mode,label', [
    ('STARTED', '', 'FIX_ALLOWED', 'Sāk izpēti'),
    ('RUNNING', '', 'DIAGNOSE_ONLY', 'Turpina izpēti'),
    ('RUNNING', '', 'FIX_ALLOWED', 'Turpina izpēti un labojuma sagatavošanu'),
    ('COMPLETED', 'PATCH_READY', 'FIX_ALLOWED', 'Gaida pārbaudi un apstiprinājumu'),
    ('COMPLETED', 'DIAGNOSIS_ONLY', 'DIAGNOSE_ONLY', 'Izpēte pabeigta'),
    ('COMPLETED', 'NO_CODE_CHANGE', 'FIX_ALLOWED', 'Darbs pabeigts bez koda labojuma'),
    ('FAILED', 'CODEX_FAILED', 'FIX_ALLOWED', 'Darbs beidzās ar kļūdu'),
    ('TIMEOUT', 'TIMEOUT', 'FIX_ALLOWED', 'Sasniegts darba laika limits'),
    ('STALLED', '', 'FIX_ALLOWED', 'Nav svaiga progresa ziņojuma'),
])
def test_truthful_latvian_state_and_action(kind, outcome, mode, label):
    body = message({**BUNDLE, 'mode': mode}, {**STATUS, 'outcome': outcome}, kind)
    assert 'Statuss: '+label in body and 'Darbība:' in body
    assert BUNDLE['incident_id'] in body and BUNDLE['job_id'] in body
    assert 'Ilgums: 10 min 5 s' in body and len(body) < 3000
    assert ('Gaida pārbaudi un apstiprinājumu' in body) == (outcome == 'PATCH_READY')


def test_patch_ready_does_not_claim_tests_or_deployment():
    body = message(BUNDLE, {**STATUS, 'outcome': 'PATCH_READY', 'changed_files': 2}, 'COMPLETED')
    assert 'Mainīti faili: 2' in body
    assert 'Jāpārbauda izmaiņas un testu rezultāti' in body
    assert 'Produkcijā vēl nav uzstādīts.' in body
    assert not body.startswith('✅')


def test_diagnosis_and_no_change_do_not_claim_incident_recovery():
    for outcome in ('DIAGNOSIS_ONLY', 'NO_CODE_CHANGE'):
        body = message(BUNDLE, {**STATUS, 'outcome': outcome}, 'COMPLETED')
        assert 'Jāpārskata izpētes rezultāts' in body
        assert 'Gaida pārbaudi un apstiprinājumu' not in body
        assert not body.startswith('✅')


def test_synthesized_start_does_not_show_later_failure():
    body = message(BUNDLE, {**STATUS, 'failure': 'CODEX_EXIT'}, 'STARTED')
    assert 'Kļūmes kods: NAV' in body
    assert 'CODEX_EXIT' not in body
