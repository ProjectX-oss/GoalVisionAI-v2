import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from app.explanations import PredictionExplanation
from app.interactions import (
    CallbackCodec,
    InMemoryAssessmentExplanationRepository,
    InteractionAction,
    InteractionButtonFactory,
    InteractionStatus,
    StoredAssessmentExplanation,
    TelegramPredictionInteractionHandler,
)
from app.presentation import (
    DEFAULT_PRESENTATION_CONFIG,
    DetailedExplanationMessage,
    PredictionPresentationData,
    TelegramPredictionPresenter,
)


class CountingLookup(InMemoryAssessmentExplanationRepository):
    def __init__(self) -> None:
        super().__init__()
        self.get_calls = 0

    def get(self, assessment_id: str) -> StoredAssessmentExplanation | None:
        self.get_calls += 1
        return super().get(assessment_id)


class PredictionInteractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 13, 12, tzinfo=timezone.utc)
        self.explanation = PredictionExplanation(
            short_summary="Home <edge> is supported & verified.",
            positive_factors=("Home attack is stronger than away attack.",),
            risk_factors=("Recent form signals conflict.",),
            missing_data=(),
            reason_codes=("ATTACK_HOME_ADVANTAGE",),
            supporting_metrics=(),
        )
        self.codec = CallbackCodec()
        self.buttons = InteractionButtonFactory(self.codec)
        self.repository = InMemoryAssessmentExplanationRepository()
        self.presenter = TelegramPredictionPresenter(
            DEFAULT_PRESENTATION_CONFIG
        )

    def store(
        self,
        assessment_id: str = "fixture_123",
        explanation: PredictionExplanation | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        self.repository.save(
            StoredAssessmentExplanation(
                assessment_id=assessment_id,
                explanation=(
                    self.explanation if explanation is None else explanation
                ),
                expires_at=expires_at or self.now + timedelta(hours=1),
            )
        )

    def handler(self) -> TelegramPredictionInteractionHandler:
        return TelegramPredictionInteractionHandler(
            lookup=self.repository,
            presenter=self.presenter,
            callback_codec=self.codec,
            clock=lambda: self.now,
        )

    def test_valid_why_this_pick_callback_returns_stored_explanation(self):
        self.store()
        action = self.buttons.why_this_pick("fixture_123")

        response = self.handler().handle(action.callback_data)

        self.assertEqual(response.status, InteractionStatus.OK)
        self.assertEqual(response.parse_mode, "HTML")
        self.assertIn("<b>Why this pick?</b>", response.text)
        self.assertIn("Home attack is stronger", response.text)

    def test_compact_presentation_accepts_typed_why_action(self):
        action = self.buttons.why_this_pick("fixture_123")
        data = PredictionPresentationData(
            league="Premier League",
            home_team="Home",
            away_team="Away",
            market="Match Winner",
            pick="Home",
            probability=61.0,
            confidence="HIGH",
            explanation=self.explanation,
            odds=1.80,
            quality_score=90,
        )

        message = self.presenter.compact(data, action)

        self.assertEqual(message.inline_actions, (action,))
        self.assertNotIn("AI Quality", message.text)

    def test_malformed_callback_is_rejected_safely(self):
        response = self.handler().handle("why:<raw explanation>")

        self.assertEqual(response.status, InteractionStatus.MALFORMED)

    def test_unknown_assessment_is_reported(self):
        callback = self.codec.encode(
            InteractionAction.WHY_THIS_PICK,
            "unknown",
        )

        response = self.handler().handle(callback)

        self.assertEqual(response.status, InteractionStatus.UNKNOWN)

    def test_expired_assessment_is_reported(self):
        self.store(expires_at=self.now - timedelta(seconds=1))

        response = self.handler().handle(
            self.buttons.why_this_pick("fixture_123").callback_data
        )

        self.assertEqual(response.status, InteractionStatus.EXPIRED)

    def test_missing_explanation_is_reported(self):
        self.repository.save(
            StoredAssessmentExplanation(
                assessment_id="fixture_123",
                explanation=None,
                expires_at=self.now + timedelta(hours=1),
            )
        )

        response = self.handler().handle(
            self.buttons.why_this_pick("fixture_123").callback_data
        )

        self.assertEqual(
            response.status,
            InteractionStatus.MISSING_EXPLANATION,
        )

    def test_callback_identifiers_are_deterministic_and_action_specific(self):
        first = self.buttons.why_this_pick("fixture_123").callback_data
        second = self.buttons.why_this_pick("fixture_123").callback_data
        statistics = self.buttons.view_statistics(
            "fixture_123"
        ).callback_data

        self.assertEqual(first, second)
        self.assertNotEqual(first, statistics)
        self.assertNotIn(self.explanation.short_summary, first)

    def test_callback_identifiers_stay_within_telegram_limit(self):
        callback = self.codec.encode(
            InteractionAction.WHY_THIS_PICK,
            "a" * self.codec.MAX_ASSESSMENT_ID_LENGTH,
        )

        self.assertLessEqual(
            len(callback.encode("utf-8")),
            self.codec.MAX_CALLBACK_BYTES,
        )
        with self.assertRaises(ValueError):
            self.codec.encode(
                InteractionAction.WHY_THIS_PICK,
                "a" * (self.codec.MAX_ASSESSMENT_ID_LENGTH + 1),
            )

    def test_explanation_response_is_html_safe(self):
        self.store()

        response = self.handler().handle(
            self.buttons.why_this_pick("fixture_123").callback_data
        )

        self.assertIn("Home &lt;edge&gt; is supported &amp; verified.", response.text)
        self.assertNotIn("<edge>", response.text)

    def test_duplicate_callback_reuses_formatted_response(self):
        lookup = CountingLookup()
        lookup.save(
            StoredAssessmentExplanation(
                assessment_id="fixture_123",
                explanation=self.explanation,
                expires_at=self.now + timedelta(hours=1),
            )
        )
        presenter = Mock(spec=TelegramPredictionPresenter)
        presenter.detailed_explanation.return_value = DetailedExplanationMessage(
            text="stored explanation"
        )
        handler = TelegramPredictionInteractionHandler(
            lookup=lookup,
            presenter=presenter,
            callback_codec=self.codec,
            clock=lambda: self.now,
        )
        callback = self.buttons.why_this_pick("fixture_123").callback_data

        first = handler.handle(callback)
        duplicate = handler.handle(callback)

        self.assertFalse(first.duplicate)
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(first.text, duplicate.text)
        self.assertEqual(lookup.get_calls, 1)
        presenter.detailed_explanation.assert_called_once_with(self.explanation)

    def test_cached_response_is_not_returned_after_expiry(self):
        current_time = [self.now]
        self.repository.save(
            StoredAssessmentExplanation(
                assessment_id="fixture_123",
                explanation=self.explanation,
                expires_at=self.now + timedelta(minutes=1),
            )
        )
        handler = TelegramPredictionInteractionHandler(
            lookup=self.repository,
            presenter=self.presenter,
            callback_codec=self.codec,
            clock=lambda: current_time[0],
        )
        callback = self.buttons.why_this_pick("fixture_123").callback_data
        self.assertEqual(handler.handle(callback).status, InteractionStatus.OK)

        current_time[0] = self.now + timedelta(minutes=2)
        response = handler.handle(callback)

        self.assertEqual(response.status, InteractionStatus.EXPIRED)
        self.assertFalse(response.duplicate)

    def test_future_actions_are_safe_placeholders_without_lookup(self):
        lookup = CountingLookup()
        handler = TelegramPredictionInteractionHandler(
            lookup=lookup,
            presenter=self.presenter,
            callback_codec=self.codec,
            clock=lambda: self.now,
        )

        for action in (
            self.buttons.view_statistics("fixture_123"),
            self.buttons.view_bankroll("fixture_123"),
        ):
            self.assertEqual(
                handler.handle(action.callback_data).status,
                InteractionStatus.PLACEHOLDER,
            )
        self.assertEqual(lookup.get_calls, 0)

    def test_interactions_do_not_call_telegram_or_network(self):
        self.store()

        with patch("telegram.Bot.send_message") as send_message:
            self.handler().handle(
                self.buttons.why_this_pick("fixture_123").callback_data
            )

        send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
