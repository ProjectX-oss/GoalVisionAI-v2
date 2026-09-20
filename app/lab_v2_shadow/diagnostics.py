"""Persisted global funnel: fixture counts and market decisions remain distinct."""
from __future__ import annotations
from collections import Counter
from datetime import datetime
from .global_evaluation import next_refresh
from .profiles import policy_for

ODDS_REASONS = {
    'FIXTURE_DISCOVERED_NO_CURRENT_ODDS': 'NO_CURRENT_ODDS',
    'FIXTURE_DISCOVERED_ODDS_STALE': 'ODDS_STALE',
    'FIXTURE_DISCOVERED_MARKET_UNSUPPORTED': 'MARKET_NOT_AVAILABLE',
    'FIXTURE_DISCOVERED_ODDS_UNNORMALIZABLE': 'INVALID_MARKET_MAPPING',
    'FIXTURE_DISCOVERED_ODDS_COVERAGE_INCOMPLETE': 'ODDS_COVERAGE_BUDGET_PENDING',
}


def global_diagnostic(fixtures: list[dict], candidates: list[dict], odds_statuses: dict,
                      now: datetime, *, reviews: dict | None = None, odds_reasons: dict | None = None) -> dict:
    """One current state per legitimate fixture; detailed independent market gates."""
    states, gates = [], []
    for fixture in fixtures:
        rows = [c for c in candidates if c['fixture_id'] == fixture['fixture_id']]
        profile = str(fixture.get('competition_profile', 'UNKNOWN'))
        metadata = {k: fixture.get(k) for k in ('fixture_id', 'league_id', 'league_name', 'country',
                    'age_category', 'classifier_version', 'classification_reason', 'classification_fingerprint',
                    'provider_metadata', 'flags')}
        metadata['competition_profile'] = profile
        ready = [c for c in rows if c['stage'] == 'READY_TO_PUBLISH']
        reason = ODDS_REASONS.get(odds_statuses.get(str(fixture['fixture_id'])), 'NEEDS_NEAR_KICKOFF_REFRESH')
        state = 'TRACKING'
        review = (reviews or {}).get(fixture['fixture_id'], {})
        if review.get('status') == 'FIXTURE_INVALID':
            state, reason = 'REJECTED', str(review.get('reason') or 'FIXTURE_STATUS_INVALID')
        elif fixture['kickoff_utc'] <= now or not fixture.get('prematch_eligible', True) or review.get('status') == 'PREMATCH_CLOSED':
            state, reason = 'RESULT_TRACKING', 'PREMATCH_PUBLICATION_CLOSED'
        elif ready:
            state = 'READY' if any(c['candidate_lane'] != 'EXPERIMENTAL' for c in ready) else 'EXPERIMENTAL_READY'
            reason = 'FINAL_REVIEW_COMPLETE'
        elif rows and all(c.get('hard_failures') for c in rows):
            state, reason = 'REJECTED', rows[0]['hard_failures'][0]
        elif not rows and reason in {'NO_CURRENT_ODDS', 'MARKET_NOT_AVAILABLE', 'ODDS_STALE'}:
            state = 'TRACKING'
        coverage_reason = (odds_reasons or {}).get(str(fixture['fixture_id']))
        if not rows and coverage_reason and not review.get('odds_status') and state not in {'REJECTED', 'RESULT_TRACKING'}:
            reason = coverage_reason
        refresh = next_refresh(fixture['kickoff_utc'], now, policy_for(profile))
        states.append({**metadata, 'state': state, 'reason': reason,
                       'kickoff_utc': fixture['kickoff_utc'].isoformat(),
                       'next_refresh_at': refresh.isoformat() if refresh else None,
                       'evaluated_at_utc': now.isoformat(), 'markets_evaluated': len(rows)})
        gate_metadata = {key: value for key, value in metadata.items() if key != 'provider_metadata'}
        if not rows:
            gates.append({**gate_metadata, 'stage': 'CURRENT_ODDS', 'market': None, 'reason_code': reason,
                          'gate_type': 'DEFERRED', 'passed': False, 'retryable': refresh is not None,
                          'missing_data': ['current_market_quotes']})
        for c in rows:
            for stage, reasons, gate_type in (
                ('INTEGRITY_VALUE', c.get('hard_failures', []), 'HARD'),
                ('PROFILE_QUALITY', c.get('soft_findings', []), 'SOFT'),
                ('OPTIONAL_DATA', c.get('optional_data_reasons', []), 'SOFT'),
                ('FINAL_REVIEW', c.get('readiness_reasons', []), 'DEFERRED'),
            ):
                for reason_code in reasons or ['PASSED']:
                    passed = reason_code in {'PASSED', 'FINAL_REVIEW_COMPLETE'} or (gate_type == 'SOFT' and c['decision'] == 'APPROVED')
                    gates.append({**gate_metadata, 'stage': stage, 'market': c['market'],
                                  'candidate_lane': c['candidate_lane'], 'reason_code': reason_code,
                                  'gate_type': gate_type, 'passed': passed,
                                  'retryable': not passed and refresh is not None,
                                  'missing_data': c.get('missing_features', [])})
    funnel = []
    for stage in sorted({g['stage'] for g in gates}):
        rows = [g for g in gates if g['stage'] == stage]
        entering = {g['fixture_id'] for g in rows}
        failing = {g['fixture_id'] for g in rows if not g['passed']}
        funnel.append({'stage': stage, 'fixtures_entering': len(entering),
                       'fixtures_with_any_failure': len(failing),
                       'fixtures_leaving_without_failure': len(entering - failing),
                       'rejected_or_deferred_decisions': sum(not g['passed'] for g in rows)})
    lanes = Counter(c['candidate_lane'] for c in candidates)
    reasons = Counter(g['reason_code'] for g in gates if not g['passed'])
    odds_count = sum(s == 'FIXTURE_DISCOVERED_WITH_CURRENT_ODDS' for s in odds_statuses.values())
    counts = {'fixtures_discovered': len(fixtures), 'fixtures_with_current_odds': odds_count,
              'fixtures_scored': len({c['fixture_id'] for c in candidates}),
              'fixtures_with_independent_probability': len({c['fixture_id'] for c in candidates if c.get('independent_probability_available')}),
              'fixtures_tracking': sum(s['state'] in {'TRACKING', 'UNAVAILABLE'} for s in states),
              'strong_candidates': lanes['STRONG'], 'standard_candidates': lanes['STANDARD'],
              'experimental_candidates': lanes['EXPERIMENTAL'], 'rejected_candidates': lanes['REJECTED'],
              'published_candidates': 0}
    grouped = {}
    for dimension, fixture_key, candidate_key in (
        ('competition_profile', 'competition_profile', 'competition_profile'),
        ('league', 'league_id', 'league_id'), ('country', 'country', 'country'),
    ):
        groups = {}
        for value in sorted({str(f.get(fixture_key, 'UNKNOWN')) for f in fixtures}):
            ids = {f['fixture_id'] for f in fixtures if str(f.get(fixture_key, 'UNKNOWN')) == value}
            selected = [c for c in candidates if str(c.get(candidate_key, 'UNKNOWN')) == value]
            groups[value] = {'fixtures_discovered': len(ids),
                             'fixtures_with_current_odds': sum(odds_statuses.get(str(i)) == 'FIXTURE_DISCOVERED_WITH_CURRENT_ODDS' for i in ids),
                             'fixtures_scored': len({c['fixture_id'] for c in selected}),
                             'lanes': dict(Counter(c['candidate_lane'] for c in selected)),
                             'rejection_reasons': dict(Counter(g['reason_code'] for g in gates if g['fixture_id'] in ids and not g['passed']))}
        grouped[dimension] = groups
    grouped['market'] = {market: {'evaluated': sum(c['market'] == market for c in candidates),
                                 'lanes': dict(Counter(c['candidate_lane'] for c in candidates if c['market'] == market))}
                         for market in sorted({c['market'] for c in candidates})}
    rejection_percentages = {
        reason: {'decisions': count, 'percent_of_failed_gate_observations': round(count * 100 / sum(reasons.values()), 3)}
        for reason, count in reasons.most_common()
    }
    fixture_reasons = Counter(s['reason'] for s in states)
    return {'rejection_reason_percentages': rejection_percentages,
            'fixture_reason_counts': {reason: {'fixtures': count, 'percent_of_discovered': round(count * 100 / len(states), 3)}
                                     for reason, count in sorted(fixture_reasons.items())},
            'grouped_throughput' : grouped, 'global_fixture_states': states, 'rejection_funnel': funnel, 'gate_evidence': gates,
            'throughput': counts, 'competition_profile_counts': dict(Counter(s['competition_profile'] for s in states)),
            'global_state_counts': dict(Counter(s['state'] for s in states)),
            'top_global_rejection_reasons': dict(reasons.most_common(15)),
            'largest_rejection_bottleneck': reasons.most_common(1),
            'candidate_counts_by_profile': dict(Counter(c.get('competition_profile', 'UNKNOWN') for c in candidates if c['decision'] == 'APPROVED')),
            'top_candidate_competitions': dict(Counter(c['league'] for c in candidates if c['decision'] == 'APPROVED')),
            'top_candidate_markets': dict(Counter(c['market'] for c in candidates if c['decision'] == 'APPROVED')),
            'fixtures_awaiting_near_kickoff_review': sum(s['state'] in {'TRACKING', 'UNAVAILABLE'} and s['next_refresh_at'] is not None for s in states),
            'throughput_warnings': ['ZERO_READY_WITH_HIGH_FIXTURE_VOLUME'] if len(fixtures) >= 200 and odds_count >= 50 and not any(s['state'] in {'READY', 'EXPERIMENTAL_READY'} for s in states) else []}


def human_diagnostic(report: dict) -> str:
    """Render only persisted counts, never estimated fixture or selection totals."""
    lines = [str(report.get('discovery_state') or 'GLOBAL DISCOVERY')]
    for key in ('priority_fixtures_discovered', 'priority_fixtures_analyzed', 'total_analyzed',
                'waiting_odds_refresh', 'soft_confidence_penalties', 'actual_hard_rejects',
                'positive_ev_shadow_observations', 'ready', 'telegram_sends'):
        lines.append(f'{key}: {report.get(key, 0)}')
    lines.extend(f'{key}: {value}' for key, value in (report.get('throughput') or {}).items())
    lines.append('By profile:')
    lines.extend(f'  {key}: {value}' for key, value in (report.get('competition_profile_counts') or {}).items())
    lines.append('Odds coverage reasons:')
    lines.extend(f'  {key}: {value}' for key, value in report.get('odds_coverage_reason_counts', {}).items())
    lines.append('Top rejection/deferral reasons:')
    lines.extend(f'  {key}: {value}' for key, value in (report.get('top_global_rejection_reasons') or {}).items())
    for key in ('api_calls_used', 'current_remaining_daily_quota', 'fixtures_awaiting_near_kickoff_review', 'throughput_warnings'):
        lines.append(f'{key}: {report.get(key)}')
    return '\n'.join(lines)
