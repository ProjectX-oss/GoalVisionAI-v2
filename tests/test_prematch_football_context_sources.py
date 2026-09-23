"""Phase B synthetic source-integrity tests; no live provider or production DB."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import ast
import json
from pathlib import Path
import random
import subprocess
import sys

import pytest

from app.prematch_football_context import calculate_context, result_fingerprint
from app.prematch_football_context.contracts import Classification, ContextInput, Fixture, History, Neutral, Status
from app.prematch_football_context.policy import Profile
from app.prematch_football_context.fingerprint import canonical_bytes
from app.prematch_football_context.sources import (
    Candidate, CaptureOrder, Query, SourceHeader, SourceKind, Timing, diagnostics,
    digest, history_query, select_source, target_query,
)
from app.prematch_football_context.source_adapter import (
    FormatEvidence, TargetState, legacy_cache_candidate, sanitize_payload, source_candidate,
    source_ref, target_state,
)
from app.prematch_football_context.evidence import (
    Binding, EvidenceUnavailable, evidence_fingerprint, replay_evidence, retain_evidence,
)

T = datetime(2026, 9, 23, 12, 0, 0, 123456, tzinfo=timezone.utc)
C = Classification(Profile.SENIOR_MEN_PRO, 'SYNTHETIC_V1', 'TEST', (), 'MEN', 'SENIOR', 'CLUB', 'a' * 64)
CURRENT = SourceKind.CURRENT
PREVIOUS = SourceKind.PREVIOUS
TARGET = SourceKind.TARGET


def raw(identifier=1, *, season=2026, status='FT', kickoff=None, home=1, away=2, gf=1, ga=0):
    return {'fixture': {'id': identifier, 'date': (kickoff or T - timedelta(days=identifier)).isoformat(),
                        'status': {'short': status}},
            'league': {'id': 10, 'season': season, 'round': 'Regular Season - 1'},
            'teams': {'home': {'id': home}, 'away': {'id': away}},
            'score': {'fulltime': {'home': gf, 'away': ga}}, 'goals': {'home': gf, 'away': ga}}


def candidate(payload=None, *, kind=CURRENT, identity=None, age=timedelta(minutes=1), **timing):
    identity = identity or {CURRENT: 'source1', PREVIOUS: 'previous', TARGET: 'target'}[kind]
    if payload is None:
        payload = ([raw(9999, status='NS', kickoff=T + timedelta(hours=1), gf=None, ga=None)]
                   if kind == TARGET else [raw(i, season=2025 if kind == PREVIOUS else 2026) for i in range(1, 9)])
    query = target_query(9999) if kind == TARGET else history_query(10, 2025 if kind == PREVIOUS else 2026)
    end = T - age
    times = Timing(**({'retrieval_completed_at': end, 'registered_at': end + timedelta(seconds=1),
                      'known_at': end + timedelta(seconds=1), 'expiry': T + timedelta(hours=1)} | timing))
    content = sanitize_payload(payload)
    header = SourceHeader(identity, query, kind, times, digest(json.loads(content)))
    return source_candidate(header, payload)


def select(*candidates, kind=CURRENT, query=None):
    return select_source(tuple(candidates), query or (target_query(9999) if kind == TARGET else history_query(10, 2025 if kind == PREVIOUS else 2026)),
                         cutoff=T, source_kind=kind)


def binding(**changes):
    return replace(Binding(9999, 10, 2026, T, C,
                           FormatEvidence(10, 2026, 90, 'SYNTHETIC90', 'b' * 64, T - timedelta(days=2)),
                           FormatEvidence(10, 2025, 90, 'SYNTHETIC90', 'b' * 64, T - timedelta(days=2))), **changes)


def bundle(*, current=None, target=None, previous=None, bind=None):
    return retain_evidence(bind or binding(), (
        select(target or candidate(kind=TARGET, identity='target'), kind=TARGET),
        select(*(current if current is not None else (candidate(),))),
        select(*(previous or ()), kind=PREVIOUS)))


def test_A_AF_exact_phase_a_input_result_and_replay():
    b = bundle()
    replay = replay_evidence(b)
    selected = b.selections[1].selected
    rows = tuple(Fixture('API_FOOTBALL', i, 10, 2026, 1, 2, T - timedelta(days=i), C.entity_scope,
                         1, 0, goals_home=1, goals_away=0, phase='Regular Season - 1') for i in range(1, 9))
    # Compare independently constructed Phase A input, including canonical row order.
    expected = ContextInput(replay.inputs.target, History(2026, source_ref(selected),
                            b.binding.current_format.regulation(T), tuple(sorted(rows, key=canonical_bytes))))
    assert replay.inputs == expected
    assert replay.result == calculate_context(expected)
    assert b.result_hash == result_fingerprint(calculate_context(expected))
    assert replay_evidence(b) == replay
    assert all(f.status == Status.AVAILABLE for f in replay.result.features)
    assert dict(diagnostics(b.selections[1]))['selected'] == 1


@pytest.mark.parametrize('field', ['retrieval_completed_at', 'registered_at', 'known_at'])
def test_B_C_D_E_T07_future_local_time_never_rescued(field):
    c = candidate(**{field: T + timedelta(microseconds=1), 'provider_updated_at': T - timedelta(days=90)})
    s = select(c)
    assert s.selected is None
    assert s.decisions[0].verdict == 'AFTER_CUTOFF'


def test_F_missing_provider_timestamp_remains_unknown():
    b = bundle()
    timing = b.selections[1].selected.header.timing
    assert timing.provider_updated_at is None and timing.provider_freshness == 'UNKNOWN'
    assert b'"provider_updated_at":null' in canonical_bytes(b)
    assert replay_evidence(b).inputs.current.source.known_at == timing.registered_at


def test_G_T07_cutoff_equality_requires_bound_durable_receipt():
    c = candidate(retrieval_completed_at=T, registered_at=T, known_at=T)
    assert select(c).decisions[0].verdict == 'ASOF_UNPROVEN'
    proof = CaptureOrder(T, c.header.source_id, c.header.content_hash, 'c' * 64)
    good = replace(c, header=replace(c.header, timing=replace(c.header.timing, before_capture=proof)))
    assert select(good).verdict == 'SELECTED'
    assert replay_evidence(bundle(current=(good,))).inputs.current.source.available_before_capture
    for bad in (replace(proof, cutoff=T - timedelta(microseconds=1)), replace(proof, source_id='other'),
                replace(proof, content_hash='d' * 64)):
        row = replace(good, header=replace(good.header, timing=replace(good.header.timing, before_capture=bad)))
        assert select(row).selected is None


@pytest.mark.parametrize(('kind', 'age'), [(CURRENT, timedelta(hours=6)), (PREVIOUS, timedelta(hours=24)), (TARGET, timedelta(minutes=15))])
def test_H_I_J_T14_strict_freshness_boundaries(kind, age):
    assert select(candidate(kind=kind, age=age), kind=kind).decisions[0].verdict == 'STALE'
    assert select(candidate(kind=kind, age=age - timedelta(microseconds=1)), kind=kind).verdict == 'SELECTED'


def test_K_expiry_equality_rejected():
    assert select(candidate(expiry=T)).decisions[0].verdict == 'EXPIRED'


@pytest.mark.parametrize('field', ['retrieval_completed_at', 'registered_at', 'known_at', 'expiry'])
def test_T07_missing_local_proof(field):
    assert select(candidate(**{field: None})).decisions[0].verdict == 'ASOF_UNPROVEN'


def test_legacy_adapter_does_not_retrofit_cache_semantics():
    c = legacy_cache_candidate(source_id='legacy', query=history_query(10, 2026), kind=CURRENT,
                              retrieved_at=T - timedelta(minutes=1), expiry=T + timedelta(hours=1), payload=[raw()])
    assert c.header.timing.retrieval_completed_at is None
    assert c.header.timing.registered_at is None
    assert select(c).decisions[0].verdict == 'ASOF_UNPROVEN'


@pytest.mark.parametrize('change', [
    {'provider_updated_at': T}, {'request_started_at': T},
    {'known_at': T - timedelta(hours=2)}, {'registered_at': T - timedelta(hours=2)},
])
def test_invalid_latest_timing_does_not_fall_back(change):
    good = candidate(identity='older', age=timedelta(minutes=2))
    bad = candidate(identity='latest', **change)
    s = select(good, bad)
    assert s.selected == bad and s.verdict == 'INVALID_TIMING'
    assert replay_evidence(bundle(current=(good, bad))).inputs.current.source is None


def test_old_provider_update_does_not_expire_fresh_results():
    assert select(candidate(provider_updated_at=T - timedelta(days=365))).verdict == 'SELECTED'


def test_L_deterministic_all_tiebreakers():
    older = candidate(identity='older', age=timedelta(minutes=2))
    latest = candidate(identity='z_latest')
    later_registration = replace(latest, header=replace(latest.header, source_id='registration', timing=replace(
        latest.header.timing, registered_at=T - timedelta(seconds=5), known_at=T - timedelta(seconds=5))))
    assert select(older, latest, later_registration).selected == later_registration
    different = candidate([raw(gf=4)], identity='different')
    expected = min((latest, different), key=lambda c: c.header.content_hash)
    assert select(latest, different).selected == expected
    twin = replace(latest, header=replace(latest.header, source_id='a_latest'))
    for values in ((latest, twin), (twin, latest)):
        assert select(*values).selected == twin
    rows = [older, latest, later_registration, different, twin]
    expected = select(*rows)
    rng = random.Random(9)
    for _ in range(10):
        rng.shuffle(rows)
        assert select(*rows) == expected


@pytest.mark.parametrize('payload,reason', [
    ({'response': None}, 'MALFORMED'), ([{'fixture': {'id': 1}}], 'MALFORMED'),
    ({'errors': {'secret': 'DO_NOT_RETAIN'}, 'response': []}, 'PROVIDER_ERROR'),
    ([raw()] * 100, 'OVERSIZED'),
    ({'results': 2, 'response': [raw()]}, 'MALFORMED'),
    ({'paging': {'current': 1, 'total': 2}, 'response': [raw()]}, 'INCOMPLETE_RESPONSE'),
])
def test_M_Q_T13_malformed_latest_never_searches_older(payload, reason):
    older = candidate(identity='older', age=timedelta(minutes=2))
    bad = candidate(payload, identity='bad')
    s = select(older, bad)
    assert s.selected == bad and s.verdict == reason
    b = bundle(current=(older, bad))
    assert b.selections[1].verdict == reason
    assert all(f.value is None for f in replay_evidence(b).result.features)


def test_N_wrong_query_cannot_compete():
    c = candidate()
    wrong = replace(c, header=replace(c.header, source_id='wrong_query', query=Query('/fixtures(results)', (('league', 10), ('season', 2026), ('last', 98), ('status', 'FT')))))
    assert select(wrong).decisions[0].verdict == 'WRONG_QUERY'
    assert select(c, wrong).selected == c
    assert select(candidate(kind=PREVIOUS)).selected is None


@pytest.mark.parametrize('field,expected', [('id', 'WRONG_COMPETITION'), ('season', 'WRONG_SEASON')])
def test_O_P_T16_response_scope_rejected(field, expected):
    row = raw()
    row['league'][field] = 99
    bad = candidate([row])
    assert select(bad).verdict == expected
    assert replay_evidence(bundle(current=(bad,))).inputs.current.source is None


def test_R_identical_duplicates_and_order_deterministic():
    rows = [raw(i) for i in range(1, 5)]
    a = bundle(current=(candidate(rows + [rows[0]]),))
    b = bundle(current=(candidate(list(reversed(rows + [rows[0]]))),))
    assert a == b
    assert len(replay_evidence(a).result.pool.games) == 4
    # Multiplicity is retained for source count integrity, not counted as new matches.
    assert len(replay_evidence(a).inputs.current.rows) == 5


def test_S_T09_conflicts_quarantined_and_retained():
    rows = [raw(i) for i in range(1, 5)] + [raw(1, gf=4)]
    b = bundle(current=(candidate(rows),))
    reverse = bundle(current=(candidate(list(reversed(rows))),))
    assert b == reverse
    result = replay_evidence(b).result
    assert len(result.pool.games) == 3
    assert len(b.exclusions) == 1 and b.exclusions[0].reasons == ('CONFLICTING_FACTS',)
    assert len(b.exclusions[0].facts) == 2
    assert 1 not in [g.fixture.fixture_id for g in result.pool.games]


def test_T_T09_correction_new_evidence_preserves_old_replay():
    old = bundle()
    expected = replay_evidence(old)
    corrected = bundle(current=(candidate([raw(i, gf=2) for i in range(1, 9)], identity='correction'),))
    assert corrected.evidence_hash != old.evidence_hash
    assert corrected.result_hash != old.result_hash
    assert replay_evidence(old) == expected
    # Minimal append-only in-memory test ledger: same key/content idempotent; changes conflict.
    ledger = {}
    def append(key, value):
        if key in ledger:
            if ledger[key] != value:
                raise ValueError('IMMUTABLE_CONFLICT')
        else:
            ledger[key] = value
    append('first', old)
    append('first', old)
    with pytest.raises(ValueError, match='IMMUTABLE_CONFLICT'):
        append('first', corrected)
    append('correction', corrected)
    assert len(ledger) == 2 and replay_evidence(ledger['first']) == expected
    with pytest.raises(FrozenInstanceError):
        old.evidence_hash = corrected.evidence_hash


@pytest.mark.parametrize('minutes,proof,expected', [(90, True, 'VERIFIED_90'), (None, False, 'REGULATION_UNVERIFIED'),
                                                   (90, False, 'REGULATION_UNVERIFIED'), (80, True, 'UNSUPPORTED_REGULATION')])
def test_U_V_W_T19_explicit_format(minutes, proof, expected):
    fmt = FormatEvidence(10, 2026, minutes, 'proof' if proof else None, 'b' * 64 if proof else None,
                         T - timedelta(days=1) if proof else None)
    b = bundle(bind=binding(current_format=fmt))
    assert fmt.verdict(T) == expected
    result = replay_evidence(b).result
    if expected == 'VERIFIED_90':
        assert result.features[0].value == '1.000000'
    else:
        assert all(f.value is None and expected in f.reasons for f in result.features)


def test_format_scope_and_future_proof_fail_closed():
    with pytest.raises(ValueError, match='FORMAT_SCOPE'):
        binding(current_format=FormatEvidence(11, 2026))
    for stamp in (None, T, T + timedelta(seconds=1)):
        fmt = replace(binding().current_format, known_at=stamp)
        assert fmt.verdict(T) == 'REGULATION_UNVERIFIED'


@pytest.mark.parametrize('status,state', [('NS', TargetState.NOT_STARTED), ('1H', TargetState.STARTED), ('2H', TargetState.STARTED),
    ('FT', TargetState.FINISHED), ('AET', TargetState.FINISHED), ('PEN', TargetState.FINISHED),
    ('PST', TargetState.POSTPONED_OR_CANCELLED), ('CANC', TargetState.POSTPONED_OR_CANCELLED),
    ('TBD', TargetState.UNKNOWN), ('ZZZ', TargetState.UNKNOWN), ('HT', TargetState.UNKNOWN)])
def test_X_Y_Z_AA_AB_target_status_mapping(status, state):
    assert target_state(status) == state
    c = candidate([raw(9999, status=status, kickoff=T + timedelta(hours=1))], kind=TARGET)
    if status == 'NS':
        assert replay_evidence(bundle(target=c)).inputs.target.status == 'NS'
    else:
        with pytest.raises(EvidenceUnavailable, match='TARGET_STATUS'):
            bundle(target=c)


def test_T08_target_kickoff_and_crossing_collection_rejected():
    for kickoff in (T, T - timedelta(microseconds=1)):
        with pytest.raises(EvidenceUnavailable):
            bundle(target=candidate([raw(9999, status='NS', kickoff=kickoff)], kind=TARGET))
    late = candidate(kind=TARGET, request_started_at=T - timedelta(seconds=1),
                     retrieval_completed_at=T + timedelta(hours=1), registered_at=T + timedelta(hours=1), known_at=T + timedelta(hours=1))
    with pytest.raises(EvidenceUnavailable, match='TARGET_SOURCE'):
        bundle(target=late)


def test_T06_T08_T16_source_normalization_and_optional_season():
    rows = [raw(1, kickoff=T - timedelta(days=365)), raw(2, kickoff=T - timedelta(days=365, microseconds=1)),
            raw(3, kickoff=T), raw(4, status='1H'), raw(9999), raw(5, kickoff=T + timedelta(days=1))]
    b = bundle(current=(candidate(rows),), previous=(candidate([raw(6, season=2025)], kind=PREVIOUS, identity='previous'),))
    result = replay_evidence(b).result
    assert {g.fixture.fixture_id for g in result.pool.games} == {1, 6}
    reasons = {r for e in result.pool.exclusions for r in e.reasons}
    assert {'OUTSIDE_HISTORY_HORIZON', 'AT_OR_AFTER_CUTOFF', 'TARGET_FIXTURE', 'UNFINISHED_OR_UNSUPPORTED_STATUS'} <= reasons
    assert not replay_evidence(bundle()).result.pool.previous_present
    late = candidate(known_at=T + timedelta(seconds=1))
    assert replay_evidence(bundle(current=(late,))).result.features[0].value is None


@pytest.mark.parametrize('status,fulltime,goals,eligible', [
    ('FT', (None, None), (2, 1), True), ('FT', (1, None), (2, 1), False),
    ('AET', (1, 1), (3, 1), True), ('PEN', (1, 1), (5, 4), True),
    ('AET', (None, None), (3, 1), False), ('PEN', (None, None), (5, 4), False),
    ('AWD', (3, 0), (3, 0), False), ('ABD', (1, 0), (1, 0), False),
])
def test_T20_regulation_only_scores(status, fulltime, goals, eligible):
    row = raw(status=status, gf=fulltime[0], ga=fulltime[1])
    row['goals'] = dict(zip(('home', 'away'), goals))
    b = bundle(current=(candidate([row]),))
    result = replay_evidence(b).result
    assert bool(result.pool.games) == eligible
    if eligible:
        g = result.pool.games[0]
        assert (g.gf_home, g.gf_away) == (goals if status == 'FT' else fulltime)
    else:
        assert b.exclusions


def test_AC_retained_bundle_survives_payload_and_cache_loss():
    payload = [raw(i) for i in range(1, 9)]
    cache = {'one': candidate(payload)}
    b = bundle(current=(cache['one'],))
    expected = replay_evidence(b)
    payload[0]['goals']['home'] = 99
    cache.clear()
    payload.clear()
    assert replay_evidence(b) == expected


@pytest.mark.parametrize('change', ['hash', 'content', 'missing', 'version', 'parser', 'selection', 'exclusions', 'facts_hash', 'input_hash', 'result_hash'])
def test_AE_corruption_fails_closed(change):
    b = bundle()
    if change == 'hash':
        b = replace(b, evidence_hash='0' * 64)
    elif change == 'missing':
        b = None
    elif change == 'version':
        b = replace(b, contract='NEXT')
    elif change in ('content', 'parser', 'selection'):
        s = b.selections[1]
        if change == 'content':
            s = replace(s, selected=replace(s.selected, content=s.selected.content.replace('"goals_home":1', '"goals_home":9')))
        elif change == 'parser':
            header = replace(s.selected.header, parser='NEXT')
            s = replace(s, selected=replace(s.selected, header=header), decisions=(replace(s.decisions[0], header=header),))
        else:
            s = replace(s, verdict='UNAVAILABLE')
        b = replace(b, selections=(b.selections[0], s, b.selections[2]))
        b = replace(b, evidence_hash=evidence_fingerprint(b))  # Inner verification must still reject.
    else:
        if change == 'exclusions':
            b = replace(b, exclusions=(None,))
        elif change == 'facts_hash':
            b = replace(b, validations=(b.validations[0], replace(b.validations[1], normalized_facts_hash='0' * 64), b.validations[2]))
        else:
            b = replace(b, **{change: '0' * 64})
        b = replace(b, evidence_hash=evidence_fingerprint(b))
    with pytest.raises(EvidenceUnavailable, match='EVIDENCE_UNAVAILABLE'):
        replay_evidence(b)


def test_AG_material_evidence_sensitivity_and_sanitization():
    original = bundle()
    c = candidate()
    for h in (replace(c.header, source_id='new_version'),
              replace(c.header, timing=replace(c.header.timing, provider_updated_at=T - timedelta(days=1))),
              replace(c.header, timing=replace(c.header.timing, registered_at=T - timedelta(seconds=2), known_at=T - timedelta(seconds=2)))):
        assert bundle(current=(replace(c, header=h),)).evidence_hash != original.evidence_hash
    fmt = replace(binding().current_format, proof_hash='d' * 64)
    assert bundle(bind=binding(current_format=fmt)).evidence_hash != original.evidence_hash
    row = raw()
    row.update({'authorization': 'SECRET', 'players': [{'private': 'SECRET'}], 'telegram': 'SECRET', 'path': '/secret/file'})
    row['fixture']['irrelevant'] = 'SECRET'
    assert sanitize_payload([row]) == sanitize_payload([raw()])
    assert 'SECRET' not in canonical_bytes(bundle(current=(candidate([row]),))).decode()
    with pytest.raises(TypeError):
        replace(original, log_receipt='not semantic')


def test_immutable_source_identity_conflicts():
    a, b = candidate(), candidate([raw(gf=3)])
    assert select(a, b).verdict == 'IMMUTABLE_SOURCE_CONFLICT'
    assert select(a, a) == select(a)
    with pytest.raises(FrozenInstanceError):
        a.content = b.content


def test_empty_missing_stale_distinct_and_previous_optional():
    empty = replay_evidence(bundle(current=(candidate([]),)))
    missing = replay_evidence(bundle(current=()))
    stale = replay_evidence(bundle(current=(candidate(age=timedelta(hours=6)),)))
    assert empty.result.features[0].sample_count == 0
    assert missing.result.features[0].sample_count is None
    assert 'STALE_SOURCE' in stale.result.features[0].reasons
    b = bundle(previous=(candidate(kind=PREVIOUS, age=timedelta(hours=24), identity='old'),))
    assert replay_evidence(b).result.features[0].status == Status.AVAILABLE


def test_AD_AH_AI_AJ_AK_AL_T32_offline_inert_and_zero_side_effects():
    package = Path(__file__).resolve().parents[1] / 'app' / 'prematch_football_context'
    for filename in ('sources.py', 'source_adapter.py', 'evidence.py'):
        tree = ast.parse((package / filename).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.level == 1 or node.module in {'dataclasses', 'datetime', 'enum', 'typing'}
            if isinstance(node, ast.Import):
                assert all(a.name in {'re', 'json'} for a in node.names)
    script = '''
import os, socket, sqlite3, sys
from unittest.mock import patch

def audit(event, args):
    if event.startswith(('socket.', 'sqlite3.connect')):
        raise AssertionError('I/O attempted')
    if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        raise AssertionError('write attempted')
sys.addaudithook(audit)
def fail(*args, **kwargs):
    raise AssertionError('side effect')
with patch.object(socket, 'socket', fail), patch.object(sqlite3, 'connect', fail), patch.object(os, 'getenv', fail):
    from tests.test_prematch_football_context_sources import bundle, replay_evidence
    b = bundle()
    assert replay_evidence(b) == replay_evidence(b)
    assert not any(n.startswith(('app.football', 'app.lab_v2_shadow', 'app.adaptive_lab', 'app.live_lab', 'telegram', 'app.reviewed_historical_odds')) for n in sys.modules)
print('OFFLINE_PASS')
'''
    # pytest imports can consult environment; load test module before blocking getenv.
    script = script.replace("with patch.object(socket", "import tests.test_prematch_football_context_sources\nwith patch.object(socket")
    completed = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == 'OFFLINE_PASS'


def test_T09_future_correction_is_not_available_at_original_cutoff():
    old = candidate(identity='old')
    late = candidate([raw(gf=9)], identity='new', retrieval_completed_at=T + timedelta(seconds=1),
                     registered_at=T + timedelta(seconds=2), known_at=T + timedelta(seconds=2))
    assert select(old, late).selected == old
    original = bundle(current=(old,))
    assert replay_evidence(original) == replay_evidence(bundle(current=(old, late)))
    future = select_source((old, late), history_query(10, 2026), cutoff=T + timedelta(minutes=1), source_kind=CURRENT)
    assert future.selected == late


def test_T08_completion_not_observed_cannot_enter_history():
    c = candidate([raw(kickoff=T - timedelta(seconds=10))])
    b = bundle(current=(c,))
    assert not replay_evidence(b).result.pool.games
    assert b.exclusions[0].reasons == ('COMPLETION_NOT_OBSERVED',)


def test_target_identity_and_source_versions_fail_closed():
    c = candidate([raw(9998, status='NS', kickoff=T + timedelta(hours=1))], kind=TARGET)
    assert select(c, kind=TARGET).verdict == 'WRONG_TARGET'
    with pytest.raises(EvidenceUnavailable):
        bundle(target=c)
    c = candidate()
    changed = replace(c, header=replace(c.header, parser='UNSUPPORTED_PARSER'))
    assert select(c, changed).verdict == 'IMMUTABLE_SOURCE_CONFLICT'
    assert select(changed).verdict == 'VERSION_MISMATCH'
    with pytest.raises(EvidenceUnavailable, match='SOURCE_VERSION_MISMATCH'):
        bundle(current=(changed,))


def test_target_equality_proof_and_neutral_designation():
    row = raw(9999, status='NS', kickoff=T + timedelta(hours=1), gf=None, ga=None)
    row['fixture']['neutral'] = True
    c = candidate([row], kind=TARGET, retrieval_completed_at=T, registered_at=T, known_at=T)
    proof = CaptureOrder(T, c.header.source_id, c.header.content_hash, 'e' * 64)
    c = replace(c, header=replace(c.header, timing=replace(c.header.timing, before_capture=proof)))
    result = replay_evidence(bundle(target=c)).result
    assert result.target.neutral == Neutral.TRUE
    assert (result.target.home_team_id, result.target.away_team_id) == (1, 2)


def test_sanitized_invalid_field_retained_and_not_repaired():
    row = raw()
    row['goals']['home'] = 'SECRET_OR_INVALID'
    c = candidate([row])
    assert 'SECRET_OR_INVALID' not in c.content and 'INVALID' in c.content
    assert select(c).verdict == 'MALFORMED'
    assert replay_evidence(bundle(current=(c,))).inputs.current.source is None


def test_error_marker_cannot_smuggle_unsanitized_retained_payload():
    c = candidate()
    doc = {'error': 'PROVIDER_ERROR', 'count': 1, 'rows': [{'authorization': 'SECRET'}]}
    malicious = replace(c, header=replace(c.header, content_hash=digest(doc)), content=canonical_bytes(doc).decode())
    assert select(malicious).verdict == 'MALFORMED'
    with pytest.raises(EvidenceUnavailable):
        bundle(current=(malicious,))


def test_immutable_identity_conflict_across_source_kinds():
    target = candidate(kind=TARGET, identity='source1')
    with pytest.raises(EvidenceUnavailable, match='IMMUTABLE_SOURCE_CONFLICT'):
        bundle(target=target)
