"""Deterministic offline normalization, rates, finite Pi replay and current form.

No runtime callers. calculate_context accepts supplied evidence only. Lower-level
functions permit synthetic golden vectors; form/difference verify sample/state
pool and cutoff bindings. A supplied Pi state must be produced by replay_pi for
real use (persistence and replay verification are later-phase responsibilities).
"""
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import TypeVar

from .contracts import (
    ContextInput, ContextResult, Exclusion, Feature, Fixture, FormComponent,
    Freshness, Game, History, PiState, Pool, Sample, SelectedGame, SourceRef,
    Status, TeamRating,
)
from .fingerprint import canonical_bytes, feature_text, fingerprint, semantic_fingerprint, utc
from .policy import CONTRACT, FEATURE_NAMES, REASONS, decimal_context, history_policy


def ordered_reasons(reasons: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Deduplicate missing reasons using the normative precedence."""
    if any(reason not in REASONS for reason in reasons):
        raise ValueError('UNKNOWN_MISSING_REASON')
    return tuple(reason for reason in REASONS if reason in reasons)


def exact_days(later: datetime, earlier: datetime) -> Decimal:
    """Integer microseconds, never float total_seconds()."""
    delta = utc(later) - utc(earlier)
    micros = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    with localcontext(decimal_context()):
        return Decimal(micros) / Decimal(86400000000)


Evidence = TypeVar("Evidence")


def _unique(items: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    # Order-independent evidence sets; arrays describing selections remain ordered.
    keyed = {canonical_bytes(item): item for item in items}
    return tuple(keyed[key] for key in sorted(keyed))


def _pair(row: Fixture) -> tuple[int | None, int | None]:
    if row.status == 'FT' and row.fulltime_home is None and row.fulltime_away is None:
        return row.goals_home, row.goals_away
    return row.fulltime_home, row.fulltime_away


def _batch_reasons(batch: History | None) -> tuple[str, ...]:
    if batch is None:
        return ('SOURCE_UNAVAILABLE',)
    reasons = []
    if batch.regulation.reason:
        reasons.append(batch.regulation.reason)
    if batch.source is None or batch.freshness == Freshness.UNAVAILABLE or len(batch.rows) > 99:
        reasons.append('SOURCE_UNAVAILABLE')
    if batch.freshness == Freshness.STALE_COLLECTION:
        reasons.append('STALE_SOURCE')
    return ordered_reasons(reasons)


def normalize_history(inputs: ContextInput) -> Pool:
    """Validate supplied identities/as-of, quarantine conflicts and order eligible facts.

    No as-of reader: known_at is an assertion supplied by the caller. Wrong target
    response season, provider or future evidence is a hard contract failure.
    Ineligible football rows and invalid optional responses remain diagnostics.
    """
    target = inputs.target
    for batch, season in ((inputs.current, target.season), (inputs.previous, target.season - 1)):
        if batch is None:
            continue
        if batch.season != season:
            raise ValueError('WRONG_QUERY_SEASON')
        if batch.source is not None and batch.source.known_at > target.cutoff:
            raise ValueError('FUTURE_KNOWN_AT')
        if batch.source is not None and batch.source.known_at == target.cutoff and not batch.source.available_before_capture:
            raise ValueError('CAPTURE_ORDER_UNPROVEN')
        if any(row.provider != target.provider for row in batch.rows):
            raise ValueError('PROVIDER_IDENTITY_MISMATCH')
    policy = history_policy(target.classification.profile)
    reasons = list(_batch_reasons(inputs.current))
    if policy is None:
        reasons.append('UNSUPPORTED_PROFILE')
    if target.regulation.reason:
        reasons.append(target.regulation.reason)
    exclusions = []
    candidates: dict[int, list[tuple[Fixture, SourceRef]]] = {}
    sources = []
    evidence = []
    for batch in (inputs.current, inputs.previous):
        if batch is None:
            evidence.append(None)
            continue
        rows = _unique(batch.rows)
        evidence.append(replace(batch, rows=rows))
        if batch.source is not None:
            sources.append(batch.source)
        batch_reasons = _batch_reasons(batch)
        if batch_reasons:
            exclusions.append(Exclusion(None, batch_reasons, rows,
                                        () if batch.source is None else (batch.source,)))
            continue
        for row in rows:
            candidates.setdefault(row.fixture_id, []).append((row, batch.source))
    games = []
    for fixture_id, entries in sorted(candidates.items()):
        rows = _unique(tuple(row for row, _ in entries))
        refs = _unique(tuple(ref for _, ref in entries))
        # Compare football facts before eligibility: never let an invalid competing
        # identity/score version win through filtering. ET/shootout totals are not facts used here.
        signatures = {canonical_bytes((r.provider, r.fixture_id, r.competition_id, r.season,
                        r.home_team_id, r.away_team_id, r.kickoff, r.entity_scope, _pair(r),
                        r.status, r.neutral, r.phase)) for r in rows}
        if len(signatures) != 1:
            exclusions.append(Exclusion(fixture_id, ('CONFLICTING_FACTS',), rows, refs))
            continue
        row = rows[0]
        pair = _pair(row)
        excluded = []
        if fixture_id == target.fixture_id:
            excluded.append('TARGET_FIXTURE')
        if type(row.competition_id) is not int or row.competition_id != target.competition_id:
            excluded.append('WRONG_COMPETITION')
        if type(row.season) is not int or row.season not in (target.season, target.season - 1) or any(
            row.season != batch.season for batch in (inputs.current, inputs.previous)
            if batch is not None and any(r.fixture_id == fixture_id for r in batch.rows)
        ):
            excluded.append('WRONG_SEASON')
        if row.entity_scope != target.classification.entity_scope:
            excluded.append('WRONG_ENTITY_SCOPE')
        if any(type(t) is not int or t <= 0 for t in (row.home_team_id, row.away_team_id)) or row.home_team_id == row.away_team_id:
            excluded.append('INVALID_TEAM_IDENTITY')
        if row.status not in ('FT', 'AET', 'PEN'):
            excluded.append('UNFINISHED_OR_UNSUPPORTED_STATUS')
        if any(type(score) is not int or not 0 <= score <= 30 for score in pair):
            excluded.append('INVALID_REGULATION_SCORE_PAIR')
        if row.kickoff >= target.cutoff:
            excluded.append('AT_OR_AFTER_CUTOFF')
        if any(ref.known_at < row.kickoff for ref in refs):
            excluded.append('COMPLETION_NOT_OBSERVED')
        if policy is None or row.kickoff < target.cutoff - timedelta(days=policy[0]):
            excluded.append('OUTSIDE_HISTORY_HORIZON')
        if excluded:
            exclusions.append(Exclusion(fixture_id, tuple(excluded), rows, refs))
        else:
            games.append(Game(row, pair[0], pair[1], refs))
    input_hash = fingerprint('FC_SOURCE_BUNDLE_V1', {'target': target, 'responses': evidence})
    available = not _batch_reasons(inputs.current)
    # An optional previous response cannot compensate for unavailable current evidence.
    return Pool(target, tuple(sorted(games, key=lambda g: (g.fixture.kickoff, g.fixture.fixture_id)))
                if available and not reasons else (),
                tuple(sorted(exclusions, key=canonical_bytes)), ordered_reasons(reasons),
                available, inputs.previous is not None, _unique(tuple(sources)), input_hash)


def pool_fingerprint(pool: Pool) -> str:
    """Fingerprint normalized pool plus all supplied/excluded evidence identity."""
    return fingerprint('FC_SOURCE_BUNDLE_V1', pool)


def select_sample(pool: Pool, team_id: int) -> Sample:
    """All venues, latest maximum eight; expose weights, N and effective N only as diagnostics."""
    if team_id not in (pool.target.home_team_id, pool.target.away_team_id):
        raise ValueError('TARGET_TEAM_REQUIRED')
    policy = history_policy(pool.target.classification.profile)
    selected = tuple(g for g in reversed(pool.games)
                     if team_id in (g.fixture.home_team_id, g.fixture.away_team_id))[:8]
    count = len(selected) if pool.history_available and policy is not None and not pool.reasons else None
    reasons = list(pool.reasons)
    relevant_exclusions = tuple(e for e in pool.exclusions if not e.facts or any(
        team_id in (r.home_team_id, r.away_team_id) for r in e.facts))
    if count is not None:
        if selected and exact_days(pool.target.cutoff, selected[0].fixture.kickoff) > min(policy[0], 120):
            reasons.append('STALE_TEAM_HISTORY')
        if count < 3:
            reasons.append('INSUFFICIENT_SAMPLE')
            if any('CONFLICTING_FACTS' in e.reasons for e in relevant_exclusions):
                reasons.append('CONFLICTING_FACTS')
    diagnostics = []
    with localcontext(decimal_context()):
        for game in selected:
            row = game.fixture
            home = row.home_team_id == team_id
            exponent = -exact_days(selected[0].fixture.kickoff, row.kickoff) / Decimal(policy[1])
            weight = (exponent * Decimal(2).ln()).exp()
            diagnostics.append(SelectedGame(row.fixture_id, row.kickoff, 'HOME' if home else 'AWAY',
                row.away_team_id if home else row.home_team_id,
                game.gf_home if home else game.gf_away, game.gf_away if home else game.gf_home,
                weight, fingerprint('FC_SOURCE_BUNDLE_V1', game)))
        total = sum((g.weight for g in diagnostics), Decimal(0))
        effective = total * total / sum((g.weight * g.weight for g in diagnostics), Decimal(0)) if diagnostics else None
    return Sample(team_id, tuple(diagnostics), policy[0] if policy else None,
                  policy[1] if policy else None, count, effective,
                  selected[-1].fixture.kickoff if selected else None,
                  selected[0].fixture.kickoff if selected else None,
                  ordered_reasons(reasons), relevant_exclusions, pool_fingerprint(pool), pool.target.cutoff)


def _feature(index: int, value: Decimal | None, reasons: tuple[str, ...], count: int | None,
             **diagnostics: object) -> Feature:
    if (value is None) != bool(reasons):
        raise ValueError('INVALID_FEATURE_AVAILABILITY')
    return Feature(FEATURE_NAMES[index], feature_text(value, index) if value is not None else None,
                   Status.AVAILABLE if value is not None else Status.MISSING,
                   ordered_reasons(reasons), count, **diagnostics)


def weighted_rates(sample: Sample, *, home: bool) -> tuple[Feature, Feature]:
    """Pair of observed GF/GA weighted means over exactly the same selected sample."""
    offset = 0 if home else 2
    values = [None, None]
    if not sample.reasons:
        with localcontext(decimal_context()):
            total = sum((g.weight for g in sample.games), Decimal(0))
            values = [sum((g.weight * Decimal(getattr(g, field)) for g in sample.games), Decimal(0)) / total
                      for field in ('gf', 'ga')]
    return tuple(_feature(offset + i, value, sample.reasons, sample.count, sample=sample)
                 for i, value in enumerate(values))


def replay_pi(pool: Pool) -> PiState:
    """Reconstruct finite same-competition state from zero in canonical ascending order."""
    ratings: dict[int, TeamRating] = {}
    with localcontext(decimal_context()):
        for game in pool.games:
            h, a = game.fixture.home_team_id, game.fixture.away_team_id
            home = ratings.get(h, TeamRating(h, Decimal(0), Decimal(0), 0, 0, 0))
            away = ratings.get(a, TeamRating(a, Decimal(0), Decimal(0), 0, 0, 0))
            error = Decimal(game.gf_home - game.gf_away) - (home.home - away.away)
            update = error / (Decimal(1) + Decimal('0.75') * abs(error))
            ratings[h] = TeamRating(h, home.home + Decimal('0.15') * update,
                                    home.away + Decimal('0.10') * update,
                                    home.total + 1, home.designated_home + 1, home.designated_away)
            ratings[a] = TeamRating(a, away.home - Decimal('0.10') * update,
                                    away.away - Decimal('0.15') * update,
                                    away.total + 1, away.designated_home, away.designated_away + 1)
    return PiState(tuple(ratings[t] for t in sorted(ratings)), pool.games, pool.target.cutoff,
                   pool_fingerprint(pool), semantic_fingerprint())


def pi_fingerprint(state: PiState) -> str:
    """State identity includes replay manifest, evidence pool and all semantic constants."""
    return fingerprint('FC_PI_STATE_V1', state)


def _bound(sample: Sample, state: PiState) -> None:
    if sample.pool_fingerprint != state.pool_fingerprint or sample.cutoff != state.cutoff or state.semantic_fingerprint != semantic_fingerprint():
        raise ValueError('PI_SAMPLE_BINDING_MISMATCH')


def rational_expected(difference: Decimal) -> Decimal:
    """RFC rational expectation, explicitly not a logistic sigmoid or probability model."""
    if not isinstance(difference, Decimal) or not difference.is_finite():
        raise ValueError('INVALID_PI_DIFFERENCE')
    with localcontext(decimal_context()):
        return Decimal('0.5') + difference / (Decimal(2) * (Decimal(1) + abs(difference)))


def _supported(rating: TeamRating | None, home: bool) -> bool:
    return rating is not None and rating.total >= 4 and (
        rating.designated_home if home else rating.designated_away) >= 1


def current_pi_form(sample: Sample, state: PiState, *, home: bool) -> Feature:
    """Current-strength re-evaluation at T; never substitute unsupported opponents."""
    _bound(sample, state)
    reasons = list(sample.reasons)
    components = []
    with localcontext(decimal_context()):
        for i, game in enumerate(sample.games):
            designated_home = game.designation == 'HOME'
            team, opponent = state.rating(sample.team_id), state.rating(game.opponent_id)
            supported = _supported(team, designated_home) and _supported(opponent, not designated_home)
            actual = Decimal(1) if game.gf > game.ga else Decimal('0.5') if game.gf == game.ga else Decimal(0)
            margin = max(Decimal('-0.10'), min(Decimal('0.10'), Decimal('0.025') * Decimal(game.gf - game.ga)))
            expected = performance = None
            if supported:
                x = (team.home if designated_home else team.away) - (opponent.away if designated_home else opponent.home)
                expected = rational_expected(x)
                performance = max(Decimal(0), min(Decimal(1), Decimal('0.5') + actual - expected + margin))
            else:
                reasons.append('UNSUPPORTED_PI_STATE')
            components.append(FormComponent(game.fixture_id, game.designation, game.opponent_id,
                actual, expected, margin, performance, len(sample.games) - i, team, opponent, supported))
        value = None if reasons else sum((Decimal(c.rank_weight) * c.performance for c in components), Decimal(0)) / (
            Decimal(len(components) * (len(components) + 1)) / Decimal(2))
    return _feature(4 if home else 5, value, ordered_reasons(reasons), sample.count,
                    sample=sample, form_components=tuple(components), pi_fingerprint=pi_fingerprint(state))


def pi_difference(pool: Pool, state: PiState, home: Sample, away: Sample) -> Feature:
    """Designated-side difference with both total/side support and target recency guards."""
    _bound(home, state)
    _bound(away, state)
    if state.pool_fingerprint != pool_fingerprint(pool) or state.cutoff != pool.target.cutoff:
        raise ValueError('PI_POOL_BINDING_MISMATCH')
    h, a = state.rating(pool.target.home_team_id), state.rating(pool.target.away_team_id)
    reasons = list(pool.reasons)
    reasons.extend(home.reasons)
    reasons.extend(away.reasons)
    if pool.history_available and not pool.reasons and (
        h is None or a is None or min(h.total, a.total) < 8 or h.designated_home < 3 or a.designated_away < 3
    ):
        reasons.append('INSUFFICIENT_SAMPLE')
        if any('CONFLICTING_FACTS' in e.reasons for e in (*home.exclusions, *away.exclusions)):
            reasons.append('CONFLICTING_FACTS')
    with localcontext(decimal_context()):
        value = None if reasons else h.home - a.away
    return _feature(6, value, ordered_reasons(reasons), len(pool.games) if pool.history_available else None,
                    support=(h, a), pi_fingerprint=pi_fingerprint(state))


def calculate_context(inputs: ContextInput) -> ContextResult:
    """Seven-feature offline result, independently available per side; no snapshot persistence."""
    pool = normalize_history(inputs)
    home, away = select_sample(pool, inputs.target.home_team_id), select_sample(pool, inputs.target.away_team_id)
    state = replay_pi(pool)
    features = (*weighted_rates(home, home=True), *weighted_rates(away, home=False),
                current_pi_form(home, state, home=True), current_pi_form(away, state, home=False),
                pi_difference(pool, state, home, away))
    return ContextResult(CONTRACT, semantic_fingerprint(), inputs.target, pool, state, features)


def result_fingerprint(result: ContextResult) -> str:
    """Canonical pure result identity; no receipt, database ID or process state."""
    return fingerprint('FC_SNAPSHOT_V1', result)
