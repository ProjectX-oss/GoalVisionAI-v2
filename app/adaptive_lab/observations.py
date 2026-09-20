"""Deterministic settlement-to-frozen-evidence linkage, never prediction replay."""
from __future__ import annotations
from pathlib import Path
import json
import sqlite3
from typing import Protocol
from .contracts import MARKETS, digest, number, side, stream_name, utc
from .repository import AuditRepository
from .features import captured_features


class EvidenceReader(Protocol):
    def get(self, kind: str, identity: str) -> dict | None: ...
    def all(self, kind: str) -> list[dict]: ...


class ReadOnlyLedger:
    """A consistent SQLite read transaction; never instantiates a migrating writer."""
    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        self.connection.execute('PRAGMA query_only=ON')
        self.connection.execute('BEGIN')

    def get(self, kind: str, identity: str) -> dict | None:
        row = self.connection.execute('SELECT document,fingerprint FROM evidence WHERE kind=? AND identity=?',
                                      (kind, identity)).fetchone()
        if not row:
            return None
        value = json.loads(row[0])
        if digest(value) != row[1]:
            raise ValueError('SOURCE_INTEGRITY_FAILURE')
        return value

    def all(self, kind: str) -> list[dict]:
        return [self.get(kind, row[0]) for row in self.connection.execute(
            'SELECT identity FROM evidence WHERE kind=? ORDER BY identity', (kind,))]

    def close(self) -> None:
        self.connection.close()


def freeze_observation(prediction: dict, receipt: dict, settlement: dict, *, stream: str,
                       publication_id: str, source_product: str = 'SINGLE') -> dict:
    """Copy captured values verbatim; derive arithmetic metrics, never old model output."""
    stream_name(stream)
    required = ('fixture_id', 'kickoff_utc', 'market', 'captured_odds', 'ensemble_probability',
                'quote_provenance_fingerprint', 'provider_origin_timestamp_utc',
                'goalvision_retrieved_at_utc', 'prepared_at_utc')
    shadow = source_product == 'SHADOW'
    if any(prediction.get(k) is None for k in required) or (not shadow and (not receipt or receipt.get('status') != 'SENT')):
        raise ValueError('MISSING_FROZEN_EVIDENCE')
    p = number(prediction['ensemble_probability'], low=0, high=1)
    odds = number(prediction['captured_odds'], low=1, high=10000)
    if not 0 < p < 1 or odds <= 1 or prediction['market'] not in MARKETS:
        raise ValueError('MISSING_FROZEN_EVIDENCE')
    created, kickoff = utc(prediction['prepared_at_utc']), utc(prediction['kickoff_utc'])
    published = created if shadow else utc(receipt['sent_at_utc']) if receipt.get('sent_at_utc') else None
    settled = utc(settlement.get('settled_at_utc') or settlement['retrieved_at_utc'])
    if published is None:
        raise ValueError('MISSING_FROZEN_EVIDENCE')
    if not utc(prediction['provider_origin_timestamp_utc']) <= utc(prediction['goalvision_retrieved_at_utc']) <= created <= published < settled:
        raise ValueError('MISSING_FROZEN_EVIDENCE')
    if stream == 'PREMATCH' and not published < kickoff < settled:
        raise ValueError('POST_KICKOFF_LEAKAGE')
    if str(settlement.get('fixture_id')) != str(prediction['fixture_id']) or settlement.get('market') != prediction['market']:
        raise ValueError('AMBIGUOUS_SELECTION_IDENTITY')
    outcome = settlement.get('status', settlement.get('outcome'))
    if outcome not in {'WON', 'LOST', 'VOID'}:
        raise ValueError('CONFLICTING_SETTLEMENT')
    if number(settlement.get('captured_odds'), low=1) != odds:
        raise ValueError('CONFLICTING_SETTLEMENT')
    home, away = settlement.get('fulltime_home'), settlement.get('fulltime_away')
    if outcome != 'VOID':
        from app.current_odds_forward_test.service import _won
        if not all(type(v) is int and 0 <= v <= 30 for v in (home, away)):
            raise ValueError('MISSING_FROZEN_EVIDENCE')
        if (_won(prediction['market'], home, away)) != (outcome == 'WON'):
            raise ValueError('CONFLICTING_SETTLEMENT')
    families = prediction.get('predictive_families', [])
    opportunity = digest([stream, prediction['fixture_id'], prediction['market'],
                          prediction.get('candidate_id', prediction.get('observation_id')),
                          prediction['quote_provenance_fingerprint'], prediction['ensemble_probability']])
    fields = {
        'model_generation': prediction.get('model_generation'),
        'model_artifact_identity': prediction.get('model_artifact_identity'),
        'classifier_version': prediction.get('classifier_version'),
        'policy_version': prediction.get('profile_policy_version', prediction.get('policy')),
        'league_id': prediction.get('league_id'),
        'competition_profile': prediction.get('competition_profile'),
        'uncertainty': prediction.get('uncertainty_penalty'),
    }
    value = dict(fields, stream=stream, observation_id='obs-' + opportunity, opportunity_key=opportunity,
        selection_id=prediction.get('candidate_id', prediction.get('observation_id', prediction.get('prediction_id'))),
        publication_id=publication_id, settlement_identity=digest(settlement), source_product=source_product,
        fixture_id=prediction['fixture_id'], kickoff_utc=prediction['kickoff_utc'], market=prediction['market'],
        side=side(prediction['market']), lane=prediction.get('candidate_lane'),
        offered_decimal_odds=prediction['captured_odds'], implied_probability=1 / odds,
        frozen_model_probability=prediction['ensemble_probability'], fair_odds=1 / p, edge=p - 1 / odds,
        EV=p * odds - 1, evidence_family_count=len(families), evidence_family_types=families,
        primary_predictive_family=families[0] if families else None,
        quote_fingerprint=prediction['quote_provenance_fingerprint'],
        quote_origin_timestamp=prediction['provider_origin_timestamp_utc'],
        quote_retrieved_timestamp=prediction['goalvision_retrieved_at_utc'],
        bookmaker=prediction.get('bookmaker'), bookmaker_id=prediction.get('bookmaker_id'),
        prediction_created_at=created.isoformat(), published_at=None if shadow else published.isoformat(), settled_at=settled.isoformat(),
        final_score=[home, away], outcome=outcome, target=None if outcome == 'VOID' else int(outcome == 'WON'),
        flat_unit_pnl=odds - 1 if outcome == 'WON' else -1 if outcome == 'LOST' else 0,
        missing_provenance=sorted(k for k, v in fields.items() if v is None),
        frozen_features=captured_features(prediction),
        frozen_flags={k: prediction.get(k) for k in ('missing_features', 'lineup_confirmed', 'calibration_status',
                                                     'market_consensus_relation', 'final_review_completed_at_utc')})
    if stream == 'LIVE':
        for key in ('live_minute', 'live_score_home', 'live_score_away', 'live_match_state_fingerprint'):
            if key not in prediction:
                raise ValueError('MISSING_FROZEN_EVIDENCE')
            value[key] = prediction[key]
        value['red_card_state'] = prediction.get('red_card_state')
        value['prematch_favorite_state'] = prediction.get('prematch_favorite_state')
    value['observation_fingerprint'] = digest(value)
    return value


def ingest(repository: AuditRepository, prediction: dict, receipt: dict, settlement: dict, *,
           stream: str, publication_id: str, source_product: str = 'SINGLE') -> dict:
    """Atomic evidence reference plus observation; idempotent across combo/single copies."""
    with repository.transaction():
        value = freeze_observation(prediction, receipt, settlement, stream=stream,
                                   publication_id=publication_id, source_product=source_product)
        # Canonical shadow and published copies of a fixture/market are one sample.
        for old in repository.all('learning_observations', stream):
            if (old['fixture_id'], old['market']) == (value['fixture_id'], value['market']) and (
                    old.get('source_product') == 'SHADOW' or source_product == 'SHADOW'):
                if old['outcome'] != value['outcome'] or old['final_score'] != value['final_score']:
                    raise ValueError('CONFLICTING_SETTLEMENT')
                return old
        existing = repository.get('learning_observations', value['observation_id'])
        if existing:
            keys = ('outcome', 'final_score', 'frozen_model_probability', 'offered_decimal_odds', 'fixture_id', 'market')
            if any(existing[k] != value[k] for k in keys):
                raise ValueError('CONFLICTING_SETTLEMENT')
            if existing['publication_id'] == publication_id and existing != value:
                raise ValueError('CONFLICTING_SETTLEMENT')
            return existing
        source = {'prediction': prediction, 'publication': receipt, 'settlement': settlement,
                  'publication_id': publication_id, 'source_product': source_product}
        source_id = 'source-' + digest(source)
        with repository.transaction():
            repository.append('source_records', source_id, stream, source, value['settled_at'])
            repository.append('learning_observations', value['observation_id'], stream, value,
                              value['settled_at'], source_id=source_id)
        return value


def import_prematch(ledger: EvidenceReader, repository: AuditRepository, *, now: str) -> dict:
    """Read authoritative ledger; explicit diagnostics include every unlinked settlement."""
    counts = {'linked_singles': 0, 'linked_combo_legs': 0, 'diagnostics': [], 'combo_records': 0}
    for result in ledger.all('single_settlement'):
        pid = result['prediction_id']
        pred = ledger.get('single_prediction', pid)
        receipt = ledger.get('receipt', 'single_prediction:' + pid)
        try:
            if pred is None or receipt is None:
                raise ValueError('UNLINKED_SETTLEMENT')
            ingest(repository, pred, receipt, result, stream='PREMATCH', publication_id=pid)
            counts['linked_singles'] += 1
        except (ValueError, KeyError, TypeError) as exc:
            _diagnostic(repository, counts, pid, str(exc), now)
    for combo in ledger.all('prediction'):
        pid = combo['prediction_id']
        result = ledger.get('settlement', pid)
        receipt = ledger.get('receipt', 'combo_prediction:' + pid) or ledger.get('receipt', 'prediction:' + pid)
        if not result:
            continue
        if not receipt:
            _diagnostic(repository, counts, pid, 'UNLINKED_SETTLEMENT', now)
            continue
        from .metrics import combo_record
        record = combo_record(combo, result)
        repository.append('combo_analytics', pid, 'COMBO', record, result['settled_at_utc'])
        counts['combo_records'] += 1
        for leg in combo['legs']:
            identity = leg['observation_id']
            resolved = ledger.get('leg_result', identity)
            try:
                if not resolved:
                    raise ValueError('UNLINKED_SETTLEMENT')
                before = len(repository.all('learning_observations', 'PREMATCH'))
                ingest(repository, leg, receipt, resolved, stream='PREMATCH', publication_id=pid,
                       source_product='COMBO_LEG')
                counts['linked_combo_legs'] += len(repository.all('learning_observations', 'PREMATCH')) - before
            except (ValueError, KeyError, TypeError) as exc:
                _diagnostic(repository, counts, identity, str(exc), now)
    return counts


def _diagnostic(repository: AuditRepository, counts: dict, identity: str, reason: str, now: str) -> None:
    allowed = {'UNLINKED_SETTLEMENT', 'AMBIGUOUS_SELECTION_IDENTITY', 'MISSING_FROZEN_EVIDENCE',
               'CONFLICTING_SETTLEMENT', 'POST_KICKOFF_LEAKAGE'}
    value = {'identity': identity, 'status': reason if reason in allowed else 'MISSING_FROZEN_EVIDENCE'}
    repository.append('linkage_diagnostics', digest(value), 'PREMATCH', value, now)
    counts['diagnostics'].append(value)
