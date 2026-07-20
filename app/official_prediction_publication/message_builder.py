import hashlib
import json
import re
from datetime import timezone
from decimal import Decimal, ROUND_DOWN
from html import escape

from app.quality_gate import QualityGateStatus
from app.risk_management import RiskProductScope

from .config import OfficialPredictionMessagePolicy
from .exceptions import OfficialPredictionPublicationValidationError
from .mapping import OfficialMarketPresentationMapper, OfficialStakeRatingMapper
from .models import (
    OfficialPredictionMessageInput,
    OfficialPredictionPublicationPayload,
)


_FORBIDDEN_REASONING = (
    "guaranteed",
    "guarantee",
    "certain win",
    "risk-free",
    "risk free",
    "sure bet",
    "sure winner",
    "cannot lose",
    "certain",
    "certainty",
    "100%",
    "no risk",
    "affiliate",
    "promo code",
    "bookmaker partner",
    "raw probability",
    "expected value threshold",
    "ev threshold",
    "stake percentage",
    "bankroll calculation",
    "exposure value",
    "brier",
    "log loss",
    "calibration error",
    "quality gate",
    "audit id",
    "repository id",
    "model health",
)
_SCORE_PATTERN = re.compile(r"\b\d+\s*[-:]\s*\d+\b")
_URL_PATTERN = re.compile(r"(?:https?://|www\.|t\.me/)", re.IGNORECASE)


class OfficialPredictionMessageBuilder:
    """Builds one canonical Telegram-safe Official prediction payload."""

    FINGERPRINT_VERSION = "official-prediction-message-fingerprint-v1"

    def __init__(
        self,
        policy: OfficialPredictionMessagePolicy,
        stakes: OfficialStakeRatingMapper | None = None,
        markets: OfficialMarketPresentationMapper | None = None,
    ) -> None:
        self.policy = policy
        self._stakes = stakes or OfficialStakeRatingMapper(policy.stake_rating)
        self._markets = markets or OfficialMarketPresentationMapper()

    def build(
        self,
        value: OfficialPredictionMessageInput,
    ) -> OfficialPredictionPublicationPayload:
        approved = value.approved
        assembly = approved.assembly
        candidate = assembly.gate_candidate
        facts = value.facts
        destination = value.destination
        self._validate_identity(value)
        calibrated = candidate.calibrated_probability
        if (
            not isinstance(calibrated, Decimal)
            or not calibrated.is_finite()
            or not Decimal("0") < calibrated < Decimal("1")
        ):
            raise OfficialPredictionPublicationValidationError(
                "Calibrated probability is required for public presentation."
            )
        if (
            not isinstance(candidate.decimal_odds, Decimal)
            or not candidate.decimal_odds.is_finite()
            or candidate.decimal_odds < self.policy.minimum_odds
        ):
            raise OfficialPredictionPublicationValidationError(
                "Approved odds are below the Official publication minimum."
            )
        stake = self._stakes.map(
            facts.stake_recommendation,
            facts.risk_decision,
        )
        selection = self._markets.format(
            candidate.market,
            candidate.selection,
            candidate.market_line,
            facts.home_team,
            facts.away_team,
        )
        reasoning = self._reasoning(facts.reasoning.ordered_facts)
        note = self._note(facts.reasoning.data_status_note)
        probability = self._probability_text(calibrated)
        odds = self._odds_text(candidate.decimal_odds)
        kickoff = candidate.kickoff_timestamp.astimezone(timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
        confidence = candidate.confidence.value.title()
        lines = [
            "<b>⚽ GoalVision AI — Official Prediction</b>",
            "",
            f"🏆 {escape(facts.competition)}",
            f"{escape(facts.home_team)} vs {escape(facts.away_team)}",
            f"🕒 {kickoff}",
            "",
            f"📊 Prediction: <b>{escape(selection)}</b>",
            f"📈 Odds: <b>{odds}</b>",
            f"🎯 Model probability: <b>{probability}%</b>",
            f"⭐ Stake: {stake.rendered}",
            f"🔒 Confidence: {escape(confidence)}",
            "",
            "🧠 <b>Why:</b>",
            *[f"• {item}" for item in reasoning],
        ]
        if note is not None:
            lines.extend(("", f"⚠️ {note}"))
        lines.extend(("", "⚠️ Betting involves risk. Bet responsibly."))
        rendered = "\n".join(lines)
        if _telegram_length(rendered) > self.policy.maximum_message_length:
            raise OfficialPredictionPublicationValidationError(
                "Rendered Official message exceeds the configured length limit."
            )
        values = {
            "prediction_id": candidate.prediction_id,
            "match_id": assembly.match_id,
            "orchestration_id": approved.orchestration_id,
            "gate_evaluation_id": approved.quality_gate_evaluation.evaluation_id,
            "candidate_fingerprint": approved.candidate_fingerprint,
            "destination_scope": destination.product_scope.value,
            "rendered_text": rendered,
            "parse_mode": self.policy.parse_mode,
            "approved_odds": _decimal_text(candidate.decimal_odds),
            "calibrated_probability": _decimal_text(calibrated),
            "public_confidence": candidate.confidence.value,
            "public_stake_rating": str(stake.stars),
            "model_version": candidate.model_version,
            "policy_version": approved.quality_gate_evaluation.policy_version,
            "message_policy_version": self.policy.version,
            "created_timestamp": approved.evaluated_at.astimezone(
                timezone.utc
            ).isoformat(),
        }
        message_fingerprint = self.fingerprint(values)
        return OfficialPredictionPublicationPayload(
            prediction_id=candidate.prediction_id,
            match_id=assembly.match_id,
            orchestration_id=approved.orchestration_id,
            gate_evaluation_id=approved.quality_gate_evaluation.evaluation_id,
            candidate_fingerprint=approved.candidate_fingerprint,
            message_fingerprint=message_fingerprint,
            destination_scope=destination.product_scope,
            rendered_text=rendered,
            parse_mode=self.policy.parse_mode,
            approved_odds=candidate.decimal_odds,
            calibrated_probability=calibrated,
            public_confidence=candidate.confidence.value,
            public_stake_rating=stake,
            created_timestamp=approved.evaluated_at,
            model_version=candidate.model_version,
            policy_version=approved.quality_gate_evaluation.policy_version,
        )

    def fingerprint(self, values: dict[str, str]) -> str:
        payload = json.dumps(
            {
                "version": self.FINGERPRINT_VERSION,
                "public_content": tuple(sorted(values.items())),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _validate_identity(self, value: OfficialPredictionMessageInput) -> None:
        approved = value.approved
        assembly = approved.assembly
        candidate = assembly.gate_candidate
        facts = value.facts
        gate = approved.quality_gate_evaluation
        if (
            approved.dry_run
            or approved.approval_status is not QualityGateStatus.APPROVED
            or gate.final_decision is not QualityGateStatus.APPROVED
        ):
            raise OfficialPredictionPublicationValidationError(
                "Only a final non-dry-run Official approval may be rendered."
            )
        identities = (
            facts.prediction_id == candidate.prediction_id == gate.prediction_id,
            facts.match_id == assembly.match_id,
            facts.orchestration_id == approved.orchestration_id,
            facts.gate_evaluation_id == gate.evaluation_id,
            facts.candidate_fingerprint == approved.candidate_fingerprint,
            facts.model_version == candidate.model_version == gate.model_version,
            facts.policy_version == gate.policy_version,
        )
        if not all(identities):
            raise OfficialPredictionPublicationValidationError(
                "Public message facts do not match persisted approval identity."
            )
        if (
            facts.bankroll_scope is not RiskProductScope.OFFICIAL
            or value.destination.product_scope is not RiskProductScope.OFFICIAL
        ):
            raise OfficialPredictionPublicationValidationError(
                "Official publication cannot use a non-Official scope."
            )
        if any(
            not item.strip()
            for item in (facts.competition, facts.home_team, facts.away_team)
        ):
            raise OfficialPredictionPublicationValidationError(
                "Competition and team names are required."
            )
        if any(
            _URL_PATTERN.search(item) or any(mark in item for mark in "\r\n\t")
            for item in (facts.competition, facts.home_team, facts.away_team)
        ):
            raise OfficialPredictionPublicationValidationError(
                "Competition and team names contain unsafe public text."
            )
        if any(
            item.tzinfo is None or item.utcoffset() is None
            for item in (approved.evaluated_at, candidate.kickoff_timestamp)
        ):
            raise OfficialPredictionPublicationValidationError(
                "Approval and kickoff timestamps must be timezone-aware."
            )

    def _reasoning(self, values: tuple[str, ...]) -> tuple[str, ...]:
        if self.policy.reasoning_required and not values:
            raise OfficialPredictionPublicationValidationError(
                "Approved public reasoning is required."
            )
        if len(values) > self.policy.maximum_reasoning_facts:
            raise OfficialPredictionPublicationValidationError(
                "Approved public reasoning exceeds the configured fact limit."
            )
        selected = values
        if any(not item.strip() for item in selected):
            raise OfficialPredictionPublicationValidationError(
                "Reasoning facts must not be empty."
            )
        joined = " ".join(selected)
        lowered = joined.casefold()
        if (
            _telegram_length(joined) > self.policy.maximum_reasoning_length
            or any(term in lowered for term in _FORBIDDEN_REASONING)
            or _SCORE_PATTERN.search(joined)
            or _URL_PATTERN.search(joined)
        ):
            raise OfficialPredictionPublicationValidationError(
                "Reasoning is unsafe or exceeds the configured public limit."
            )
        return tuple(escape(item.strip()) for item in selected)

    def _note(self, value: str | None) -> str | None:
        if value is None:
            return None
        if (
            not value.strip()
            or _telegram_length(value) > self.policy.maximum_reasoning_length
        ):
            raise OfficialPredictionPublicationValidationError(
                "Public data-status note is malformed."
            )
        lowered = value.casefold()
        if (
            any(term in lowered for term in _FORBIDDEN_REASONING)
            or _SCORE_PATTERN.search(value)
            or _URL_PATTERN.search(value)
        ):
            raise OfficialPredictionPublicationValidationError(
                "Public data-status note contains unsafe wording."
            )
        return escape(value.strip())

    @staticmethod
    def _probability_text(value: Decimal) -> str:
        return format((value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_DOWN), "f")

    @staticmethod
    def _odds_text(value: Decimal) -> str:
        normalized = _decimal_text(value)
        if "." not in normalized:
            return f"{normalized}.00"
        whole, fraction = normalized.split(".", 1)
        return f"{whole}.{fraction.ljust(2, '0')}"


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _telegram_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2
