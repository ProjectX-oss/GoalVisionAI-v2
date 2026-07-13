import unittest
from unittest.mock import patch

from app.explanations import PredictionExplanation
from app.presentation import (
    DEFAULT_PRESENTATION_CONFIG,
    InlineActionMetadata,
    PredictionPresentationData,
    PresentationConfig,
    TelegramPredictionPresenter,
)


class PredictionPresentationTests(unittest.TestCase):

    def setUp(self) -> None:
        self.explanation = PredictionExplanation(
            short_summary="Home is supported by two data factors.",
            positive_factors=(
                "Home has the stronger recent-form rating.",
                "Home has the stronger attack rating.",
            ),
            risk_factors=(),
            missing_data=(),
            reason_codes=("DATA_COMPLETE", "FORM_HOME_ADVANTAGE"),
            supporting_metrics=(),
        )
        self.presenter = TelegramPredictionPresenter(
            DEFAULT_PRESENTATION_CONFIG
        )

    def data(self, **changes) -> PredictionPresentationData:
        values = {
            "league": "Premier League",
            "home_team": "Home",
            "away_team": "Away",
            "market": "Match Winner",
            "pick": "Home",
            "probability": 62.5,
            "confidence": "HIGH",
            "explanation": self.explanation,
            "odds": 1.85,
            "quality_score": 88,
        }
        values.update(changes)
        return PredictionPresentationData(**values)

    def test_compact_home_pick(self):
        message = self.presenter.compact(
            self.data(),
            InlineActionMetadata("Why this pick?", "why:1"),
        )

        self.assertIn("<b>GoalVision AI</b>", message.text)
        self.assertIn("Match Winner: <b>Home</b>", message.text)
        self.assertIn("Probability: 62.5%", message.text)
        self.assertEqual(message.parse_mode, "HTML")
        self.assertEqual(len(message.inline_actions), 1)
        self.assertLessEqual(len(message.text.splitlines()), 7)

    def test_compact_away_pick(self):
        message = self.presenter.compact(
            self.data(pick="Away", probability=57.0)
        )

        self.assertIn("Match Winner: <b>Away</b>", message.text)
        self.assertIn("Probability: 57.0%", message.text)

    def test_missing_odds_are_omitted(self):
        message = self.presenter.compact(self.data(odds=None))

        self.assertNotIn("Odds:", message.text)

    def test_quality_score_is_disabled_by_default(self):
        message = self.presenter.compact(self.data(quality_score=99))

        self.assertNotIn("AI Quality", message.text)

    def test_quality_score_can_be_enabled_explicitly(self):
        presenter = TelegramPredictionPresenter(
            PresentationConfig(show_quality_score=True)
        )

        message = presenter.compact(self.data(quality_score=88))

        self.assertIn("AI Quality: 88/100", message.text)

    def test_detailed_explanation_uses_positive_factors(self):
        message = self.presenter.detailed(self.data())

        self.assertIn("<b>Why this pick?</b>", message.text)
        self.assertIn("<b>Key factors</b>", message.text)
        self.assertIn(
            "Home has the stronger recent-form rating.",
            message.text,
        )

    def test_detailed_explanation_uses_risks_and_missing_data(self):
        explanation = PredictionExplanation(
            short_summary="Evidence is limited.",
            positive_factors=(),
            risk_factors=("Critical supporting data is missing.",),
            missing_data=("standings", "head-to-head history"),
            reason_codes=("DATA_PARTIAL", "CRITICAL_DATA_MISSING"),
            supporting_metrics=(),
        )

        message = self.presenter.detailed(self.data(explanation=explanation))

        self.assertIn("<b>Key risks</b>", message.text)
        self.assertIn("<b>Missing data</b>", message.text)
        self.assertIn("standings", message.text)

    def test_all_dynamic_text_is_html_escaped(self):
        explanation = PredictionExplanation(
            short_summary="Use <care> & verify.",
            positive_factors=("A < B & C",),
            risk_factors=("Risk > baseline",),
            missing_data=("<raw>",),
            reason_codes=("CRITICAL_DATA_MISSING",),
            supporting_metrics=(),
        )
        data = self.data(
            league="A&B <League>",
            home_team="Home <One>",
            away_team="Away & Two",
            market="Winner <90>",
            pick="Home & Draw",
            confidence="HIGH <test>",
            explanation=explanation,
        )

        compact = self.presenter.compact(data)
        detailed = self.presenter.detailed(data)

        self.assertIn("A&amp;B &lt;League&gt;", compact.text)
        self.assertIn("Home &lt;One&gt;", compact.text)
        self.assertIn("Home &amp; Draw", compact.text)
        self.assertIn("Use &lt;care&gt; &amp; verify.", detailed.text)
        self.assertNotIn("<care>", detailed.text)

    def test_formatting_is_deterministic(self):
        data = self.data()

        self.assertEqual(
            self.presenter.compact(data),
            self.presenter.compact(data),
        )
        self.assertEqual(
            self.presenter.detailed(data),
            self.presenter.detailed(data),
        )

    def test_formatters_do_not_call_telegram(self):
        with patch("telegram.Bot.send_message") as send_message:
            self.presenter.compact(self.data())
            self.presenter.detailed(self.data())

        send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
