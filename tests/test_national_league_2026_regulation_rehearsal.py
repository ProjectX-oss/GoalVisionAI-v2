"""Genuine exact-scope regulation; synthetic football, identities and injected clock."""
from contextlib import closing, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
import io
import json
from pathlib import Path

import pytest

from app.prematch_football_context.fingerprint import canonical_bytes, canonical_data
from app.prematch_football_context.readiness.__main__ import main as readiness_cli
from app.prematch_football_context.readiness.regulations import verify_retained
from app.prematch_football_context.regulation_registry import Registry, format_evidence, resolve
from app.prematch_football_context.regulation_registry.__main__ import main as registry_cli
from app.prematch_football_context.regulation_registry.contracts import decode
from app.prematch_football_context.regulation_registry.service import Resolution
from app.prematch_football_context.snapshot.service import reproduce
from tests.test_prematch_registry_readiness import offline, start
from tests.test_prematch_football_context_readiness import ID, ROW
from tests.test_prematch_football_context_sources import raw

EVIDENCE = Path(__file__).resolve().parents[1] / 'docs/rehearsals/national_league_2026_regulation'


def test_national_league_review_and_readiness(tmp_path: Path, offline: None) -> None:
    """Replay import, exact boundaries and real readiness using no provider client."""
    law, fa = (decode((EVIDENCE / name).read_text()) for name in ('ifab.json', 'the_fa.json'))
    exported = json.loads((EVIDENCE / 'offline_export.json').read_text())
    now = datetime.fromisoformat(exported['resolution']['cutoff'].replace('Z', '+00:00'))
    db = tmp_path / 'regulations.sqlite'
    with redirect_stdout(io.StringIO()):
        assert registry_cli(['init', '--db', str(db)]) == 0
        for name in ('ifab.json', 'the_fa.json'):
            assert registry_cli(['validate', str(EVIDENCE / name)]) == 0
            assert registry_cli(['import', '--db', str(db), str(EVIDENCE / name)]) == 0
    assert law.regulation_minutes == 90 and fa.regulation_minutes is None
    assert fa.organizer == 'THE_FA'
    assert law.validity_start is fa.validity_start is None
    assert fa.source_effective_until - law.reviewed_at <= timedelta(days=7)
    fixture_day = datetime.fromisoformat('2026-09-26T14:00:00+00:00')
    assert max(law.reviewed_at, fa.reviewed_at) < now < fixture_day < fa.source_effective_until

    def lookup(**changes: object) -> Resolution:
        return resolve(db, **(dict(provider='API_FOOTBALL', competition_id=43, season=2026,
                                   cutoff=now) | changes))

    result = lookup()
    assert result.verdict == 'VERIFIED_90'
    assert canonical_data(result) == exported['resolution']
    assert result.fingerprint == exported['resolution_fingerprint']
    assert canonical_data(format_evidence(result, cutoff=now)) == exported['format_evidence']
    before = db.read_bytes()
    with closing(Registry(db, writable=True)) as registry:
        registry.append(fa)
        registry.append(law)
        assert len(registry.verify()) == 2
    assert db.read_bytes() == before and canonical_bytes(lookup()) == canonical_bytes(result)
    for change in ({'competition_id': n} for n in (2, 39, 40, 42, 44, 50, 51, 1000)):
        assert lookup(**change).verdict == 'REGULATION_UNVERIFIED'
    for season in (2025, 2027):
        assert lookup(season=season).verdict == 'REGULATION_UNVERIFIED'
    for review in (law, fa):
        for cutoff in (review.reviewed_at - timedelta(microseconds=1), review.reviewed_at,
                       review.source_effective_until):
            assert lookup(cutoff=cutoff).verdict == 'REGULATION_UNVERIFIED'
    for records in ((law,), (fa,)):
        assert format_evidence(replace(result, records=records), cutoff=now).minutes is None
    damaged = canonical_data(fa)
    damaged['incorporation']['base_evidence_fingerprint'] = '0' * 64
    with pytest.raises(ValueError):
        decode(json.dumps(damaged))

    root = tmp_path / 'synthetic-readiness'
    observation = start(root, db, lambda: now, 43)
    # Keep the reviewed lower-division profile; category adaptation is unchanged.
    observation.prepare(((9999, 43, 2026, 'LOWER_DIVISION_OR_SEMIPRO', *ROW[4:]),))
    target = raw(9999, status='NS', kickoff=now + timedelta(hours=1), gf=None, ga=None)
    target['league']['id'] = 43
    observation.capture('/fixtures', {'id': 9999}, [target], now)
    rows = [raw(i, home=1 if i < 5 else 2, away=100+i,
                kickoff=now-timedelta(days=i)) for i in range(1, 9)]
    for row in rows:
        row['league']['id'] = 43
    observation.capture('/fixtures', {'league': 43, 'season': 2026, 'status': 'FT', 'last': 99}, rows, now)
    identity = replace(ID, competition_id=43)
    observation.bind(observation.begin(), (identity,))
    observation.observe(identity, new_opportunity=True)
    snapshot = observation.snapshots.load('9999:HOME_WIN')
    assert snapshot.binding.current_format.verdict(now) == 'VERIFIED_90'
    assert snapshot.binding.previous_format.verdict(now) == 'REGULATION_UNVERIFIED'
    assert snapshot.projection.missing == (0, 0, 0, 0, 1, 1, 1)
    assert snapshot.projection.reasons[4:] == (
        ('UNSUPPORTED_PI_STATE',), ('UNSUPPORTED_PI_STATE',), ('INSUFFICIENT_SAMPLE',))
    assert reproduce(observation.evidence, snapshot) == snapshot
    events, bad = observation.ledger.read()
    assert not bad
    verify_retained(snapshot, events, observation.run_id)
    proof = next(doc for kind, _, doc in events if kind == 'REGULATION_PROOF')
    assert proof['resolution_fingerprint'] == result.fingerprint
    db.rename(tmp_path / 'regulations-original-unavailable.sqlite')
    assert not db.exists()
    observation.finish(completed=True)
    files_before = {p.name: p.read_bytes() for p in root.iterdir()}
    reports = {}
    for command in ('report', 'verify', 'diagnostics'):
        with redirect_stdout(io.StringIO()) as stream:
            assert readiness_cli(['--root', str(root), command]) == 0
        reports[command] = json.loads(stream.getvalue())
        assert reports[command]['reproduction']['VERIFIED'] == 1
    assert files_before == {p.name: p.read_bytes() for p in root.iterdir()}
    manifest = json.loads((EVIDENCE / 'source_manifest.json').read_text())
    for path, expected in manifest['preserved_artifact_sha256'].items():
        assert hashlib.sha256((EVIDENCE.parents[2] / path).read_bytes()).hexdigest() == expected
    (tmp_path / 'rehearsal.json').write_text(json.dumps(canonical_data({
        'football': 'SYNTHETIC; fixture 9999 is not a provider observation or the public fixture',
        'clock': now, 'registry_unavailable': True, 'readiness_root': str(root),
        'snapshot': snapshot, 'retained_events': events, 'offline_reports': reports,
    }), indent=2) + '\n')
