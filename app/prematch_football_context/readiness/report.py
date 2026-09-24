"""Deterministic read-only input coverage; no outcomes, model or provider imports."""
from collections import Counter
from contextlib import ExitStack
from decimal import Decimal, localcontext
from pathlib import Path

from ..capture.repository import EvidenceRepository
from ..policy import FEATURE_NAMES, decimal_context
from ..snapshot.repository import SnapshotRepository
from ..snapshot.service import reproduce
from ..snapshot.contracts import Projection
from .ledger import Ledger


def rate(numerator: int, denominator: int, name: str) -> dict[str, object]:
    """Every rate carries the exact denominator; an empty denominator is N/A."""
    with localcontext(decimal_context()):
        value = format(Decimal(numerator) / Decimal(denominator), '.6f') if denominator else 'N/A'
    return {'numerator': numerator, 'denominator': denominator, 'denominator_name': name, 'fraction': value}


def readiness(*, attempts: int, snapshots: int, competitions: int, days: int,
              failures: int, incomplete: int) -> str:
    """Input review only, never promotion or permission to implement Phase E."""
    if failures or incomplete:
        return 'CAPTURE_BLOCKED'
    if not attempts:
        return 'NO_PROSPECTIVE_EVIDENCE'
    if not snapshots:
        return 'CAPTURE_BLOCKED'
    if snapshots < 100:
        return 'INSUFFICIENT_SAMPLE'
    if competitions < 5 or days < 7:
        return 'PARTIAL_COVERAGE'
    return 'READY_FOR_V2_RESEARCH_REVIEW'


def feature_coverage(projections: tuple[Projection, ...]) -> tuple[dict[str, int], dict[str, dict]]:
    """Aggregate exact masks/reasons; feature availability uses snapshots only."""
    histogram = {str(i): 0 for i in range(8)}
    features = {name: {'available': 0, 'missing': 0, 'missing_reasons': Counter()} for name in FEATURE_NAMES}
    for projection in projections:
        histogram[str(7-sum(projection.missing))] += 1
        for name, missing, reasons in zip(FEATURE_NAMES, projection.missing, projection.reasons):
            features[name]['missing' if missing else 'available'] += 1
            features[name]['missing_reasons'].update(reasons)
    for counts in features.values():
        counts['availability_rate'] = rate(counts['available'], len(projections), 'successful_immutable_snapshots')
        counts['missing_reasons'] = dict(sorted(counts['missing_reasons'].items()))
    return histogram, features


def run_state(run: dict, end: dict | None, *, linked_events: bool) -> tuple[str, str]:
    """Classify only positive immutable completion/zero-activity proof.

    V1 always counted every response callback and every attempted observation in
    END diagnostics, including persistence failures. Its *exactly empty* durable
    END, together with no linked events, proves zero observations. Missing END,
    omitted diagnostics, unknown versions and mere absence of rows prove nothing.
    V2 additionally requires the typed credential failure and explicit zero hook
    counts. No exception text or credentials are retained.
    """
    if end is not None and end.get('completed') is True:
        return 'COMPLETED_OBSERVATION', 'COMPLETED_END'
    if end is not None and end.get('completed') is False and not linked_events and end.get('diagnostics') == {}:
        if run.get('version') == 'FC_READINESS_1':
            return 'PREFLIGHT_FAILURE', 'LEGACY_ZERO_OBSERVATION_END'
        activity = end.get('activity')
        expected = {'responses', 'preparations', 'decisions', 'opportunities', 'attempts'}
        if (run.get('version') == 'FC_READINESS_2' and end.get('credential_failure') is True
                and type(activity) is dict and set(activity) == expected
                and all(type(v) is int and v == 0 for v in activity.values())):
            return 'PREFLIGHT_FAILURE', 'CREDENTIAL_FAILURE_ZERO_ACTIVITY'
    return 'INCOMPLETE_EVIDENCE_WINDOW', 'ZERO_ACTIVITY_NOT_PROVEN'


def coverage(root: Path) -> dict[str, object]:
    """Open all three stores read-only, verify every row, report corruption explicitly.

    Reports describe persisted observation only. An incomplete RUN blocks unless
    its immutable END proves a preflight failure with zero observations. A total
    storage failure can only be diagnosed by bounded stderr diagnostics.
    """
    try:
        with ExitStack() as stack:
            e = EvidenceRepository(root/'sources.db')
            stack.callback(e.close)
            s = SnapshotRepository(root/'snapshots.db')
            stack.callback(s.close)
            ledger = Ledger(root/'attempts.db')
            stack.callback(ledger.close)
            return analyze(e, s, ledger)
    except Exception:
        return {'version': 'FC_READINESS_2', 'readiness': 'CAPTURE_BLOCKED',
                'integrity_failures': {'STORE_OR_REPORT_UNAVAILABLE': 1},
                'denominator_completeness': 'UNPROVEN', 'phase_e_authorized': False}


def analyze(e: EvidenceRepository, s: SnapshotRepository, ledger: Ledger) -> dict[str, object]:
    """Inspect immutable snapshots and bounded attempt events without any writes."""
    events, bad = ledger.read()
    integrity = Counter({'CORRUPT_LEDGER_EVENT': bad}) if bad else Counter()
    runs = {key: doc for kind, key, doc in events if kind == 'RUN'}
    ends = {key: doc for kind, key, doc in events if kind == 'END'}
    opportunities = {key: doc for kind, key, doc in events if kind == 'OPPORTUNITY'}
    results = {key: doc for kind, key, doc in events if kind == 'RESULT'}
    attempts = {key: doc for key, doc in opportunities.items() if doc['attempted'] is True}
    incomplete = sum(key not in ends or ends[key].get('completed') is not True for key in runs)
    # V1 did not count successful begin() calls. An unassociated decision marker
    # could belong to its failed run, so legacy zero-counter proof is insufficient
    # in that case. V2 has an explicit decision-boundary activity count.
    unlinked_receipts = {r[0] for r in e.connection.execute(
        "SELECT receipt_hash FROM fc_receipts WHERE event='DECISION'")} - {
            doc.get('receipt') for doc in opportunities.values()}
    run_details = []
    for key, run in sorted(runs.items()):
        linked = any(doc.get('run_id') == key for doc in (*opportunities.values(), *results.values()))
        state, proof = run_state(run, ends.get(key), linked_events=(
            linked or (run.get('version') == 'FC_READINESS_1' and bool(unlinked_receipts))))
        run_details.append({'run_id': key, 'state': state, 'proof': proof})
    states = Counter(row['state'] for row in run_details)
    window_incomplete = states['INCOMPLETE_EVIDENCE_WINDOW']
    if set(ends) - set(runs) or any(doc['run_id'] not in runs for doc in opportunities.values()):
        integrity['RUN_LINKAGE'] += 1
    if set(results) - set(attempts):
        integrity['RESULT_WITHOUT_ATTEMPT'] += 1
    by_key: dict[str, dict] = {}
    for doc in attempts.values():
        if doc['key'] in by_key:
            integrity['DUPLICATE_NEW_CANONICAL'] += 1
        by_key[doc['key']] = doc
    diagnostics: Counter[str] = Counter()
    for doc in ends.values():
        diagnostics.update(doc['diagnostics'])
    if diagnostics.get('LEDGER_WRITE_FAILURE', 0):
        integrity['INCOMPLETE_ATTEMPT_LEDGER'] += diagnostics['LEDGER_WRITE_FAILURE']
    for code in ('SOURCE_UNAVAILABLE_CONFLICT', 'SNAPSHOT_UNAVAILABLE_CONFLICT'):
        if diagnostics.get(code, 0):
            integrity[code] += diagnostics[code]
    for repo in (e, s, ledger):
        if repo.connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            integrity['SQLITE_INTEGRITY'] += 1
        if repo.connection.execute('PRAGMA foreign_key_check').fetchall():
            integrity['SQLITE_FOREIGN_KEY'] += 1
    receipts = {}
    for (hashed,) in e.connection.execute("SELECT receipt_hash FROM fc_receipts WHERE event='DECISION' ORDER BY ordering"):
        try:
            receipts[hashed] = e.load_cutoff(hashed)
        except Exception:
            integrity['INVALID_DECISION_RECEIPT'] += 1
    try:
        registered_sources = len(e.inspect())
    except Exception:
        registered_sources = None
        integrity['INVALID_SOURCE_EVIDENCE'] += 1
    cutoff = []
    for doc in attempts.values():
        if doc['receipt'] is not None:
            if doc['receipt'] not in receipts:
                integrity['ATTEMPT_RECEIPT_UNAVAILABLE'] += 1
            else:
                cutoff.append(receipts[doc['receipt']].cutoff)
    verified, failed, snapshots = 0, 0, []
    raw_rows = s.connection.execute('SELECT opportunity_key FROM fc_v2_snapshots ORDER BY opportunity_key').fetchall()
    for (key,) in raw_rows:
        try:
            value = s.load(key)
            attempt = by_key.get(key)
            if attempt is None or (attempt['candidate_id'], attempt['receipt'], attempt['fixture_id'], attempt['competition_id'], attempt['profile']) != (
                    value.opportunity.candidate_id, value.receipt.receipt_hash, value.opportunity.fixture_id,
                    value.binding.competition_id, value.binding.classification.profile.value):
                raise ValueError('SNAPSHOT_ATTEMPT_LINKAGE')
            snapshots.append(value)
            reproduce(e, value)
            verified += 1
        except Exception:
            failed += 1
    if failed:
        integrity['SNAPSHOT_REPRODUCTION_FAILED'] += failed
    snapshot_ids = {v.snapshot_id for v in snapshots}
    for doc in results.values():
        if doc['snapshot_id'] is not None and doc['snapshot_id'] not in snapshot_ids:
            integrity['RESULT_SNAPSHOT_UNAVAILABLE'] += 1
    missing_results = len(set(attempts) - set(results))
    if missing_results:
        integrity['ATTEMPT_RESULT_UNAVAILABLE'] += missing_results
    histogram, features = feature_coverage(tuple(v.projection for v in snapshots))
    profiles: Counter[str] = Counter()
    regulations: Counter[str] = Counter()
    sources = {k: Counter() for k in ('TARGET', 'CURRENT', 'PREVIOUS')}
    for key in attempts:
        result = results.get(key)
        for kind in sources:
            sources[kind][result['sources'][kind] if result else 'RESULT_UNAVAILABLE'] += 1
    groups: dict[tuple[int, str], list] = {}
    for value in snapshots:
        profile = value.binding.classification.profile.value
        profiles[profile] += 1
        regulations[value.binding.current_format.verdict(value.receipt.cutoff)] += 1
        groups.setdefault((value.binding.competition_id, profile), []).append(value)
    n = len(snapshots)
    competitions = {v.binding.competition_id for v in snapshots}
    days = {v.receipt.cutoff.date() for v in snapshots}
    breakdown = []
    for (competition, profile), values in sorted(groups.items()):
        row = {'competition_id': competition, 'profile': profile, 'snapshots': len(values),
               'sample_sufficient': len(values) >= 10}
        if len(values) >= 10:
            row['feature_availability'] = {name: rate(sum(v.projection.missing[i] == 0 for v in values),
                len(values), 'group_successful_immutable_snapshots') for i, name in enumerate(FEATURE_NAMES)}
        breakdown.append(row)
    return {
        'version': 'FC_READINESS_2',
        'readiness': readiness(attempts=len(attempts), snapshots=n, competitions=len(competitions), days=len(days),
                               failures=sum(integrity.values()), incomplete=window_incomplete),
        'phase_e_authorized': False,
        'thresholds': {'snapshots': 100, 'competitions': 5, 'distinct_utc_decision_dates': 7,
                       'reproduction_fraction': '1.000000', 'integrity_failures': 0, 'group_minimum': 10},
        'denominator_definitions': {
            'canonical': 'Unique fixture:market keys seen at the existing coordinator canonical-freeze hook during enabled runs; includes old rows separately.',
            'attempts': 'New canonical PREMATCH fixture:market opportunities observed during enabled runs, including receipt, scope, source and persistence failures.',
            'successful_immutable_snapshots': 'Structurally valid immutable snapshots with exact prospective attempt linkage; reproduction failures are separately blocking.',
            'discovery': 'Not a canonical opportunity denominator; no discovery percentages are calculated.',
            'feature_missing_reasons': 'One count per missing feature/reason; multiple reasons may apply.',
            'sources': 'Phase B source-selection verdict per eligible attempt; SELECTED proves query/as-of payload availability, not regulation/support.',
            'regulation_and_profiles': 'Successful immutable snapshots; current target regulation counted once per snapshot.',
            'runs': 'All persisted runs remain visible; incomplete_runs includes preflight failures. Only evidence_window_incomplete_runs blocks completeness, alongside integrity failures.',
        },
        'denominator_completeness': 'UNPROVEN' if window_incomplete or integrity else 'VERIFIED_PERSISTED_RUNS',
        'runs': len(runs), 'incomplete_runs': incomplete,
        'historical_preflight_failures': states['PREFLIGHT_FAILURE'],
        'evidence_window_incomplete_runs': window_incomplete,
        'completed_observation_runs': states['COMPLETED_OBSERVATION'],
        'run_classification': run_details,
        'observed_canonical_prematch_opportunities': len({v['key'] for v in opportunities.values()}),
        'old_canonical_observations_not_attempted': sum(not v['attempted'] for v in opportunities.values()),
        'final_evaluated_candidates': diagnostics.get('FINAL_EVALUATED_CANDIDATES', 0),
        'v2_observation_attempts': len(attempts), 'durable_decision_receipts': len(receipts),
        'attempts_with_durable_receipt': sum(v['receipt'] in receipts for v in attempts.values()),
        'registered_sources': registered_sources, 'snapshot_rows': len(raw_rows), 'successful_v2_snapshots': n,
        'snapshot_rate': rate(n, len(attempts), 'eligible_v2_observation_attempts'),
        'available_feature_histogram': histogram,
        'all_seven_available': rate(histogram['7'], n, 'successful_immutable_snapshots'),
        'features': features,
        'source_availability': {k: {'verdict_counts': dict(sorted(v.items())),
            'available': v['SELECTED'], 'missing': len(attempts)-v['SELECTED'],
            'rate': rate(v['SELECTED'], len(attempts), 'eligible_v2_observation_attempts')} for k, v in sources.items()},
        'regulation_counts': {k: regulations[k] for k in ('VERIFIED_90', 'REGULATION_UNVERIFIED', 'UNSUPPORTED_REGULATION')},
        'profile_counts': dict(sorted(profiles.items())),
        'attempt_profile_counts': dict(sorted(Counter(v['profile'] for v in attempts.values()).items())),
        'diagnostics': dict(sorted(diagnostics.items())),
        'source_capture_failure_counts': {k: v for k, v in sorted(diagnostics.items())
            if k in ('SOURCE_CAPTURE_EXCEPTION', 'CLIENT_CAPTURE_FAILURE', 'EVIDENCE_STORE_UNAVAILABLE')
            or k.startswith('SOURCE_UNAVAILABLE')},
        'snapshot_failure_counts': dict(sorted(Counter(v['status'] for v in results.values() if v['status'] != 'CAPTURED').items())),
        'reproduction': {'VERIFIED': verified, 'FAILED': failed, 'rate': rate(verified, len(raw_rows), 'all_stored_snapshot_rows')},
        'integrity_failures': dict(sorted(integrity.items())),
        'first_decision_cutoff': min(cutoff) if cutoff else None,
        'last_decision_cutoff': max(cutoff) if cutoff else None,
        'unique_fixtures': len({v['fixture_id'] for v in attempts.values()}),
        'unique_competitions': len({v['competition_id'] for v in attempts.values()}),
        'snapshot_unique_fixtures': len({v.opportunity.fixture_id for v in snapshots}),
        'snapshot_unique_competitions': len(competitions), 'snapshot_distinct_utc_days': len(days),
        'competition_profile_breakdown': breakdown,
        'interpretation': 'Input availability only. Coverage does not establish predictive value or authorize Phase E.',
    }
