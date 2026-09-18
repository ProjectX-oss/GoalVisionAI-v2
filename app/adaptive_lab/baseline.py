"""Reviewed PREMATCH baseline adapter; no fitted parameters or executable artifacts."""
from __future__ import annotations
from dataclasses import asdict
from decimal import Decimal
from .contracts import digest

IDENTITY = 'EXISTING_PREMATCH_BASELINE_V1'
ACCEPTED_COMMIT = '0c4f316248e55f504b780cdef4e25165b800a779'


def artifact() -> dict:
    """Identify the accepted deterministic signal/profile inference contract."""
    from app.lab_v2_shadow.ensemble import POLICY_VERSION
    from app.lab_v2_shadow.profiles import POLICY_VERSION as profile_version
    value={'family':IDENTITY,'stream':'PREMATCH','accepted_commit':ACCEPTED_COMMIT,
           'ensemble_policy':POLICY_VERSION,'profile_policy':profile_version,
           'probability_contract':'FINITE_OPEN_UNIT_INTERVAL',
           'rollback_identity':IDENTITY,'registry_version':'LAB_MODEL_REGISTRY_V1'}
    return {**value,'artifact_fingerprint':digest(value)}


def validate(value: dict) -> None:
    if value != artifact():
        raise ValueError('BASELINE_ARTIFACT_INCOMPATIBLE')


def context(signals: list, profile: str, missing: list | tuple, market: str,
            odds: Decimal, *, contradiction: bool = False) -> dict:
    """Freeze actual pre-profile signals, not already weighted display signals."""
    return {'signals':[{k:str(v) if isinstance(v,Decimal) else v for k,v in asdict(s).items()}
                       for s in signals], 'profile':profile,'missing':list(missing),
            'market':market,'odds':str(odds),'contradiction':contradiction}


def infer(frozen: dict) -> Decimal:
    """Invoke accepted inference on exact frozen inputs; never recompute old labels."""
    from app.lab_v2_shadow.ensemble import EnsembleSignal
    from app.lab_v2_shadow.global_evaluation import evaluate_profile
    from app.lab_v2_shadow.profiles import policy_for
    signals=[EnsembleSignal(**{**s,'reliability':Decimal(s['reliability']),
                               'probability':Decimal(s['probability']) if s['probability'] is not None else None})
             for s in frozen['signals']]
    decision,_=evaluate_profile(frozen['market'],Decimal(frozen['odds']),signals,
                                policy_for(frozen['profile']),tuple(frozen['missing']),
                                contradiction=frozen['contradiction'])
    p=decision.ensemble_probability
    if p is None or not p.is_finite() or not 0<p<1:
        raise ValueError('BASELINE_PROBABILITY_CONTRACT')
    return p


def predict(value: dict, row: dict) -> float:
    validate(value)
    if row['stream']!='PREMATCH':
        raise ValueError('MODEL_STREAM_MISMATCH')
    frozen=row.get('frozen_features',{}).get('baseline_context')
    if frozen is None:
        raise ValueError('BASELINE_FROZEN_CONTEXT_REQUIRED')
    if frozen['market']!=row['market']:
        raise ValueError('BASELINE_MARKET_MISMATCH')
    return float(infer(frozen))
