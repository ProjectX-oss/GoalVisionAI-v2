"""Separate mandatory probability evidence from optional provider context."""
from __future__ import annotations

from .capability import LeagueCapability


def signal_requirements(missing: tuple[str, ...], capability: LeagueCapability,
                        *, independent_probability: bool) -> list[dict]:
    """Optional signal absence changes uncertainty, never the probability contract."""
    supported = {'lineup': capability.lineups, 'injuries': capability.injuries,
                 'advanced_stats': capability.fixture_statistics, 'standings': capability.standings}
    rows = [{'signal': 'independent_non_market_probability', 'gate_type': 'HARD',
             'present': independent_probability,
             'reason_code': 'PASSED' if independent_probability else 'MANDATORY_SIGNAL_MISSING'}]
    for feature in missing:
        code = ('PROVIDER_DOES_NOT_SUPPORT_SIGNAL' if supported.get(feature) is False else
                'SIGNAL_NOT_YET_AVAILABLE' if feature == 'lineup' else 'OPTIONAL_SIGNAL_MISSING')
        rows.append({'signal': feature, 'gate_type': 'SOFT', 'present': False, 'reason_code': code})
    return rows
