import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TypeVar

from app.publication_quality_gate import (
    ConfidenceLevel,
    FactStatus,
    LineupStatus,
    MarketAvailability,
)
from app.risk_management import RiskProductScope

from .exceptions import (
    CandidateRegistrationValidationError,
    CandidateScopeValidationError,
)
from .fingerprint import (
    OfficialCandidateRegistryFingerprint,
    canonical_decimal,
    canonical_items,
    canonical_timestamp,
    reasoning_material,
)
from .models import (
    OfficialCandidateMarket,
    OfficialCandidateMarketIdentity,
    OfficialPredictionCandidateRegistrationCommand,
    OfficialPredictionReasoningFact,
    PreparedOfficialPredictionCandidate,
    ReasoningFactType,
)
from .policy import OfficialPredictionCandidateRegistryPolicy


_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._:/-]*$")
_URL = re.compile(r"(?:https?://|www\.|t\.me/|telegram\.me/)", re.IGNORECASE)
_HTML = re.compile(r"[<>]")
_AFFILIATE = re.compile(
    r"\b(?:affiliate|referral|promo(?:tional)?\s*code|bonus\s*code)\b",
    re.IGNORECASE,
)
_CREDENTIAL = re.compile(
    r"\b(?:bot\s*token|api\s*key|password|client\s*secret|bearer\s+token)\b",
    re.IGNORECASE,
)
_PROMOTIONAL = re.compile(
    r"\b(?:guaranteed|sure\s*win|risk[- ]?free|lock\s+of\s+the\s+day|"
    r"easy\s+money|100\s*%\s*(?:win|safe))\b",
    re.IGNORECASE,
)
_CORRECT_SCORE = re.compile(r"\b(?:correct|exact)\s+score\b", re.IGNORECASE)


_EnumT = TypeVar("_EnumT", bound=Enum)


class OfficialPredictionCandidateValidator:
    def __init__(
        self,
        policy: OfficialPredictionCandidateRegistryPolicy,
        fingerprints: OfficialCandidateRegistryFingerprint | None = None,
    ) -> None:
        self.policy = policy
        self._fingerprints = fingerprints or OfficialCandidateRegistryFingerprint()

    def prepare(
        self,
        command: OfficialPredictionCandidateRegistrationCommand,
    ) -> PreparedOfficialPredictionCandidate:
        self._scope(command)
        source_event_id = self._identifier(command.source_event_id, "SOURCE_EVENT_ID")
        prediction_id = self._identifier(command.prediction_id, "PREDICTION_ID")
        match_id = self._identifier(command.match_id, "MATCH_ID")
        competition_id = self._optional_identifier(
            command.competition_id,
            "COMPETITION_ID",
        )
        home_team_id = self._optional_identifier(command.home_team_id, "HOME_TEAM_ID")
        away_team_id = self._optional_identifier(command.away_team_id, "AWAY_TEAM_ID")
        odds_source_id = self._identifier(command.odds_source_id, "ODDS_SOURCE_ID")
        source_data_version = self._identifier(
            command.source_data_version,
            "SOURCE_DATA_VERSION",
        )
        model_version = self._model_version(command.model_version)
        competition_name = self._public_name(
            command.competition_name,
            "COMPETITION_NAME",
        )
        home_team_name = self._public_name(command.home_team_name, "HOME_TEAM_NAME")
        away_team_name = self._public_name(command.away_team_name, "AWAY_TEAM_NAME")
        normalized_competition = self._comparison(competition_name)
        normalized_home = self._comparison(home_team_name)
        normalized_away = self._comparison(away_team_name)
        if (
            home_team_id is not None
            and away_team_id is not None
            and home_team_id == away_team_id
        ) or normalized_home == normalized_away:
            self._invalid("IDENTICAL_TEAMS", "Home and away teams must be different.")

        registration = self._timestamp(
            command.registration_timestamp,
            "REGISTRATION_TIMESTAMP",
        )
        prediction_created = self._timestamp(
            command.prediction_creation_timestamp,
            "PREDICTION_CREATION_TIMESTAMP",
        )
        kickoff = self._timestamp(command.kickoff_timestamp, "KICKOFF_TIMESTAMP")
        odds_timestamp = self._timestamp(command.odds_timestamp, "ODDS_TIMESTAMP")
        core_timestamp = self._timestamp(
            command.core_match_data_timestamp,
            "CORE_DATA_TIMESTAMP",
        )
        if prediction_created >= kickoff:
            self._invalid(
                "PREDICTION_AT_OR_AFTER_KICKOFF",
                "Prediction creation must precede kickoff.",
            )
        if registration >= kickoff:
            self._invalid(
                "REGISTRATION_AT_OR_AFTER_KICKOFF",
                "Pre-match candidates must be registered before kickoff.",
            )
        for value, code, label in (
            (prediction_created, "FUTURE_PREDICTION_TIMESTAMP", "Prediction creation"),
            (odds_timestamp, "FUTURE_ODDS_TIMESTAMP", "Odds observation"),
            (core_timestamp, "FUTURE_CORE_DATA_TIMESTAMP", "Core match data"),
        ):
            if value > registration:
                self._invalid(code, f"{label} cannot be after registration.")

        lineup_status = self._enum(command.lineup_status, LineupStatus, "LINEUP_STATUS")
        lineup_timestamp = self._optional_timestamp(
            command.lineup_data_timestamp,
            "LINEUP_DATA_TIMESTAMP",
        )
        if lineup_status in {LineupStatus.CONFIRMED, LineupStatus.UNCONFIRMED}:
            if lineup_timestamp is None:
                self._invalid(
                    "LINEUP_TIMESTAMP_MISSING",
                    "Available lineup status requires its supplied timestamp.",
                )
        if lineup_timestamp is not None and lineup_timestamp > registration:
            self._invalid(
                "FUTURE_LINEUP_TIMESTAMP",
                "Lineup data cannot be after registration.",
            )

        injury_status = self._enum(
            command.injury_suspension_status,
            FactStatus,
            "INJURY_SUSPENSION_STATUS",
        )
        injury_timestamp = self._optional_timestamp(
            command.injury_suspension_data_timestamp,
            "INJURY_SUSPENSION_DATA_TIMESTAMP",
        )
        if injury_status in {FactStatus.AVAILABLE, FactStatus.PARTIAL}:
            if injury_timestamp is None:
                self._invalid(
                    "INJURY_TIMESTAMP_MISSING",
                    "Available injury/suspension facts require their timestamp.",
                )
        if injury_timestamp is not None and injury_timestamp > registration:
            self._invalid(
                "FUTURE_INJURY_TIMESTAMP",
                "Injury/suspension data cannot be after registration.",
            )

        if command.is_live:
            self._invalid("LIVE_CANDIDATE_FORBIDDEN", "Live candidates are unsupported.")
        if command.is_accumulator:
            self._invalid(
                "ACCUMULATOR_CANDIDATE_FORBIDDEN",
                "Combo and accumulator candidates are unsupported.",
            )
        market_identity = self._market(
            command.market_type,
            command.selection,
            command.market_line,
        )
        probability = self._decimal(command.raw_model_probability, "RAW_PROBABILITY")
        if not Decimal("0.001") <= probability <= Decimal("0.999"):
            self._invalid(
                "INVALID_RAW_PROBABILITY",
                "Raw probability must be in [0.001, 0.999].",
            )
        odds = self._decimal(command.decimal_odds, "DECIMAL_ODDS")
        if odds <= Decimal("1"):
            self._invalid("INVALID_DECIMAL_ODDS", "Decimal odds must exceed 1.00.")
        expected_value = self._decimal(
            command.supplied_expected_value,
            "SUPPLIED_EXPECTED_VALUE",
        )
        confidence = self._enum(
            command.confidence_level,
            ConfidenceLevel,
            "CONFIDENCE_LEVEL",
        )
        supporting = self._enum(
            command.supporting_data_status,
            FactStatus,
            "SUPPORTING_DATA_STATUS",
        )
        availability = self._enum(
            command.market_availability,
            MarketAvailability,
            "MARKET_AVAILABILITY",
        )
        reasoning = self._reasoning(command.public_reasoning_facts)
        provenance = self._provenance(command.provenance)

        logical = self._fingerprints.logical_identity(
            prediction_id=prediction_id,
            match_id=match_id,
            model_version=model_version,
            market=market_identity,
            bankroll_scope=RiskProductScope.OFFICIAL.value,
            destination_scope=RiskProductScope.OFFICIAL.value,
        )
        content_material = {
            "logical_identity_fingerprint": logical,
            "source_event_id": source_event_id,
            "source_data_version": source_data_version,
            "competition_id": competition_id,
            "competition_name": normalized_competition,
            "home_team_id": home_team_id,
            "home_team_name": normalized_home,
            "away_team_id": away_team_id,
            "away_team_name": normalized_away,
            "kickoff_timestamp": canonical_timestamp(kickoff),
            "prediction_creation_timestamp": canonical_timestamp(prediction_created),
            "model_version": model_version,
            "market": market_identity.market.value,
            "selection": market_identity.selection,
            "market_line": canonical_decimal(market_identity.market_line),
            "raw_model_probability": canonical_decimal(probability),
            "supplied_expected_value": canonical_decimal(expected_value),
            "decimal_odds": canonical_decimal(odds),
            "odds_timestamp": canonical_timestamp(odds_timestamp),
            "odds_source_id": odds_source_id,
            "core_match_data_timestamp": canonical_timestamp(core_timestamp),
            "lineup_status": lineup_status.value,
            "lineup_data_timestamp": canonical_timestamp(lineup_timestamp),
            "injury_suspension_status": injury_status.value,
            "injury_suspension_data_timestamp": canonical_timestamp(injury_timestamp),
            "confidence_level": confidence.value,
            "public_reasoning_facts": reasoning_material(reasoning),
            "supporting_data_status": supporting.value,
            "market_availability": availability.value,
            "bankroll_scope": RiskProductScope.OFFICIAL.value,
            "destination_scope": RiskProductScope.OFFICIAL.value,
            "is_live": False,
            "is_accumulator": False,
        }
        if provenance:
            content_material["provenance"] = provenance
        content = self._fingerprints.content(content_material)
        snapshot = canonical_items(content_material)
        return PreparedOfficialPredictionCandidate(
            logical_identity_fingerprint=logical,
            content_fingerprint=content,
            source_event_id=source_event_id,
            prediction_id=prediction_id,
            match_id=match_id,
            competition_id=competition_id,
            competition_name=competition_name,
            normalized_competition_name=normalized_competition,
            home_team_id=home_team_id,
            home_team_name=home_team_name,
            normalized_home_team_name=normalized_home,
            away_team_id=away_team_id,
            away_team_name=away_team_name,
            normalized_away_team_name=normalized_away,
            kickoff_timestamp=kickoff,
            prediction_creation_timestamp=prediction_created,
            model_version=model_version,
            market_identity=market_identity,
            raw_model_probability=probability,
            supplied_expected_value=expected_value,
            decimal_odds=odds,
            odds_timestamp=odds_timestamp,
            odds_source_id=odds_source_id,
            core_match_data_timestamp=core_timestamp,
            lineup_status=lineup_status,
            lineup_data_timestamp=lineup_timestamp,
            injury_suspension_status=injury_status,
            injury_suspension_data_timestamp=injury_timestamp,
            confidence_level=confidence,
            public_reasoning_facts=reasoning,
            source_data_version=source_data_version,
            supporting_data_status=supporting,
            market_availability=availability,
            bankroll_scope=RiskProductScope.OFFICIAL,
            destination_scope=RiskProductScope.OFFICIAL,
            registration_timestamp=registration,
            normalized_snapshot=snapshot,
            provenance=provenance,
        )

    def normalize_reason_code(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).strip().upper()
        normalized = "_".join(normalized.split())
        if (
            not normalized
            or len(normalized) > self.policy.maximum_lifecycle_reason_length
            or re.fullmatch(r"[A-Z0-9][A-Z0-9_:-]*", normalized) is None
        ):
            self._invalid(
                "INVALID_LIFECYCLE_REASON",
                "Lifecycle reason codes must use bounded safe identifiers.",
            )
        return normalized

    def normalize_event_timestamp(self, value: datetime) -> datetime:
        return self._timestamp(value, "LIFECYCLE_EVENT_TIMESTAMP")

    def _scope(self, command: OfficialPredictionCandidateRegistrationCommand) -> None:
        if (
            command.bankroll_scope is not RiskProductScope.OFFICIAL
            or command.destination_scope is not RiskProductScope.OFFICIAL
        ):
            raise CandidateScopeValidationError(
                ("NON_OFFICIAL_SCOPE",),
                ("Only Official bankroll and destination scope are accepted.",),
            )

    def _market(
        self,
        market_value: str,
        selection_value: str,
        line: Decimal | None,
    ) -> OfficialCandidateMarketIdentity:
        market_key = self._comparison(self._display(market_value, "MARKET"))
        market_key = market_key.replace("/", " ").replace("_", " ")
        market_key = " ".join(market_key.split())
        aliases = {
            "match winner": OfficialCandidateMarket.MATCH_WINNER,
            "moneyline": OfficialCandidateMarket.MATCH_WINNER,
            "1x2": OfficialCandidateMarket.MATCH_WINNER,
            "double chance": OfficialCandidateMarket.DOUBLE_CHANCE,
            "totals": OfficialCandidateMarket.TOTALS,
            "over under": OfficialCandidateMarket.TOTALS,
            "over under goals": OfficialCandidateMarket.TOTALS,
            "btts": OfficialCandidateMarket.BTTS,
            "both teams to score": OfficialCandidateMarket.BTTS,
        }
        if market_key in {"correct score", "exact score"}:
            self._invalid(
                "CORRECT_SCORE_FORBIDDEN",
                "Correct-score candidates are forbidden.",
            )
        if market_key not in aliases:
            self._invalid("UNSUPPORTED_MARKET", "Market type is unsupported.")
        market = aliases[market_key]
        selection_key = self._comparison(self._display(selection_value, "SELECTION"))
        selection_key = selection_key.replace("_", " ").replace("/", " ")
        selection_key = " ".join(selection_key.split())
        selections = {
            OfficialCandidateMarket.MATCH_WINNER: {
                "home": "HOME", "1": "HOME", "draw": "DRAW", "x": "DRAW",
                "away": "AWAY", "2": "AWAY",
            },
            OfficialCandidateMarket.DOUBLE_CHANCE: {
                "home or draw": "HOME OR DRAW", "1x": "HOME OR DRAW",
                "away or draw": "AWAY OR DRAW", "x2": "AWAY OR DRAW",
                "home or away": "HOME OR AWAY", "12": "HOME OR AWAY",
            },
            OfficialCandidateMarket.TOTALS: {"over": "OVER", "under": "UNDER"},
            OfficialCandidateMarket.BTTS: {"yes": "YES", "no": "NO"},
        }[market]
        if selection_key not in selections:
            self._invalid(
                "INCONSISTENT_MARKET_SELECTION",
                "Selection is inconsistent with the supplied market.",
            )
        normalized_line: Decimal | None = None
        if market is OfficialCandidateMarket.TOTALS:
            if line is None:
                self._invalid("INVALID_MARKET_LINE", "Totals require a market line.")
            normalized_line = self._decimal(line, "MARKET_LINE")
            if normalized_line <= 0:
                self._invalid(
                    "INVALID_MARKET_LINE",
                    "Totals market lines must be positive.",
                )
        elif line is not None:
            self._invalid(
                "INVALID_MARKET_LINE",
                "This market must not contain a market line.",
            )
        return OfficialCandidateMarketIdentity(
            market=market,
            selection=selections[selection_key],
            market_line=normalized_line,
        )

    def _reasoning(
        self,
        values: tuple[OfficialPredictionReasoningFact, ...],
    ) -> tuple[OfficialPredictionReasoningFact, ...]:
        if not isinstance(values, tuple) or not values:
            self._invalid(
                "REASONING_FACTS_MISSING",
                "At least one structured public reasoning fact is required.",
            )
        if len(values) > self.policy.maximum_reasoning_fact_count:
            self._invalid(
                "TOO_MANY_REASONING_FACTS",
                "Public reasoning fact count exceeds its bounded limit.",
            )
        normalized: list[OfficialPredictionReasoningFact] = []
        for fact in values:
            if not isinstance(fact, OfficialPredictionReasoningFact) or not isinstance(
                fact.fact_type,
                ReasoningFactType,
            ):
                self._invalid(
                    "UNSUPPORTED_REASONING_FACT",
                    "Reasoning facts must use approved structured types.",
                )
            text = self._display(
                fact.text,
                "REASONING_FACT",
                maximum=self.policy.maximum_reasoning_fact_length,
            )
            source = (
                self._identifier(fact.source_reference, "REASONING_SOURCE")
                if fact.source_reference is not None
                else None
            )
            if fact.source_reference is not None and any(
                pattern.search(fact.source_reference)
                for pattern in (_URL, _AFFILIATE, _CREDENTIAL)
            ):
                self._invalid(
                    "UNSAFE_REASONING_SOURCE",
                    "Reasoning source references must not contain URLs, "
                    "affiliates, or credentials.",
                )
            if (
                source is not None
                and len(source) > self.policy.maximum_reasoning_source_length
            ):
                self._invalid(
                    "REASONING_SOURCE_TOO_LONG",
                    "Reasoning source identity exceeds its bounded limit.",
                )
            for pattern, code, explanation in (
                (
                    _URL,
                    "REASONING_URL_FORBIDDEN",
                    "Reasoning facts must not contain URLs.",
                ),
                (
                    _AFFILIATE,
                    "AFFILIATE_CONTENT_FORBIDDEN",
                    "Affiliate content is forbidden.",
                ),
                (
                    _CREDENTIAL,
                    "CREDENTIAL_CONTENT_FORBIDDEN",
                    "Credential-like content is forbidden.",
                ),
                (
                    _PROMOTIONAL,
                    "PROMOTIONAL_CLAIM_FORBIDDEN",
                    "Guaranteed or risk-free claims are forbidden.",
                ),
                (
                    _CORRECT_SCORE,
                    "CORRECT_SCORE_REASONING_FORBIDDEN",
                    "Correct-score wording is forbidden.",
                ),
                (
                    _HTML,
                    "HTML_CONTENT_FORBIDDEN",
                    "Reasoning facts must be HTML-neutral.",
                ),
            ):
                if pattern.search(text):
                    self._invalid(code, explanation)
            normalized.append(
                OfficialPredictionReasoningFact(fact.fact_type, text, source)
            )
        ordered = tuple(sorted(
            normalized,
            key=lambda item: (
                item.fact_type.value,
                self._comparison(item.text),
                item.source_reference or "",
            ),
        ))
        if len(set(ordered)) != len(ordered):
            self._invalid(
                "DUPLICATE_REASONING_FACT",
                "Duplicate structured reasoning facts are unsupported.",
            )
        if sum(len(item.text) for item in ordered) > self.policy.maximum_total_reasoning_length:
            self._invalid(
                "REASONING_TOTAL_TOO_LONG",
                "Combined reasoning text exceeds its bounded limit.",
            )
        return ordered

    def _provenance(
        self,
        values: tuple[tuple[str, str], ...],
    ) -> tuple[tuple[str, str], ...]:
        if not isinstance(values, tuple):
            self._invalid(
                "INVALID_PROVENANCE",
                "Candidate provenance must be an immutable tuple.",
            )
        if len(values) > self.policy.maximum_provenance_item_count:
            self._invalid(
                "TOO_MUCH_PROVENANCE",
                "Candidate provenance exceeds its bounded item limit.",
            )
        normalized: list[tuple[str, str]] = []
        for item in values:
            if not isinstance(item, tuple) or len(item) != 2:
                self._invalid(
                    "INVALID_PROVENANCE",
                    "Candidate provenance must contain immutable text pairs.",
                )
            key = self._identifier(item[0], "PROVENANCE_KEY")
            value = self._display(
                item[1],
                "PROVENANCE_VALUE",
                maximum=self.policy.maximum_provenance_value_length,
            )
            if any(
                pattern.search(value) or pattern.search(key)
                for pattern in (_URL, _AFFILIATE, _CREDENTIAL)
            ):
                self._invalid(
                    "UNSAFE_PROVENANCE",
                    "Candidate provenance cannot contain URLs, affiliates, or credentials.",
                )
            normalized.append((key, value))
        ordered = tuple(sorted(normalized))
        if len({key for key, _ in ordered}) != len(ordered):
            self._invalid(
                "DUPLICATE_PROVENANCE_KEY",
                "Candidate provenance keys must be unique.",
            )
        return ordered

    def _identifier(self, value: str, code: str) -> str:
        if not isinstance(value, str):
            self._invalid(f"INVALID_{code}", f"{code} must be a string identifier.")
        normalized = unicodedata.normalize("NFKC", value).strip().casefold()
        if (
            not normalized
            or len(normalized) > self.policy.maximum_identifier_length
            or _IDENTIFIER.fullmatch(normalized) is None
        ):
            self._invalid(f"INVALID_{code}", f"{code} is malformed.")
        return normalized

    def _optional_identifier(self, value: str | None, code: str) -> str | None:
        return None if value is None else self._identifier(value, code)

    def _model_version(self, value: str) -> str:
        normalized = self._identifier(value, "MODEL_VERSION")
        if len(normalized) > self.policy.maximum_model_version_length:
            self._invalid("INVALID_MODEL_VERSION", "Model version is too long.")
        return normalized

    def _display(self, value: str, code: str, maximum: int | None = None) -> str:
        if not isinstance(value, str):
            self._invalid(f"INVALID_{code}", f"{code} must be supplied as text.")
        normalized = " ".join(unicodedata.normalize("NFC", value).strip().split())
        limit = maximum or self.policy.maximum_display_name_length
        if not normalized or len(normalized) > limit or _HTML.search(normalized):
            self._invalid(f"INVALID_{code}", f"{code} is empty or malformed.")
        if any(unicodedata.category(char) == "Cc" for char in normalized):
            self._invalid(f"INVALID_{code}", f"{code} contains control characters.")
        return normalized

    def _public_name(self, value: str, code: str) -> str:
        if not isinstance(value, str):
            self._invalid(f"INVALID_{code}", f"{code} must be supplied as text.")
        preserved = unicodedata.normalize("NFC", value).strip()
        if (
            not preserved
            or len(preserved) > self.policy.maximum_display_name_length
            or _HTML.search(preserved)
            or any(unicodedata.category(char) == "Cc" for char in preserved)
        ):
            self._invalid(f"INVALID_{code}", f"{code} is empty or malformed.")
        return preserved

    @staticmethod
    def _comparison(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

    def _timestamp(self, value: datetime, code: str) -> datetime:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            self._invalid(f"INVALID_{code}", f"{code} must be timezone-aware.")
        return value.astimezone(timezone.utc)

    def _optional_timestamp(self, value: datetime | None, code: str) -> datetime | None:
        return None if value is None else self._timestamp(value, code)

    def _decimal(self, value: Decimal, code: str) -> Decimal:
        if not isinstance(value, Decimal) or not value.is_finite():
            self._invalid(f"INVALID_{code}", f"{code} must be a finite Decimal.")
        return value.normalize()

    def _enum(
        self,
        value: object,
        enum_type: type[_EnumT],
        code: str,
    ) -> _EnumT:
        if not isinstance(value, enum_type):
            self._invalid(f"INVALID_{code}", f"{code} uses an unsupported value.")
        return value

    @staticmethod
    def _invalid(code: str, explanation: str) -> None:
        raise CandidateRegistrationValidationError((code,), (explanation,))
