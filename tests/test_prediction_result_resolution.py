import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.results import (
    DEFAULT_FIXTURE_STATUS_POLICY,
    DEFAULT_MARKET_SETTLEMENT_REGISTRY,
    FinishedMatchResult,
    FixtureStatusPolicy,
    InMemoryPredictionResultRepository,
    NonPlayableFixturePolicy,
    PredictionResultResolutionService,
    PredictionResultResolver,
    PublishedPredictionReference,
    ResolutionStatus,
    SettlementReasonCode,
)


class PredictionResultResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 13, 20, tzinfo=timezone.utc)
        self.prediction = PublishedPredictionReference(
            prediction_id="prediction-1",
            fixture_id=500,
            market="Match Winner",
            selection="HOME",
            published_at=datetime(2026, 7, 12, 12, tzinfo=timezone.utc),
        )
        self.repository = InMemoryPredictionResultRepository(
            (self.prediction,)
        )
        self.resolver = PredictionResultResolver(
            status_policy=DEFAULT_FIXTURE_STATUS_POLICY,
            market_registry=DEFAULT_MARKET_SETTLEMENT_REGISTRY,
        )
        self.service = PredictionResultResolutionService(
            resolver=self.resolver,
            repository=self.repository,
            clock=lambda: self.now,
        )

    def prediction_for(self, selection: str, market: str = "Match Winner"):
        return PublishedPredictionReference(
            prediction_id=f"prediction-{selection}-{market}",
            fixture_id=500,
            market=market,
            selection=selection,
            published_at=self.prediction.published_at,
        )

    @staticmethod
    def match(
        home_score: int | None,
        away_score: int | None,
        status: str = "FT",
    ) -> FinishedMatchResult:
        return FinishedMatchResult(
            fixture_id=500,
            status=status,
            home_score=home_score,
            away_score=away_score,
        )

    def resolve(
        self,
        prediction: PublishedPredictionReference,
        match: FinishedMatchResult | None,
    ):
        repository = InMemoryPredictionResultRepository((prediction,))
        service = PredictionResultResolutionService(
            resolver=self.resolver,
            repository=repository,
            clock=lambda: self.now,
        )
        return service.resolve_one(prediction, match)

    def test_home_pick_won(self):
        result = self.service.resolve_one(
            self.prediction,
            self.match(2, 1),
        )

        self.assertEqual(result.status, ResolutionStatus.WON)
        self.assertEqual(result.fixture_id, 500)
        self.assertEqual(result.prediction_id, "prediction-1")
        self.assertEqual(result.resolved_at, self.now)
        self.assertEqual((result.home_score, result.away_score), (2, 1))
        self.assertEqual(result.settlement_rule_version, "match-winner-v1")
        self.assertEqual(
            result.reason_codes,
            (SettlementReasonCode.MATCH_RESULT_SETTLED,),
        )

    def test_home_pick_lost(self):
        result = self.service.resolve_one(
            self.prediction,
            self.match(0, 1),
        )

        self.assertEqual(result.status, ResolutionStatus.LOST)

    def test_away_pick_won(self):
        prediction = self.prediction_for("AWAY")

        result = self.resolve(prediction, self.match(1, 3))

        self.assertEqual(result.status, ResolutionStatus.WON)

    def test_draw_pick_won(self):
        prediction = self.prediction_for("DRAW")

        result = self.resolve(prediction, self.match(2, 2))

        self.assertEqual(result.status, ResolutionStatus.WON)

    def test_pending_match_is_not_stored(self):
        result = self.service.resolve_one(
            self.prediction,
            self.match(None, None, "NS"),
        )

        self.assertEqual(result.status, ResolutionStatus.PENDING)
        self.assertIsNone(result.resolved_at)
        self.assertIsNone(self.repository.get_resolved("prediction-1"))
        self.assertEqual(self.repository.load_pending(), (self.prediction,))

    def test_missing_score_is_never_inferred(self):
        result = self.service.resolve_one(
            self.prediction,
            self.match(2, None),
        )

        self.assertEqual(result.status, ResolutionStatus.UNRESOLVED)
        self.assertIn(
            SettlementReasonCode.FINAL_SCORE_MISSING,
            result.reason_codes,
        )
        self.assertIsNone(result.resolved_at)

    def test_extra_time_score_is_not_used_as_regulation_result(self):
        result = self.service.resolve_one(
            self.prediction,
            self.match(2, 1, "AET"),
        )

        self.assertEqual(result.status, ResolutionStatus.UNRESOLVED)
        self.assertEqual(
            result.reason_codes,
            (SettlementReasonCode.UNSUPPORTED_FIXTURE_STATUS,),
        )

    def test_unsupported_market_is_unresolved(self):
        prediction = self.prediction_for("YES", "BTTS")

        result = self.resolve(prediction, self.match(1, 1))

        self.assertEqual(result.status, ResolutionStatus.UNRESOLVED)
        self.assertEqual(
            result.reason_codes,
            (SettlementReasonCode.UNSUPPORTED_MARKET,),
        )

    def test_malformed_selection_is_unresolved(self):
        prediction = self.prediction_for("correct score 2-1")

        result = self.resolve(prediction, self.match(2, 1))

        self.assertEqual(result.status, ResolutionStatus.UNRESOLVED)
        self.assertEqual(
            result.reason_codes,
            (SettlementReasonCode.MALFORMED_PREDICTION,),
        )

    def test_cancelled_fixture_is_void_by_default_policy(self):
        result = self.service.resolve_one(
            self.prediction,
            self.match(None, None, "CANC"),
        )

        self.assertEqual(result.status, ResolutionStatus.VOID)
        self.assertEqual(result.resolved_at, self.now)
        self.assertEqual(
            result.reason_codes,
            (SettlementReasonCode.FIXTURE_CANCELLED,),
        )

    def test_postponed_and_abandoned_fixtures_follow_policy(self):
        postponed = self.service.resolve_one(
            self.prediction,
            self.match(None, None, "PST"),
        )
        other_prediction = self.prediction_for("AWAY")
        abandoned = self.resolve(
            other_prediction,
            self.match(1, 0, "ABD"),
        )

        self.assertEqual(postponed.status, ResolutionStatus.UNRESOLVED)
        self.assertEqual(abandoned.status, ResolutionStatus.VOID)

    def test_non_playable_policy_is_configurable(self):
        resolver = PredictionResultResolver(
            status_policy=FixtureStatusPolicy(
                non_playable=NonPlayableFixturePolicy(
                    cancelled=ResolutionStatus.UNRESOLVED,
                    postponed=ResolutionStatus.VOID,
                    abandoned=ResolutionStatus.UNRESOLVED,
                )
            ),
            market_registry=DEFAULT_MARKET_SETTLEMENT_REGISTRY,
        )
        service = PredictionResultResolutionService(
            resolver=resolver,
            repository=self.repository,
            clock=lambda: self.now,
        )

        result = service.resolve_one(
            self.prediction,
            self.match(None, None, "PST"),
        )

        self.assertEqual(result.status, ResolutionStatus.VOID)

    def test_duplicate_resolution_preserves_first_result(self):
        first = self.service.resolve_one(self.prediction, self.match(2, 0))

        duplicate = self.service.resolve_one(
            self.prediction,
            self.match(0, 3),
        )

        self.assertIs(duplicate, first)
        self.assertEqual(duplicate.status, ResolutionStatus.WON)
        self.assertEqual((duplicate.home_score, duplicate.away_score), (2, 0))
        self.assertEqual(self.repository.load_pending(), ())

    def test_output_is_deterministic(self):
        first = self.resolve(self.prediction, self.match(3, 1))
        second = self.resolve(self.prediction, self.match(3, 1))

        self.assertEqual(first, second)

    def test_resolve_pending_uses_injected_repository(self):
        results = self.service.resolve_pending({500: self.match(2, 1)})

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, ResolutionStatus.WON)

    def test_prediction_engine_is_never_called(self):
        with patch("app.prediction.engine.PredictionEngine.predict") as predict:
            result = self.service.resolve_one(
                self.prediction,
                self.match(2, 1),
            )

        self.assertEqual(result.status, ResolutionStatus.WON)
        predict.assert_not_called()

    def test_resolution_makes_no_network_or_telegram_calls(self):
        with (
            patch("telegram.Bot.send_message") as send_message,
            patch("httpx.AsyncClient.get") as http_get,
        ):
            result = self.service.resolve_one(
                self.prediction,
                self.match(2, 1),
            )

        self.assertEqual(result.status, ResolutionStatus.WON)
        send_message.assert_not_called()
        http_get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
