"""Entirely synthetic reviewed chains; authority-shaped URLs are not real evidence."""
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import sqlite3

import pytest

from app.prematch_football_context.capture.repository import ImmutableConflict
from app.prematch_football_context.fingerprint import canonical_bytes
from app.prematch_football_context.regulation_registry import (
    Incorporation, IncorporatedCompetitionRegulation, Registry, ReviewedCompetitionRegulation, SourceType, Verdict,
    format_evidence, initialize,
)
from app.prematch_football_context.regulation_registry.contracts import (
    INCORPORATED_VERSION, LINK_VERSION, decode, digest,
)
from app.prematch_football_context.regulation_registry.repository import TABLE, SCHEMA
from tests.test_prematch_football_context_regulation_registry import (
    T, append, db, lookup, no_network, record,
)


def base(**changes: object) -> ReviewedCompetitionRegulation:
    """Synthetic base-law review retains the accepted exact-scope contract."""
    return record(**(dict(review_id='SYNTHETIC_BASE', organizer='IFAB',
        source_type=SourceType.IFAB_BASE_LAW,
        source_url='https://theifab.com/SYNTHETIC-LAW',
        reviewed_statement='SYNTHETIC law: two 45 minute halves.') | changes))


def competition(law: ReviewedCompetitionRegulation | None = None, *,
                link_changes: dict[str, object] | None = None,
                **changes: object) -> IncorporatedCompetitionRegulation:
    """Synthetic competition claims incorporation, never an invented duration."""
    law = base() if law is None else law
    owner = changes.get('review_id', 'SYNTHETIC_COMPETITION')
    edge = dict(competition_review_id=owner, base_review_id=law.review_id,
                base_evidence_fingerprint=law.evidence_fingerprint,
                reviewed_statement='SYNTHETIC competition explicitly incorporates SYNTHETIC law.',
                relationship='INCORPORATES')
    edge.update(link_changes or {})
    edge['fingerprint'] = digest(LINK_VERSION, edge)
    content = replace(record().retained_source_content,
                      excerpt='SYNTHETIC competition matches conform to SYNTHETIC base law.',
                      section='SYNTHETIC incorporation article')
    doc = record(retained_source_content=content).fingerprint_material()
    doc.update(review_id=owner, regulation_minutes=None, evidence_version=INCORPORATED_VERSION,
               reviewed_statement='SYNTHETIC incorporation only; no explicit duration.',
               incorporation=Incorporation(**edge))
    doc.update(changes)
    doc['source_content_sha256'] = digest('FC_V2_REGULATION_SOURCE_V1', doc['retained_source_content'])
    doc['evidence_fingerprint'] = digest(INCORPORATED_VERSION, doc)
    return IncorporatedCompetitionRegulation(**doc)


@pytest.mark.parametrize('items', [(base(),), (competition(),), ()])
def test_incomplete_or_no_incorporation(db: Path, items: tuple) -> None:
    append(db, *items)
    result = lookup(db)
    assert result.verdict == Verdict.REGULATION_UNVERIFIED
    assert format_evidence(result, cutoff=T).minutes is None


def test_complete_truthful_chain_offline_reproduction(db: Path, tmp_path: Path) -> None:
    law, comp = base(), competition()
    append(db, comp, law)
    before = db.read_bytes()
    result = lookup(db)
    assert result.verdict == Verdict.VERIFIED_90
    assert comp.regulation_minutes is None and law.regulation_minutes == 90
    assert set(result.records) == {comp, law}
    exported = json.loads(canonical_bytes(result))
    restored = replace(result, records=tuple(decode(json.dumps(r)) for r in exported['records']))
    assert restored == result
    assert digest('FC_V2_REGULATION_RESOLUTION_V1', exported) == result.fingerprint
    assert format_evidence(restored, cutoff=T).proof_hash == result.fingerprint
    assert format_evidence(restored, cutoff=T).known_at == max(comp.reviewed_at, law.reviewed_at)
    second = tmp_path/'reverse.db'
    initialize(second)
    append(second, law, comp)
    assert lookup(second) == result == lookup(db)
    assert db.read_bytes() == before
    assert format_evidence(replace(result, records=(comp,)), cutoff=T).minutes is None
    assert format_evidence(replace(result, records=(law,)), cutoff=T).minutes is None


@pytest.mark.parametrize('scope', [{'competition_id': 11}, {'season': 2025}, {'season': 2027}, {'provider': 'OTHER'}])
def test_exact_scope(db: Path, scope: dict) -> None:
    append(db, competition(), base())
    assert lookup(db, **scope).verdict == Verdict.REGULATION_UNVERIFIED


@pytest.mark.parametrize('side', ['competition', 'base'])
@pytest.mark.parametrize('change', [
    {'reviewed_at': T}, {'reviewed_at': T+timedelta(seconds=1)},
    {'source_effective_until': T}, {'source_effective_from': T+timedelta(seconds=1)},
    {'season': 2027}, {'competition_id': 11},
])
def test_independent_asof_and_scope(db: Path, side: str, change: dict) -> None:
    law = base(**change) if side == 'base' else base()
    comp = competition(law, **change) if side == 'competition' else competition(law)
    append(db, comp, law)
    assert lookup(db).verdict == Verdict.REGULATION_UNVERIFIED


@pytest.mark.parametrize('edge', [{'base_review_id': 'MISSING'}, {'base_evidence_fingerprint': '0'*64},
                                  {'base_review_id': 'SYNTHETIC_REVIEW_1'}])
def test_wrong_link_target(db: Path, edge: dict) -> None:
    append(db, competition(link_changes=edge), base(), record())
    assert lookup(db).verdict == Verdict.REGULATION_UNVERIFIED


@pytest.mark.parametrize('damage', ['missing', 'target', 'edge_hash', 'owner', 'base_content', 'base_hash'])
def test_tampered_import(damage: str) -> None:
    doc = json.loads(canonical_bytes(base() if damage.startswith('base') else competition()))
    if damage == 'missing':
        del doc['incorporation']
    elif damage == 'target':
        doc['incorporation']['base_review_id'] = 'CHANGED'
    elif damage == 'edge_hash':
        doc['incorporation']['fingerprint'] = '0'*64
    elif damage == 'owner':
        doc['incorporation']['competition_review_id'] = 'CHANGED'
    elif damage == 'base_content':
        doc['retained_source_content']['excerpt'] = 'CHANGED'
    else:
        doc['evidence_fingerprint'] = '0'*64
    with pytest.raises(ValueError):
        decode(json.dumps(doc))


@pytest.mark.parametrize('side', ['competition', 'base'])
def test_persisted_tampering_rejected(db: Path, side: str) -> None:
    append(db, competition(), base())
    item = competition() if side == 'competition' else base()
    doc = json.loads(canonical_bytes(item))
    if side == 'competition':
        doc['incorporation']['base_review_id'] = 'CHANGED'
    else:
        doc['regulation_minutes'] = 80
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(f'DROP TRIGGER {TABLE}_no_update')
        conn.execute(f'UPDATE {TABLE} SET document=? WHERE review_id=?',
                     (json.dumps(doc), item.review_id))
        conn.execute(SCHEMA[1])
    assert lookup(db).verdict == Verdict.REGULATION_UNVERIFIED


@pytest.mark.parametrize('kind', ['explicit', 'second_direct', 'second_chain'])
def test_conflicting_durations(db: Path, kind: str) -> None:
    law = base()
    append(db, law, competition(regulation_minutes=80) if kind == 'explicit' else competition())
    if kind == 'second_direct':
        append(db, record(regulation_minutes=80))
    if kind == 'second_chain':
        other = base(review_id='SYNTHETIC_OTHER_LAW', regulation_minutes=80)
        append(db, other, competition(other, review_id='SYNTHETIC_OTHER_COMPETITION'))
    result = lookup(db)
    assert result.verdict == Verdict.CONFLICTING_REGULATION_EVIDENCE
    assert format_evidence(result, cutoff=T).minutes is None


@pytest.mark.parametrize('sql', [f'UPDATE {TABLE} SET document=document', f'DELETE FROM {TABLE}',
    f'INSERT OR REPLACE INTO {TABLE} SELECT * FROM {TABLE}', f'REPLACE INTO {TABLE} SELECT * FROM {TABLE}'])
def test_chain_sql_guards(db: Path, sql: str) -> None:
    append(db, base(), competition())
    with closing(sqlite3.connect(db)) as conn:
        with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE'):
            conn.execute(sql)
    assert lookup(db).verdict == Verdict.VERIFIED_90


def test_changed_link_replay_and_complete_hash(db: Path, tmp_path: Path) -> None:
    append(db, base(), competition(), competition())
    original = lookup(db)
    changed = competition(link_changes={'reviewed_statement': 'SYNTHETIC revised incorporation review.'})
    with pytest.raises(ImmutableConflict):
        append(db, changed)
    with closing(Registry(db)) as registry:
        with pytest.raises(ValueError, match='READ_ONLY'):
            registry.append(changed)
    other = tmp_path/'other.db'
    initialize(other)
    append(other, base(), changed)
    assert lookup(other).verdict == Verdict.VERIFIED_90
    assert lookup(other).fingerprint != original.fingerprint
    assert format_evidence(lookup(other), cutoff=T).proof_hash != format_evidence(original, cutoff=T).proof_hash
    third = tmp_path/'third.db'
    initialize(third)
    revised = base(reviewer='SYNTHETIC_OTHER_REVIEWER')
    append(third, revised, competition(revised))
    assert lookup(third).fingerprint != original.fingerprint


def test_unlinked_base_cannot_override_direct_authority(db: Path) -> None:
    append(db, base(), record(regulation_minutes=80))
    assert lookup(db).verdict == Verdict.UNSUPPORTED_REGULATION


def test_later_base_never_upgrades_earlier_decision(db: Path) -> None:
    law = base(reviewed_at=T+timedelta(seconds=1))
    append(db, competition(law))
    earlier = lookup(db)
    append(db, law)
    assert lookup(db) == earlier
    assert lookup(db, cutoff=T+timedelta(seconds=2)).verdict == Verdict.VERIFIED_90


@pytest.mark.parametrize('case', ['features', 'parity', 'snapshots', 'AET_explicit', 'AET_missing',
                                  'PEN_explicit', 'PEN_missing'])
def test_chain_existing_integration_contracts(db: Path, tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    """Run accepted bridge/runtime regressions with incorporated proof instead."""
    from tests import test_prematch_football_context_regulation_registry as accepted
    append(db, base())
    monkeypatch.setattr(accepted, 'record', competition)
    if case == 'features':
        accepted.test_bridge_preserves_seven_feature_results(db)
    elif case == 'parity':
        accepted.test_registry_lookup_bridge_provider_request_parity(db, tmp_path)
    elif case == 'snapshots':
        accepted.test_review_does_not_upgrade_historical_readiness(db, tmp_path)
    else:
        status, score = case.split('_')
        accepted.test_bridge_format_never_proves_regulation_score(db, status, score == 'explicit')


def test_chain_cli_import_export(db: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from app.prematch_football_context.regulation_registry.__main__ import main
    for review in (competition(), base()):
        path = tmp_path / (review.review_id + '.json')
        path.write_bytes(canonical_bytes(review))
        assert main(['validate', str(path)]) == 0
        assert main(['import', '--db', str(db), str(path)]) == 0
        assert main(['import', '--db', str(db), str(path)]) == 0
    capsys.readouterr()
    assert main(['resolve', '--db', str(db), '--provider', 'API_FOOTBALL', '--competition-id', '10',
                 '--season', '2026', '--cutoff', T.isoformat()]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert len(exported['records']) == 2
    assert exported['verdict'] == 'VERIFIED_90'
    assert any(r.get('incorporation', {}).get('relationship') == 'INCORPORATES' for r in exported['records'])


def test_ucl_has_no_imported_real_evidence(db: Path) -> None:
    assert lookup(db, competition_id=2).verdict == Verdict.REGULATION_UNVERIFIED
    append(db, competition(), base())
    assert lookup(db, competition_id=2).verdict == Verdict.REGULATION_UNVERIFIED


@pytest.mark.parametrize('edge', [
    {'competition_review_id': 'SYNTHETIC_WRONG_OWNER'},
    {'relationship': 'ASSUMED'},
    {'base_review_id': 'SYNTHETIC_COMPETITION'},
])
def test_rehashed_invalid_relationship_rejected(edge: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        competition(link_changes=edge)


def test_old_contract_still_requires_explicit_duration() -> None:
    with pytest.raises(ValueError):
        record(regulation_minutes=None)
    with pytest.raises(ValueError):
        base(regulation_minutes=None)


def test_competition_provenance_committed_to_chain(db: Path, tmp_path: Path) -> None:
    append(db, competition(), base())
    original = format_evidence(lookup(db), cutoff=T)
    second = tmp_path / 'changed-competition.db'
    initialize(second)
    append(second, base(), competition(reviewer='SYNTHETIC_SECOND_REVIEWER'))
    assert format_evidence(lookup(second), cutoff=T).proof_hash != original.proof_hash


def test_unlinked_base_does_not_change_legacy_bridge_review_time(db: Path) -> None:
    direct = record()
    append(db, direct, base(reviewed_at=T-timedelta(seconds=1)))
    assert format_evidence(lookup(db), cutoff=T).known_at == direct.reviewed_at
