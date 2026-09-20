"""Priority analysis first, persistent fair ordering within each priority class."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from .repository import ShadowEvidenceRepository
from .profiles import policy_for, is_priority, resource_priority


def fair_order(fixtures: list[dict], repository: ShadowEvidenceRepository, *, phase: str) -> list[dict]:
    """Priority class first, then least-served category and round robin.

    Counts survive restart. Categories share the remaining ordinary budget.
    Near kickoff affects order within a category, never category inclusion.
    """
    served: dict[str, int] = defaultdict(int)
    last: dict[int, str] = {}
    for row in repository.all('enrichment_service'):
        if row['phase'] == phase:
            served[row['competition_profile']] += 1
            last[row['fixture_id']] = row['at']
    queues: dict[str, list[dict]] = defaultdict(list)
    for item in sorted(fixtures, key=lambda x: (last.get(x['fixture_id'], ''), x['kickoff_utc'], x['fixture_id'])):
        queues[str(item.get('competition_profile', 'UNKNOWN'))].append(item)
    result = []
    while queues:
        profile = min(queues, key=lambda p: (served[p] / policy_for(p).scheduling_weight, p))
        result.append(queues[profile].pop(0))
        served[profile] += 1
        if not queues[profile]:
            del queues[profile]
    return sorted(result, key=resource_priority)


def record_service(repository: ShadowEvidenceRepository, fixture: dict, now: datetime, phase: str) -> None:
    """Persist only work actually serviced; unvisited queues keep their turn."""
    row = {'fixture_id': fixture['fixture_id'], 'competition_profile': str(fixture.get('competition_profile', 'UNKNOWN')),
           'phase': phase, 'at': now.isoformat()}
    repository.append('enrichment_service', f"{phase}:{fixture['fixture_id']}:{now.isoformat()}", row, created_at=now)
