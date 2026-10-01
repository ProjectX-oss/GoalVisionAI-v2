"""Scope index must preserve pins, replay and fail-closed integrity."""
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path

import pytest

from app.prematch_football_context.capture.adapter import CaptureScope
from app.prematch_football_context.capture.repository import EvidenceRepository
from app.prematch_football_context.evidence import EvidenceUnavailable
from app.prematch_football_context.sources import SourceKind, history_query, target_query
from app.prematch_football_context.snapshot.service import available_pins, assemble, KINDS
from tests.test_prematch_football_context_capture import material, TARGET, END
from tests.test_prematch_football_context_snapshot import stores, capture, OPPORTUNITY, no_network
from tests.test_prematch_football_context_sources import T, binding, raw


def reference_pins(repo, receipt, scope):
    queries = (target_query(scope.fixture_id), history_query(scope.competition_id, scope.season),
               history_query(scope.competition_id, scope.season - 1))
    pins = [[], [], []]
    for (identity,) in repo.connection.execute(
            "SELECT source_id FROM fc_receipts WHERE event='SOURCE' AND ordering<? ORDER BY ordering",
            (receipt.ordering,)):
        candidate = repo.load(identity, decision=receipt)
        for index, key in enumerate(zip(KINDS, queries)):
            if (candidate.header.kind, candidate.header.query) == key:
                pins[index].append(identity)
    return tuple(tuple(sorted(group)) for group in pins)


def unrelated(repo, fixture=10000):
    scope = CaptureScope(target_query(fixture), SourceKind.TARGET, timedelta(minutes=2))
    return repo.register(material(scope=scope, payload=[
        raw(fixture, status='NS', kickoff=T + timedelta(hours=1), gf=None, ga=None)]))


def test_reuses_one_full_validation_across_scopes_and_preserves_snapshot(stores, monkeypatch):
    repo, _ = stores
    capture(repo)
    for fixture in range(10000, 10020):
        unrelated(repo, fixture)
    receipt = repo.capture_cutoff()
    expected = reference_pins(repo, receipt, binding())
    other = replace(binding(), fixture_id=10000)
    other_expected = reference_pins(repo, receipt, other)
    snapshot = assemble(repo, OPPORTUNITY, receipt, binding(), source_candidates=expected)
    original, loaded = repo.load, []
    def counted(identity, *, decision=None):
        loaded.append(identity)
        return original(identity, decision=decision)
    monkeypatch.setattr(repo, 'load', counted)
    for _ in range(10):
        assert available_pins(repo, receipt, binding()) == expected
        assert available_pins(repo, receipt, other) == other_expected
    assert len(loaded) == 23  # One full pass, not 20 passes over 23 sources.
    assert assemble(repo, OPPORTUNITY, receipt, binding()) == snapshot
    assert len(loaded) == 23 + sum(map(len, expected))  # Pins still revalidated.


@pytest.mark.parametrize('external', [False, True])
@pytest.mark.parametrize('damage', ['body', 'scope', 'receipt', 'delete', 'unrelated'])
def test_warm_index_detects_local_and_other_connection_corruption(stores, external, damage):
    repo, _ = stores
    target, _, _ = capture(repo)
    other = unrelated(repo)
    receipt = repo.capture_cutoff()
    available_pins(repo, receipt, binding())
    writer = EvidenceRepository(Path(repo.connection.execute('PRAGMA database_list').fetchone()[2]),
                                writable=True, clock=lambda: T) if external else repo
    identity = other.source_id if damage == 'unrelated' else target.source_id
    try:
        db = writer.connection
        if damage == 'receipt':
            db.execute('DROP TRIGGER fc_receipts_no_update')
            db.execute("UPDATE fc_receipts SET receipt_hash=? WHERE source_id=?", ('0'*64, identity))
        elif damage == 'delete':
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute('DROP TRIGGER fc_sources_no_delete')
            db.execute('DELETE FROM fc_sources WHERE source_id=?', (identity,))
        else:
            db.execute('DROP TRIGGER fc_sources_no_update')
            document = '{}'
            if damage == 'scope':
                document = json.loads(db.execute(
                    'SELECT material_json FROM fc_sources WHERE source_id=?', (identity,)).fetchone()[0])
                document['query']['parameters'] = [['id', 12345]]
                document = json.dumps(document)
            db.execute('UPDATE fc_sources SET material_json=? WHERE source_id=?', (document, identity))
        with pytest.raises(EvidenceUnavailable):
            available_pins(repo, receipt, binding())
    finally:
        if external:
            writer.close()


@pytest.mark.parametrize('external', [False, True])
def test_append_invalidates_index_without_leaking_later_sources(stores, external):
    repo, _ = stores
    capture(repo)
    first = repo.capture_cutoff()
    original = available_pins(repo, first, binding())
    writer = EvidenceRepository(Path(repo.connection.execute('PRAGMA database_list').fetchone()[2]),
                                writable=True, clock=lambda: T) if external else repo
    try:
        added = writer.register(material(end=END + timedelta(seconds=1)))
        assert available_pins(repo, first, binding()) == original
        second = writer.capture_cutoff()
        latest = available_pins(repo, second, binding())
        assert added.source_id in latest[1]
        assert latest == reference_pins(repo, second, binding())
        assert available_pins(repo, first, binding()) == original
    finally:
        if external:
            writer.close()


def test_concurrent_change_discards_partial_index(stores, monkeypatch):
    repo, _ = stores
    capture(repo)
    receipt = repo.capture_cutoff()
    writer = EvidenceRepository(Path(repo.connection.execute('PRAGMA database_list').fetchone()[2]),
                                writable=True, clock=lambda: T)
    original = repo.load
    changed = False
    def mutate_once(identity, *, decision=None):
        nonlocal changed
        result = original(identity, decision=decision)
        if not changed:
            changed = True
            unrelated(writer)
        return result
    monkeypatch.setattr(repo, 'load', mutate_once)
    try:
        with pytest.raises(EvidenceUnavailable, match='SOURCE_INDEX_CHANGED'):
            available_pins(repo, receipt, binding())
        assert available_pins(repo, receipt, binding()) == reference_pins(repo, receipt, binding())
    finally:
        writer.close()


def test_failed_build_retries_full_validation_and_warm_marker_is_verified(stores, monkeypatch):
    repo, _ = stores
    capture(repo)
    receipt = repo.capture_cutoff()
    original, count = repo.load, 0
    def fail_second(identity, *, decision=None):
        nonlocal count
        count += 1
        if count == 2:
            raise EvidenceUnavailable('INJECTED')
        return original(identity, decision=decision)
    monkeypatch.setattr(repo, 'load', fail_second)
    with pytest.raises(EvidenceUnavailable, match='INJECTED'):
        available_pins(repo, receipt, binding())
    assert available_pins(repo, receipt, binding()) == reference_pins(repo, receipt, binding())
    assert count == 8  # 2 failed + 3 rebuilt + 3 reference loads.
    with pytest.raises(EvidenceUnavailable):
        available_pins(repo, replace(receipt, ordering=receipt.ordering+1), binding())
    repo.connection.execute('DROP TRIGGER fc_receipts_no_update')
    repo.connection.execute("UPDATE fc_receipts SET receipt_hash=? WHERE event='DECISION'", ('0'*64,))
    with pytest.raises(EvidenceUnavailable):
        available_pins(repo, receipt, binding())
