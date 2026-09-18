"""Central reviewed policy: models cannot mutate the safety shell or thresholds."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime
from .contracts import digest, stream_name, utc


@dataclass(frozen=True)
class LearningPolicy:
    version: str = 'LAB_ADAPTIVE_V2'
    observe_min: int = 100
    research_min: int = 200
    automatic_min: int = 500
    automatic_days: int = 90
    specialized_min: int = 200
    specialized_days: int = 60
    calibration_min: int = 300
    new_resolved_min: int = 50
    cycle_days: int = 7
    candidate_limit: int = 50
    training_rows_limit: int = 20000
    operation_budget: int = 250_000_000
    iterations: int = 150
    embargo_hours: int = 24
    holdout_min: int = 100
    shadow_min: int = 100
    shadow_days: int = 30
    performance_rollback_min: int = 200
    performance_rollback_days: int = 30
    brier_tolerance: float = 0.01
    logloss_tolerance: float = 0.025
    ece_tolerance: float = 0.03
    selection_ratio_min: float = 0.5
    selection_ratio_max: float = 2.0
    subgroup_min: int = 30
    subgroup_brier_tolerance: float = 0.06
    bootstrap_replicates: int = 200
    seed: int = 1729

    @property
    def fingerprint(self) -> str:
        return digest(asdict(self))


POLICY = LearningPolicy()


def eligibility(rows: list[dict], stream: str, now: datetime, *, previous: dict | None = None) -> dict:
    """Only this stream's real resolved binary observations count; voids do not."""
    stream_name(stream)
    resolved = [r for r in rows if r['stream'] == stream and r['outcome'] in {'WON', 'LOST'}
                and utc(r['settled_at']) <= utc(now)]
    dates = [utc(r['prediction_created_at']) for r in resolved]
    days = (max(dates) - min(dates)).days if dates else 0
    n = len(resolved)
    status = ('INSUFFICIENT_SAMPLE' if n < POLICY.observe_min else
              'OBSERVE_ONLY' if n < POLICY.research_min else
              'RESEARCH_ELIGIBLE' if n < POLICY.automatic_min or days < POLICY.automatic_days else
              'AUTO_LEARNING_ELIGIBLE')
    new = [r for r in resolved if previous is None or utc(r['settled_at']) > utc(previous['created_at'])]
    due = previous is None or (utc(now) - utc(previous['created_at'])).days >= POLICY.cycle_days
    reason = status
    if n >= POLICY.observe_min and (len(new) < POLICY.new_resolved_min or not due):
        reason = 'NOT_ENOUGH_NEW_DATA' if len(new) < POLICY.new_resolved_min else 'CYCLE_COOLDOWN'
    stage=('LEARNING_AND_OBSERVING' if n<POLICY.observe_min else 'EARLY_RESEARCH' if n<POLICY.research_min else
           'CHALLENGER_RESEARCH' if not (n>=POLICY.automatic_min and days>=POLICY.automatic_days) else 'FULL_AUTO_LEARNING_ELIGIBLE')
    return {'next_threshold':{'resolved':POLICY.observe_min if n<POLICY.observe_min else POLICY.research_min if n<POLICY.research_min else POLICY.automatic_min, 'calendar_days':POLICY.automatic_days},
            'stage':stage,'stream': stream, 'resolved': n, 'days_covered': days, 'status': status,
            'reason': reason, 'new_resolved': len(new), 'cycle_due': due,
            'research_due': n >= POLICY.observe_min and len(new) >= POLICY.new_resolved_min and due,
            'automatic_eligible': status == 'AUTO_LEARNING_ELIGIBLE', 'policy_version': POLICY.version,
            'policy_fingerprint': POLICY.fingerprint}
