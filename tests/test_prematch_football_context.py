"""Phase A RFC goldens and offline invariants; exclusively synthetic supplied facts."""
import ast
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
import hashlib
from pathlib import Path
import random
import subprocess
import sys
import unittest

from app.prematch_football_context import (
    CONTRACT, FEATURE_NAMES, calculate_context, result_fingerprint, semantic_fingerprint, semantic_manifest,
)
from app.prematch_football_context.calculations import (
    current_pi_form, exact_days, normalize_history, pi_difference, pi_fingerprint,
    rational_expected, replay_pi, select_sample,
)
from app.prematch_football_context.contracts import (
    Classification, ContextInput, Fixture, Freshness, History, Neutral, Regulation,
    SourceRef, Status, Target, TeamRating,
)
from app.prematch_football_context.fingerprint import canonical_bytes, feature_text, fingerprint
from app.prematch_football_context.policy import Profile, decimal_context, history_policy

D = Decimal
T = datetime(2026, 9, 23, 12, 0, 0, 123456, tzinfo=timezone.utc)
CLASSIFICATION = Classification(Profile.SENIOR_MEN_PRO, 'SYNTHETIC_V1', 'TEST', (),
                                'MEN', 'SENIOR', 'CLUB', 'a' * 64)
FORMAT = Regulation(90, 'SYNTHETIC_90_V1', 'b' * 64)
SOURCE = SourceRef('synthetic', 'current', 'c' * 64, T - timedelta(minutes=1))
TARGET = Target('API_FOOTBALL', 9999, 10, 2026, 1, 2, T + timedelta(hours=1), T,
                CLASSIFICATION, FORMAT, SOURCE)


def fixture(identifier: int, *, days: int = 1, home: int = 1, away: int = 2,
            gf: int = 1, ga: int = 0, **changes: object) -> Fixture:
    row = Fixture('API_FOOTBALL', identifier, 10, 2026, home, away,
                  T - timedelta(days=days), CLASSIFICATION.entity_scope, gf, ga)
    return replace(row, **changes)


def request(rows: tuple[Fixture, ...], *, target: Target = TARGET,
            previous: History | None = None) -> ContextInput:
    return ContextInput(target, History(target.season, SOURCE, target.regulation, rows), previous)


def sample_state(rows: tuple[Fixture, ...]):
    pool = normalize_history(request(rows))
    return pool, select_sample(pool, 1), select_sample(pool, 2), replay_pi(pool)


def rating(team: int, *, total: int = 8, home: int = 4, value: str = '0') -> TeamRating:
    return TeamRating(team, D(value), D(value), total, home, total - home)


class RatesGoldens(unittest.TestCase):
    def test_T01_exact_half_life_and_orientation(self):
        rows = (fixture(1, gf=2, ga=0), fixture(2, days=121, home=2, away=1, gf=1, ga=1),
                fixture(3, days=241, gf=0, ga=2))
        result = calculate_context(request(rows))
        self.assertEqual([f.value for f in result.features[:4]], ['1.428571', '0.571429', '0.571429', '1.428571'])
        sample = result.features[0].sample
        self.assertEqual(tuple(g.weight for g in sample.games), (D(1), D('.5'), D('.25')))
        self.assertEqual(tuple(g.gf for g in sample.games), (2, 1, 0))
        self.assertEqual(tuple(g.ga for g in sample.games), (0, 1, 2))
        self.assertEqual(sample.count, 3)
        self.assertEqual((sample.horizon_days, sample.half_life_days), (365, 120))
        self.assertEqual(sample.latest, rows[0].kickoff)
        self.assertEqual(sample.oldest, rows[-1].kickoff)
        with localcontext(decimal_context()):
            self.assertEqual(sample.effective_sample_size, D('1.75') ** 2 / D('1.3125'))
        swap = calculate_context(request(rows, target=replace(TARGET, home_team_id=2, away_team_id=1)))
        self.assertEqual(swap.features[0].value, result.features[2].value)
        self.assertEqual(swap.features[2].value, result.features[0].value)
        # Neither raw mean (1), total (3), nor a home-venue-only statistic.
        self.assertNotIn(result.features[0].value, ('1.000000', '3.000000'))

    def test_T02_sample_boundaries(self):
        for n in (2, 3, 8, 9):
            with self.subTest(n=n):
                result = calculate_context(request(tuple(fixture(i + 1, days=i + 1) for i in range(n))))
                f = result.features[0]
                self.assertEqual(f.sample_count, min(n, 8))
                self.assertEqual(f.status, Status.MISSING if n == 2 else Status.AVAILABLE)
                self.assertEqual(tuple(g.fixture_id for g in f.sample.games), tuple(range(1, min(n, 8) + 1)))
        eight = calculate_context(request(tuple(fixture(i + 1, days=i + 1) for i in range(8))))
        nine = calculate_context(request(tuple(fixture(i + 1, days=i + 1) for i in range(8)) + (fixture(9, days=9, gf=30),)))
        self.assertEqual(eight.features[0].value, nine.features[0].value)

    def test_T15_side_independent_missingness(self):
        rows = tuple(fixture(i, home=1, away=10 + i) for i in range(1, 4))
        result = calculate_context(request(rows))
        self.assertTrue(all(f.status == Status.AVAILABLE for f in result.features[:2]))
        self.assertTrue(all(f.status == Status.MISSING for f in result.features[2:]))
        self.assertEqual(result.features[2].sample_count, 0)

    def test_pair_invalidates_both_rates(self):
        rows = tuple(fixture(i) for i in range(1, 4))
        for invalid in (None, -1, 31):
            with self.subTest(invalid=invalid):
                result = calculate_context(request((replace(rows[0], fulltime_away=invalid), *rows[1:])))
                self.assertEqual([f.value for f in result.features[:2]], [None, None])
                self.assertEqual(result.features[0].sample_count, 2)
                self.assertIn('INVALID_REGULATION_SCORE_PAIR', result.pool.exclusions[0].reasons)


class PiFormGoldens(unittest.TestCase):
    def test_T03_current_form_and_rational_not_logistic(self):
        rows = (fixture(1, days=1), fixture(2, days=2, gf=1, ga=1), fixture(3, days=3, gf=0, ga=1))
        pool, home, away, state = sample_state(rows)
        state = replace(state, ratings=(rating(1), rating(2)))
        form = current_pi_form(home, state, home=True)
        self.assertEqual(form.value, '0.666667')
        self.assertEqual(tuple(c.performance for c in form.form_components), (D(1), D('.5'), D(0)))
        self.assertEqual(tuple(c.rank_weight for c in form.form_components), (3, 2, 1))
        self.assertEqual(tuple(c.margin for c in form.form_components), (D('.025'), D(0), D('-.025')))
        self.assertEqual(rational_expected(D(1)), D('.75'))
        with localcontext(decimal_context()):
            logistic = D(1) / (D(1) + D(-1).exp())
        self.assertNotEqual(rational_expected(D(1)), logistic)
        changed = replace(state, ratings=(rating(1, value='1'), rating(2)))
        changed_form = current_pi_form(home, changed, home=True)
        self.assertTrue(all(c.expected == D('.75') for c in changed_form.form_components))
        self.assertNotEqual(changed_form.pi_fingerprint, form.pi_fingerprint)
        self.assertNotEqual(changed_form.value, form.value)

    def test_T04_one_update_zero_seed_and_old_state(self):
        pool, home, away, state = sample_state((fixture(1),))
        h, a = state.rating(1), state.rating(2)
        with localcontext(decimal_context()):
            u = D(4) / D(7)
            self.assertEqual(h.home, D('.15') * u)
            self.assertEqual(h.away, D('.10') * u)
            self.assertEqual(a.home, -D('.10') * u)
            self.assertEqual(a.away, -D('.15') * u)
        self.assertEqual((h.total, h.designated_home, h.designated_away), (1, 1, 0))
        self.assertEqual((a.total, a.designated_home, a.designated_away), (1, 0, 1))
        self.assertIsNone(pi_difference(pool, state, home, away).value)
        self.assertIsNone(state.rating(1000))

    def test_T05_difference_support_boundaries_and_available_zero(self):
        rows = tuple(fixture(i, days=i, gf=0, ga=0) for i in range(1, 9))
        pool, home, away, state = sample_state(rows)
        for total, home_count, away_count, available in ((7, 3, 3, False), (8, 2, 3, False),
                (8, 3, 2, False), (8, 3, 3, True)):
            with self.subTest(total=total, home=home_count, away=away_count):
                pinned = replace(state, ratings=(rating(1, total=total, home=home_count),
                                                 rating(2, total=total, home=total - away_count)))
                f = pi_difference(pool, pinned, home, away)
                self.assertEqual(f.value, '0.000000' if available else None)
                self.assertEqual(f.status == Status.AVAILABLE, available)
        # Actual replay also reaches support, including a legitimate zero state.
        result = calculate_context(request(rows))
        self.assertEqual(result.features[6].value, '0.000000')

    def test_T05_form_every_opponent_and_dimension_boundaries(self):
        rows = tuple(fixture(i, days=i, away=3 if i == 8 else 2) for i in range(1, 10))
        pool, home, _, state = sample_state(rows)
        for total, dimension, available in ((3, 1, False), (4, 0, False), (4, 1, True)):
            with self.subTest(total=total, dimension=dimension):
                pinned = replace(state, ratings=(rating(1), rating(2), rating(3, total=total, home=total - dimension)))
                f = current_pi_form(home, pinned, home=True)
                self.assertEqual(f.status == Status.AVAILABLE, available)
                self.assertEqual(f.sample_count, 8)
                self.assertEqual(tuple(c.fixture_id for c in f.form_components), tuple(range(1, 9)))
                if not available:
                    self.assertIn('UNSUPPORTED_PI_STATE', f.reasons)
                    self.assertFalse(f.form_components[-1].supported)
        for target_rating in (rating(1, total=3, home=1), rating(1, home=0)):
            pinned = replace(state, ratings=(target_rating, rating(2), rating(3)))
            self.assertIn('UNSUPPORTED_PI_STATE', current_pi_form(home, pinned, home=True).reasons)

    def test_T15_form_sides_can_differ(self):
        rows = tuple(fixture(i, days=i, home=1 if i < 4 else 2, away=3 if i < 4 else 4) for i in range(1, 7))
        pool, home, away, state = sample_state(rows)
        pinned = replace(state, ratings=(rating(1), rating(2), rating(3), rating(4, total=3, home=1)))
        self.assertEqual(current_pi_form(home, pinned, home=True).status, Status.AVAILABLE)
        self.assertEqual(current_pi_form(away, pinned, home=False).status, Status.MISSING)

    def test_supported_zero_form_is_available(self):
        _, sample, _, state = sample_state(tuple(fixture(i, gf=0, ga=1) for i in range(1, 4)))
        state = replace(state, ratings=(rating(1), rating(2)))
        form = current_pi_form(sample, state, home=True)
        self.assertEqual((form.value, form.status, form.reasons), ('0.000000', Status.AVAILABLE, ()))

    def test_form_clamps_only_explicit_formula_components(self):
        rows = (fixture(1, gf=30), fixture(2, days=2, gf=0, ga=30), fixture(3, days=3, gf=0, ga=0))
        _, home, _, state = sample_state(rows)
        state = replace(state, ratings=(rating(1), rating(2)))
        form = current_pi_form(home, state, home=True)
        self.assertEqual(tuple(c.margin for c in form.form_components), (D('.10'), D('-.10'), D(0)))
        self.assertTrue(all(D(0) <= c.performance <= D(1) for c in form.form_components))

    def test_no_cross_pool_or_cutoff_state(self):
        pool, home, away, state = sample_state(tuple(fixture(i) for i in range(1, 9)))
        with self.assertRaisesRegex(ValueError, 'BINDING'):
            current_pi_form(home, replace(state, pool_fingerprint='d' * 64), home=True)
        with self.assertRaisesRegex(ValueError, 'BINDING'):
            pi_difference(pool, replace(state, cutoff=T - timedelta(seconds=1)), home, away)


class EligibilityGoldens(unittest.TestCase):
    def test_T06_all_profile_constants(self):
        expected = ((365, 120),) * 6 + ((120, 30),) * 3 + ((120, 45), (180, 60), (180, 60), None)
        self.assertEqual(tuple(history_policy(p) for p in Profile), expected)
        target = replace(TARGET, classification=replace(CLASSIFICATION, profile=Profile.UNKNOWN))
        result = calculate_context(request((fixture(1),), target=target))
        self.assertTrue(all(f.value is None and f.reasons[0] == 'UNSUPPORTED_PROFILE' for f in result.features))

    def test_T06_horizon_cutoff_target_and_future(self):
        rows = (fixture(1, days=365), fixture(2, kickoff=T - timedelta(days=365, microseconds=1)),
                fixture(3, kickoff=T), fixture(4, kickoff=T + timedelta(days=1)),
                fixture(9999), fixture(5, kickoff=T - timedelta(microseconds=1)))
        # Supply evidence at T; assertion means completed observation before capture transaction.
        inp = request(rows)
        inp = replace(inp, current=replace(inp.current, source=replace(SOURCE, known_at=T, available_before_capture=True)))
        pool = normalize_history(inp)
        self.assertEqual(tuple(g.fixture.fixture_id for g in pool.games), (1, 5))
        excluded = {e.fixture_id: e.reasons for e in pool.exclusions}
        self.assertIn('TARGET_FIXTURE', excluded[9999])
        self.assertIn('AT_OR_AFTER_CUTOFF', excluded[3])
        self.assertIn('AT_OR_AFTER_CUTOFF', excluded[4])
        self.assertIn('OUTSIDE_HISTORY_HORIZON', excluded[2])

    def test_T06_recency_boundary(self):
        for delta, missing in ((timedelta(days=120), False), (timedelta(days=120, microseconds=1), True)):
            rows = tuple(fixture(i, kickoff=T - delta - timedelta(days=i - 1), gf=0, ga=0) for i in range(1, 9))
            result = calculate_context(request(rows))
            self.assertEqual('STALE_TEAM_HISTORY' in result.features[0].reasons, missing)
            self.assertEqual('STALE_TEAM_HISTORY' in result.features[6].reasons, missing)
            if not missing:
                self.assertEqual(result.features[6].value, '0.000000')

    def test_T06_T16_previous_season_optional_and_no_season_reset(self):
        current = tuple(fixture(i, days=i) for i in range(1, 3))
        old = fixture(3, days=3, season=2025)
        previous = History(2025, replace(SOURCE, identity='previous'), FORMAT, (old,))
        with_previous = calculate_context(request(current, previous=previous))
        without = calculate_context(request(current))
        self.assertEqual(with_previous.features[0].sample_count, 3)
        self.assertEqual(with_previous.pi_state.rating(1).total, 3)
        self.assertEqual(without.features[0].sample_count, 2)
        self.assertFalse(without.pool.previous_present)
        bad = replace(previous, rows=(replace(old, season=2024),))
        self.assertEqual(calculate_context(request(current, previous=bad)).features[0].sample_count, 2)
        with self.assertRaisesRegex(ValueError, 'WRONG_QUERY_SEASON'):
            calculate_context(request(current, previous=replace(previous, season=2024)))

    def test_T16_youth_horizon(self):
        target = replace(TARGET, classification=replace(CLASSIFICATION, profile=Profile.YOUTH_U19_U20, age_group='U19'))
        rows = tuple(fixture(i, days=days, entity_scope=target.classification.entity_scope)
                     for i, days in enumerate((1, 119, 120, 121), 1))
        result = calculate_context(request(rows, target=target))
        self.assertEqual(result.features[0].sample_count, 3)
        self.assertEqual(result.features[0].sample.half_life_days, 30)

    def test_T10_permutation_duplicates_same_kickoff_numeric_id(self):
        rows = (fixture(2), fixture(10), fixture(1), fixture(3, days=2))
        expected = calculate_context(request(rows))
        self.assertEqual(tuple(g.fixture.fixture_id for g in expected.pool.games), (3, 1, 2, 10))
        self.assertEqual(tuple(g.fixture_id for g in expected.features[0].sample.games), (10, 2, 1, 3))
        rng = random.Random(710)
        for _ in range(12):
            shuffled = list(rows + (rows[0], rows[-1]))
            rng.shuffle(shuffled)
            result = calculate_context(request(tuple(shuffled)))
            self.assertEqual(result, expected)
            self.assertEqual(result_fingerprint(result), result_fingerprint(expected))
            self.assertEqual(pi_fingerprint(result.pi_state), pi_fingerprint(expected.pi_state))

    def test_conflicting_duplicate_facts_all_quarantined(self):
        rows = tuple(fixture(i) for i in range(1, 5))
        for change in ({'fulltime_home': 4}, {'home_team_id': 20}, {'season': 2025}, {'competition_id': 20}):
            with self.subTest(change=change):
                conflict = replace(rows[0], **change)
                result = calculate_context(request(rows + (conflict,)))
                reverse = calculate_context(request(tuple(reversed(rows + (conflict,)))))
                self.assertEqual(result_fingerprint(result), result_fingerprint(reverse))
                self.assertEqual(result.features[0].sample_count, 3)
                self.assertEqual(result.features[0].status, Status.AVAILABLE)
                self.assertNotIn(1, tuple(g.fixture.fixture_id for g in result.pi_state.updates))
                self.assertTrue(any(e.reasons == ('CONFLICTING_FACTS',) and len(e.facts) == 2 for e in result.pool.exclusions))
        sparse = calculate_context(request(rows[:3] + (replace(rows[0], fulltime_home=4),)))
        self.assertEqual(sparse.features[0].reasons, ('CONFLICTING_FACTS', 'INSUFFICIENT_SAMPLE'))

    def test_T18_neutral_designation_unchanged(self):
        baseline = None
        for neutral in Neutral:
            rows = tuple(fixture(i, neutral=neutral) for i in range(1, 9))
            result = calculate_context(request(rows, target=replace(TARGET, neutral=neutral)))
            values = tuple(f.value for f in result.features)
            ratings = result.pi_state.ratings
            if baseline is None:
                baseline = values, ratings
            self.assertEqual((values, ratings), baseline)
            self.assertEqual(result.target.neutral, neutral)
            self.assertTrue(all(c.designation == 'HOME' for c in result.features[4].form_components))

    def test_T17_T19_competition_and_entity_isolation_no_rest(self):
        for profile in (Profile.SENIOR_WOMEN_PRO, Profile.YOUTH_U21_U23, Profile.RESERVE_OR_B_TEAM,
                        Profile.DOMESTIC_CUP, Profile.INTERNATIONAL_CLUB, Profile.INTERNATIONAL_SENIOR):
            with self.subTest(profile=profile):
                classification = replace(CLASSIFICATION, profile=profile, team_category=profile.value)
                target = replace(TARGET, classification=classification)
                valid = tuple(fixture(i, days=i, entity_scope=classification.entity_scope) for i in range(1, 4))
                unrelated = (fixture(4, competition_id=11, days=2, entity_scope=classification.entity_scope),
                             fixture(5, days=1))
                result = calculate_context(request(valid + unrelated, target=target))
                self.assertEqual(result.features[0].sample_count, 3)
                self.assertEqual(result.pi_state.rating(1).total, 3)
                self.assertEqual(tuple(f.name for f in result.features), FEATURE_NAMES)
                self.assertFalse(any('rest' in name for name in FEATURE_NAMES))
                self.assertFalse(result.complete_team_history)

    def test_T19_regulation_unverified_and_unsupported(self):
        for fmt, reason in ((Regulation(None, None, None), 'REGULATION_UNVERIFIED'),
                            (Regulation(90, None, None), 'REGULATION_UNVERIFIED'),
                            (Regulation(80, 'format80', 'd' * 64), 'UNSUPPORTED_REGULATION')):
            with self.subTest(format=fmt):
                result = calculate_context(request(tuple(fixture(i) for i in range(1, 4)), target=replace(TARGET, regulation=fmt)))
                self.assertTrue(all(f.value is None and reason in f.reasons for f in result.features))
        previous = History(2025, SOURCE, Regulation(None, None, None), (fixture(5, season=2025),))
        result = calculate_context(request(tuple(fixture(i) for i in range(1, 4)), previous=previous))
        self.assertEqual(result.features[0].status, Status.AVAILABLE)
        self.assertEqual(result.features[0].sample_count, 3)

    def test_T20_fulltime_only_aet_pen_and_ft_fallback(self):
        rows = tuple(fixture(i, status=status, gf=1, ga=1, goals_home=8, goals_away=6)
                     for i, status in enumerate(('FT', 'AET', 'PEN'), 1))
        result = calculate_context(request(rows))
        self.assertEqual(result.features[0].value, '1.000000')
        self.assertTrue(all(r.home == D(0) and r.away == D(0) for r in result.pi_state.ratings))
        self.assertTrue(all(c.actual == D('.5') for c in result.features[4].form_components))
        for status in ('AET', 'PEN'):
            bad = fixture(10, status=status, fulltime_home=None, fulltime_away=None, goals_home=2, goals_away=1)
            self.assertEqual(len(normalize_history(request((bad,))).games), 0)
        fallback = fixture(11, fulltime_home=None, fulltime_away=None, goals_home=2, goals_away=1)
        self.assertEqual(normalize_history(request((fallback,))).games[0].gf_home, 2)
        partial = replace(fallback, fulltime_home=1)
        self.assertFalse(normalize_history(request((partial,))).games)

    def test_T20_unsupported_statuses_and_invalid_teams(self):
        for status in ('ABD', 'SUSP', 'PST', 'CANC', '1H', '2H', 'AWD', 'WO', 'NS'):
            self.assertFalse(normalize_history(request((fixture(1, status=status),))).games)
        for home, away in ((1, 1), (0, 2), (-1, 2)):
            self.assertFalse(normalize_history(request((fixture(1, home=home, away=away),))).games)

    def test_source_unavailable_empty_stale_and_optional_omission(self):
        missing = calculate_context(ContextInput(TARGET, None))
        self.assertTrue(all(f.value is None and f.sample_count is None for f in missing.features))
        empty = calculate_context(request(()))
        self.assertEqual(empty.features[0].sample_count, 0)
        inp = request(tuple(fixture(i) for i in range(1, 4)))
        stale = calculate_context(replace(inp, current=replace(inp.current, freshness=Freshness.STALE_COLLECTION)))
        self.assertTrue(all('STALE_SOURCE' in f.reasons for f in stale.features))
        previous = History(2025, SOURCE, FORMAT, (), Freshness.STALE_COLLECTION)
        partial = calculate_context(replace(inp, previous=previous))
        self.assertEqual(partial.features[0].status, Status.AVAILABLE)
        self.assertTrue(any('STALE_SOURCE' in e.reasons for e in partial.pool.exclusions))
        oversized = calculate_context(request(tuple(fixture(i) for i in range(1, 101))))
        self.assertIn('SOURCE_UNAVAILABLE', oversized.features[0].reasons)

    def test_missing_reason_precedence_preserves_all_applicable_reasons(self):
        target = replace(TARGET, classification=replace(CLASSIFICATION, profile=Profile.UNKNOWN),
                         regulation=Regulation(None, None, None))
        result = calculate_context(ContextInput(target, None))
        self.assertTrue(all(f.reasons == ('UNSUPPORTED_PROFILE', 'REGULATION_UNVERIFIED', 'SOURCE_UNAVAILABLE')
                            for f in result.features))

    def test_supplied_known_at_and_target_validation(self):
        inp = request((fixture(1),))
        with self.assertRaisesRegex(ValueError, 'FUTURE_KNOWN_AT'):
            normalize_history(replace(inp, current=replace(inp.current, source=replace(SOURCE, known_at=T + timedelta(microseconds=1)))))
        with self.assertRaisesRegex(ValueError, 'PROVIDER'):
            normalize_history(request((fixture(1, provider='OTHER'),)))
        for changes in ({'cutoff': TARGET.kickoff}, {'status': '1H'}, {'home_team_id': 2},
                        {'home_team_id': True}, {'kickoff': T.replace(tzinfo=None)}):
            with self.assertRaises(ValueError):
                replace(TARGET, **changes)
        unobserved = replace(inp, current=replace(inp.current, source=replace(SOURCE, known_at=T - timedelta(days=2))))
        self.assertFalse(normalize_history(unobserved).games)


class SerializationAndInvariants(unittest.TestCase):
    def test_T11_canonical_bytes_and_hash_literal(self):
        doc = {'é': 'e\u0301', 'time': T.astimezone(timezone(timedelta(hours=3))),
               'z': D('-0.0000'), 'decimal': D('1.230000'), 'missing': None, 'flag': True}
        expected = '{"decimal":"1.23","flag":true,"missing":null,"time":"2026-09-23T12:00:00.123456Z","z":"0","é":"é"}'.encode()
        self.assertEqual(canonical_bytes(doc), expected)
        self.assertEqual(fingerprint('FC_SNAPSHOT_V1', doc), hashlib.sha256(b'FC_SNAPSHOT_V1\n' + expected).hexdigest())
        self.assertEqual(fingerprint('FC_SNAPSHOT_V1', doc), 'd6cd07468eb48663d4218ab0a407ec433f553137629e796ec6ec676ce73efecb')
        self.assertEqual(canonical_bytes({'a': D('1E+3')}), b'{"a":"1000"}')
        with self.assertRaises(ValueError):
            canonical_bytes({'é': 1, 'e\u0301': 2})
        for value in (1.2, float('nan'), D('NaN'), D('Infinity'), D('-Infinity'), object()):
            with self.assertRaises(ValueError):
                canonical_bytes(value)

    def test_T11_final_rounding_negative_zero_and_ranges(self):
        self.assertEqual(feature_text(D('-0'), 0), '0.000000')
        self.assertEqual(feature_text(D('-0.0000001'), 6), '0.000000')
        self.assertEqual(feature_text(D('1.2345665'), 0), '1.234566')
        self.assertEqual(feature_text(D('1.2345675'), 0), '1.234568')
        for value, index in ((D('-0.1'), 0), (D('30.000001'), 0), (D('1.1'), 4),
                             (D('79.200001'), 6), (D('-79.200001'), 6), (D('NaN'), 0), (D('Infinity'), 0)):
            with self.assertRaisesRegex(ValueError, 'INVARIANT'):
                feature_text(value, index)
        self.assertEqual(feature_text(D('-79.2'), 6), '-79.200000')
        self.assertEqual(feature_text(D('79.2'), 6), '79.200000')

    def test_manifest_golden_and_sensitivity(self):
        manifest = semantic_manifest()
        self.assertEqual(semantic_fingerprint(), 'f6b27feb0a0352f02390f392cfeea9e200039ad163dad7f764567cc4efe8276a')
        self.assertEqual(manifest['contract'], CONTRACT)
        self.assertEqual(tuple(f['name'] for f in manifest['features']), FEATURE_NAMES)
        for key, change in (('contract', 'V_NEXT'), ('features', tuple(reversed(manifest['features']))),
                            ('profile_policy', 'NEXT'), ('arithmetic', 'NEXT'), ('rates', {'min_N': 4}),
                            ('serialization', {'ensure_ascii': True}), ('pi', {'support_total': 9})):
            with self.subTest(key=key):
                self.assertNotEqual(fingerprint('FC_SEMANTICS_V1', manifest | {key: change}), semantic_fingerprint())
        manifest['profiles']['UNKNOWN'] = (365, 120)
        self.assertIsNone(semantic_manifest()['profiles']['UNKNOWN'])

    def test_T11_result_hash_sensitivity_and_timezone_equivalence(self):
        inp = request(tuple(fixture(i, days=i) for i in range(1, 9)))
        base = calculate_context(inp)
        digest = result_fingerprint(base)
        changes = (
            replace(inp, target=replace(TARGET, cutoff=T + timedelta(microseconds=1))),
            replace(inp, current=replace(inp.current, source=replace(SOURCE, identity='other'))),
            replace(inp, current=replace(inp.current, source=replace(SOURCE, payload_hash='d' * 64))),
            replace(inp, target=replace(TARGET, fixture_id=10000)),
        )
        for changed in changes:
            self.assertNotEqual(result_fingerprint(calculate_context(changed)), digest)
        zone = timezone(timedelta(hours=-4))
        zoned = replace(inp, target=replace(TARGET, cutoff=T.astimezone(zone), kickoff=TARGET.kickoff.astimezone(zone)),
                        current=replace(inp.current, rows=tuple(replace(r, kickoff=r.kickoff.astimezone(zone)) for r in inp.current.rows)))
        self.assertEqual(result_fingerprint(calculate_context(zoned)), digest)
        for changed in (replace(base, contract='NEXT'), replace(base, features=tuple(reversed(base.features))),
                        replace(base, features=(replace(base.features[0], value='2.000000'), *base.features[1:])),
                        replace(base, features=(replace(base.features[0], status=Status.MISSING, value=None, reasons=('SOURCE_UNAVAILABLE',)), *base.features[1:]))):
            self.assertNotEqual(result_fingerprint(changed), digest)
        # Strict dataclass constructors have no operational receipt/surrogate fields.
        with self.assertRaises(TypeError):
            replace(inp, receipt_id=5)

    def test_unicode_identity_equivalence_before_scope_matching(self):
        classification = replace(CLASSIFICATION, team_category='Clu\u0301b')
        composed = replace(classification, team_category='Clúb')
        rows = tuple(fixture(i, entity_scope=('MEN', 'SENIOR', 'Clu\u0301b')) for i in range(1, 4))
        left = request(rows, target=replace(TARGET, classification=classification))
        right = request(tuple(replace(r, entity_scope=('MEN', 'SENIOR', 'Clúb')) for r in rows),
                        target=replace(TARGET, classification=composed))
        self.assertEqual(calculate_context(left).features[0].status, Status.AVAILABLE)
        self.assertEqual(result_fingerprint(calculate_context(left)), result_fingerprint(calculate_context(right)))

    def test_ambient_decimal_context_cannot_change_outputs(self):
        inp = request(tuple(fixture(i, days=i * 9, gf=i % 4, ga=i % 3) for i in range(1, 10)))
        expected = result_fingerprint(calculate_context(inp))
        with localcontext() as ctx:
            ctx.prec = 5
            ctx.rounding = ROUND_DOWN
            ctx.traps[Inexact] = True
            self.assertEqual(result_fingerprint(calculate_context(inp)), expected)
        self.assertEqual(exact_days(T, T - timedelta(microseconds=1)), D('1.157407407407407407407407407E-11'))

    def test_cutoff_equality_requires_supplied_capture_order_proof(self):
        inp = request(tuple(fixture(i) for i in range(1, 4)))
        source = replace(SOURCE, known_at=T)
        with self.assertRaisesRegex(ValueError, 'CAPTURE_ORDER_UNPROVEN'):
            normalize_history(replace(inp, current=replace(inp.current, source=source)))
        proven = replace(source, available_before_capture=True)
        result = calculate_context(replace(inp, current=replace(inp.current, source=proven)))
        self.assertEqual(result.features[0].status, Status.AVAILABLE)
        with self.assertRaisesRegex(ValueError, 'CUTOFF'):
            replace(TARGET, source=source)
        self.assertEqual(replace(TARGET, source=proven).source, proven)

    def test_typed_input_and_result_contract_failures(self):
        for score in (True, '1', 1.0, float('nan'), []):
            with self.assertRaisesRegex(ValueError, 'SCORE_TYPE'):
                fixture(1, fulltime_home=score)
        for team in (True, '1', 1.0, []):
            with self.assertRaisesRegex(ValueError, 'IDENTITY_TYPE'):
                fixture(1, home=team)
        f = calculate_context(request(tuple(fixture(i) for i in range(1, 4)))).features[0]
        for changes in ({'value': None}, {'value': '-0.000000'}, {'value': 'NaN'}, {'value': '1'},
                        {'status': Status.MISSING}, {'reasons': ('UNSUPPORTED_PI_STATE', 'INSUFFICIENT_SAMPLE')},
                        {'sample_count': -1}, {'sample_count': None}):
            with self.assertRaises(ValueError):
                replace(f, **changes)
        with self.assertRaises(ValueError):
            ContextInput(TARGET, {})

    def test_form_cutoff_binding_and_difference_invariant(self):
        pool, home, away, state = sample_state(tuple(fixture(i) for i in range(1, 9)))
        with self.assertRaisesRegex(ValueError, 'BINDING'):
            current_pi_form(home, replace(state, cutoff=T - timedelta(microseconds=1)), home=True)
        huge = replace(state, ratings=(rating(1, value='80'), rating(2)))
        with self.assertRaisesRegex(ValueError, 'INVARIANT'):
            pi_difference(pool, huge, home, away)

    def test_bounded_two_season_replay_maximum(self):
        rows = tuple(fixture(i, days=i) for i in range(1, 100))
        previous = History(2025, replace(SOURCE, identity='previous'), FORMAT,
                           tuple(fixture(i, days=i, season=2025) for i in range(100, 199)))
        result = calculate_context(request(rows, previous=previous))
        self.assertEqual(len(result.pi_state.updates), 198)
        self.assertEqual(result.pi_state.rating(1).total, 198)
        self.assertEqual(result.features[0].sample_count, 8)
        self.assertEqual(result.features[6].status, Status.AVAILABLE)

    def test_immutable_inputs_and_contract_rejections(self):
        with self.assertRaises(FrozenInstanceError):
            TARGET.season = 2027
        with self.assertRaises(ValueError):
            History(2026, SOURCE, FORMAT, [fixture(1)])
        with self.assertRaises(ValueError):
            replace(SOURCE, payload_hash='not-a-hash')
        with self.assertRaises(TypeError):
            replace(TARGET, undeclared=1)
        with self.assertRaises(ValueError):
            replace(CLASSIFICATION, flags=['mutable'])

    def test_deterministic_lightweight_invariants(self):
        rng = random.Random(32)
        for _ in range(12):
            rows = tuple(fixture(i, days=rng.randint(1, 350), home=1 if i % 2 else 2,
                                 away=2 if i % 2 else 1, gf=rng.randint(0, 30), ga=rng.randint(0, 30))
                         for i in range(1, 45))
            result = calculate_context(request(rows))
            for i, f in enumerate(result.features):
                if f.value is not None:
                    low, high = (D(0), D(30)) if i < 4 else (D(0), D(1)) if i < 6 else (D('-79.2'), D('79.2'))
                    self.assertTrue(low <= D(f.value) <= high)
                if f.sample is not None:
                    self.assertLessEqual(len(f.sample.games), 8)
                    self.assertTrue(all(g.fixture_id != TARGET.fixture_id and g.kickoff < T for g in f.sample.games))
            self.assertEqual(result_fingerprint(calculate_context(request(tuple(reversed(rows))))), result_fingerprint(result))

    def test_noninteger_age_weight_golden(self):
        rows = (fixture(1), fixture(2, kickoff=T - timedelta(days=2, microseconds=123)), fixture(3, days=7))
        sample = calculate_context(request(rows)).features[0].sample
        with localcontext(decimal_context()):
            age = D(86400000123) / D(86400000000)
            expected = ((-age / D(120)) * D(2).ln()).exp()
        self.assertEqual(sample.games[1].weight, expected)
        self.assertEqual(str(expected), '0.9942404238093715909803908831')

    def test_T32_imports_and_calculations_inert(self):
        package = Path(__file__).resolve().parents[1] / 'app' / 'prematch_football_context'
        forbidden = {'os', 'socket', 'sqlite3', 'requests', 'httpx', 'telegram', 'pathlib', 'subprocess'}
        for path in package.glob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name.split('.')[0] in forbidden for alias in node.names))
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], forbidden)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, ('now', 'utcnow', 'today', 'getenv'))
        script = '''
import socket, sqlite3, os, sys
from unittest.mock import patch

def audit(event, args):
    if event.startswith(("socket.connect", "socket.getaddrinfo", "sqlite3.connect")):
        raise AssertionError("I/O attempted")
    if event == "open" and (args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
        raise AssertionError("filesystem mutation attempted")
sys.addaudithook(audit)

def fail(*a, **kw):
    raise AssertionError("forbidden side effect")
with patch.object(socket, "socket", fail), patch.object(sqlite3, "connect", fail), patch.object(os, "getenv", fail):
    import app.prematch_football_context
    from tests.test_prematch_football_context import request, fixture
    result = app.prematch_football_context.calculate_context(request(tuple(fixture(i) for i in range(1, 9))))
    print(app.prematch_football_context.result_fingerprint(result))
assert not any(n.startswith(("app.lab_v2_shadow", "app.adaptive_lab", "app.live_lab", "telegram")) for n in sys.modules)
'''
        completed = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, check=True)
        expected = calculate_context(request(tuple(fixture(i) for i in range(1, 9))))
        self.assertEqual(completed.stdout.strip(), result_fingerprint(expected))


if __name__ == '__main__':
    unittest.main()
