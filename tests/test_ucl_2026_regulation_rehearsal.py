"""Offline reproduction of the retained real review; never fetch sources."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
import socket
import sqlite3

import httpx
import pytest

from app.prematch_football_context.fingerprint import canonical_bytes, canonical_data
from app.prematch_football_context.regulation_registry import (
    Registry, Verdict, format_evidence, initialize, resolve,
)
from app.prematch_football_context.regulation_registry.contracts import decode, digest
from app.prematch_football_context.regulation_registry.repository import TABLE, SCHEMA
from app.prematch_football_context.regulation_registry.service import Resolution

EVIDENCE = Path(__file__).resolve().parents[1] / 'docs/rehearsals/ucl_2026_regulation'


def test_retained_ucl_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reimport exact reviews, reproduce exported proof, and fail closed at boundaries."""
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail('NETWORK_FORBIDDEN')

    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    law, competition = (decode((EVIDENCE / name).read_text()) for name in ('ifab.json', 'uefa.json'))
    exported = json.loads((EVIDENCE / 'offline_export.json').read_text())
    cutoff = datetime.fromisoformat(exported['resolution']['cutoff'].replace('Z', '+00:00'))
    db = tmp_path / 'new-test-registry.sqlite'
    initialize(db)

    def lookup(**changes: object) -> Resolution:
        return resolve(db, **(dict(provider='API_FOOTBALL', competition_id=2, season=2026,
                                   cutoff=cutoff) | changes))

    with closing(Registry(db, writable=True)) as registry:
        registry.append(law)
    assert lookup().verdict == Verdict.REGULATION_UNVERIFIED  # IFAB alone
    with closing(Registry(db, writable=True)) as registry:
        registry.append(competition)
        assert len(registry.verify()) == 2
    result = lookup()
    assert result.verdict == Verdict.VERIFIED_90
    assert law.regulation_minutes == 90 and competition.regulation_minutes is None
    assert canonical_data(result) == exported['resolution']
    assert result.fingerprint == exported['resolution_fingerprint']
    assert digest('FC_V2_REGULATION_RESOLUTION_V1', exported['resolution']) == result.fingerprint
    fmt = format_evidence(result, cutoff=cutoff)
    assert canonical_data(fmt) == exported['format_evidence']
    assert fmt.proof_hash == result.fingerprint

    # Synthetic scores exercise the real UCL proof; they are not match evidence.
    from app.prematch_football_context.evidence import Binding, retain_evidence, replay_evidence
    from app.prematch_football_context.source_adapter import FormatEvidence, sanitize_payload, source_candidate
    from app.prematch_football_context.sources import (
        SourceHeader, SourceKind, Timing, digest as source_digest, history_query, select_source, target_query,
    )
    from tests.test_prematch_football_context_sources import C, raw

    for status in ('AET', 'PEN'):
        for explicit in (False, True):
            rows = [raw(i, status=status, kickoff=cutoff-timedelta(days=i),
                        gf=1 if explicit else None, ga=1 if explicit else None) for i in range(1, 9)]
            target = [raw(9999, status='NS', kickoff=cutoff+timedelta(hours=1), gf=None, ga=None)]
            for row in rows + target:
                row['league']['id'] = 2
            for row in rows:
                row['goals'] = {'home': 4, 'away': 3}
            selections = []
            for kind, query, payload in ((SourceKind.TARGET, target_query(9999), target),
                                         (SourceKind.CURRENT, history_query(2, 2026), rows)):
                content = json.loads(sanitize_payload(payload))
                known = cutoff-timedelta(seconds=1)
                header = SourceHeader('SYNTHETIC_UCL_SCORE_' + kind.value, query, kind,
                                      Timing(known, known, known, cutoff+timedelta(hours=1)),
                                      source_digest(content))
                candidate = source_candidate(header, payload)
                selections.append(select_source((candidate,), query, cutoff=cutoff, source_kind=kind))
            selections.append(select_source((), history_query(2, 2025), cutoff=cutoff,
                                            source_kind=SourceKind.PREVIOUS))
            binding = Binding(9999, 2, 2026, cutoff, C, fmt, FormatEvidence(2, 2025))
            replay = replay_evidence(retain_evidence(binding, tuple(selections))).result
            if explicit:
                assert replay.features[0].value == replay.features[1].value == '1.000000'
            else:
                assert all(f.value is None for f in replay.features)
                assert all('INVALID_REGULATION_SCORE_PAIR' in e.reasons for e in replay.pool.exclusions)

    before = db.read_bytes()
    with closing(Registry(db, writable=True)) as registry:
        registry.append(competition)
        registry.append(law)
        assert len(registry.verify()) == 2
    assert db.read_bytes() == before
    assert canonical_bytes(lookup()) == canonical_bytes(result)  # closed/reopened
    assert format_evidence(lookup(), cutoff=cutoff) == fmt
    for scope in ({'competition_id': 3}, {'season': 2025}, {'season': 2027}):
        assert lookup(**scope).verdict == Verdict.REGULATION_UNVERIFIED
    for review in (law, competition):
        for at in (review.reviewed_at - timedelta(microseconds=1), review.reviewed_at,
                   review.source_effective_until):
            assert lookup(cutoff=at).verdict == Verdict.REGULATION_UNVERIFIED
    for retained in ((law,), (competition,)):
        assert format_evidence(replace(result, records=retained), cutoff=cutoff).minutes is None
    for original, key in ((law, 'regulation_minutes'), (competition, 'incorporation')):
        damaged = canonical_data(original)
        if key == 'incorporation':
            damaged[key]['base_evidence_fingerprint'] = '0' * 64
        else:
            damaged[key] = 80
        with pytest.raises(ValueError):
            decode(json.dumps(damaged))
    # Deliberately corrupt only this disposable test store, restoring schema so
    # row-content validation (not just missing-trigger validation) is exercised.
    damaged = canonical_data(competition)
    damaged['incorporation']['base_review_id'] = 'MISSING'
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute(f'DROP TRIGGER {TABLE}_no_update')
        connection.execute(f'UPDATE {TABLE} SET document=? WHERE review_id=?',
                           (json.dumps(damaged), competition.review_id))
        connection.execute(SCHEMA[1])
    assert lookup().reason == 'REGISTRY_UNAVAILABLE_OR_INVALID'
    assert lookup().verdict == Verdict.REGULATION_UNVERIFIED
