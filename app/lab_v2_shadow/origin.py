"""Frozen selection attribution; Football Context V2 is observation, not inference."""
from __future__ import annotations

from datetime import datetime

ORIGIN_VERSION = 'LAB_SELECTION_ORIGIN_V1'
SELECTOR = 'EXISTING_LAB_V2_SELECTOR'
LABEL = '🧪 GoalVision AI Lab · V2 atlase'


def freeze_origin(candidate: dict, *, now: datetime, observer: object | None = None) -> dict:
    """Retain only the actual selector and an exact, already frozen context link."""
    context = None
    if observer is not None:
        try:
            snapshot = observer.snapshots.load(f"{candidate['fixture_id']}:{candidate['market']}")
            if (snapshot is not None and snapshot.opportunity.candidate_id == candidate['candidate_id']
                    and snapshot.receipt.cutoff <= now
                    and snapshot.home_team_id == candidate['home_team_id']
                    and snapshot.away_team_id == candidate['away_team_id']):
                from app.prematch_football_context.snapshot.service import reproduce
                if reproduce(observer.evidence, snapshot) != snapshot:
                    raise ValueError('CONTEXT_REPRODUCTION_FAILED')
                _verify_proof(observer.ledger, snapshot)
                context = {'snapshot_id': snapshot.snapshot_id,
                           'snapshot_hash': snapshot.snapshot_hash,
                           'receipt_hash': snapshot.receipt.receipt_hash,
                           'cutoff': snapshot.receipt.cutoff.isoformat(),
                           'available_features': 7 - sum(snapshot.projection.missing),
                           'total_features': 7, 'use': 'OBSERVATION_ONLY'}
        except Exception:
            # Missing optional proof cannot suppress an existing valid selector.
            context = None
    return {'version': ORIGIN_VERSION, 'origins': [SELECTOR],
            'selector_policy': candidate['policy'],
            'profile_policy': candidate.get('profile_policy_version'),
            'model_generation': candidate.get('model_generation'),
            'model_artifact': candidate.get('model_artifact_identity'),
            'probability_kind': candidate.get('probability_kind'),
            'predictive_families': candidate.get('predictive_families', []),
            'independent_context_model': None, 'context': context,
            'frozen_at_utc': now.isoformat()}


def _verify_proof(ledger: object, snapshot: object) -> None:
    """Verify the exact pre-decision proof chain offline, without the live registry."""
    from app.prematch_football_context.readiness.regulations import formats, registry_format, verify_retained
    if not any(registry_format(fmt) for _, fmt in formats(snapshot)):
        return
    events = []

    def read(kind: str, key: str) -> dict:
        value = ledger.get(kind, key)
        events.append((kind, key, value))
        return value

    link = read('REGULATION_LINK', snapshot.snapshot_id)
    acquisition = read('REGISTRY_ACQUISITION', link['acquisition_id'])
    read('REGISTRY_VIEW', acquisition['view_id'])
    read('REGISTRY_DECISION', snapshot.receipt.receipt_hash)
    for key in link['proofs'].values():
        read('REGULATION_PROOF', key)
    verify_retained(snapshot, events, acquisition['run_id'])


def is_labelled(value: dict) -> bool:
    """New metadata only; never infer new attribution from a historical ID."""
    origin = value.get('selection_origin') or {}
    return origin.get('version') == ORIGIN_VERSION and SELECTOR in origin.get('origins', [])


def result_message(value: dict, receipt: dict) -> str:
    """Label the outcome and link the original confirmed Telegram message."""
    from app.lab_combo.presentation import market_label, public_decimal, score, team_pair
    return '\n'.join((LABEL, value['status'], f"⚽ {team_pair(value)}",
        f"🎯 {market_label(value['market'])} · {public_decimal(value['captured_odds'])}",
        f"Rezultāts: {score(value)}", f"Atsauce: {value['prediction_id']}",
        f"https://t.me/c/3510920417/{receipt['message_id']}",
        f"Hipotētisks 1u rezultāts: {value['unit_result']}u; nav reālas naudas uzskaite."))
