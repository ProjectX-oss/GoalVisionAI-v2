from dataclasses import dataclass
from typing import Protocol

from .models import (
    FinishedMatchResult,
    PublishedPredictionReference,
    ResolutionStatus,
    SettlementReasonCode,
)


@dataclass(frozen=True, slots=True)
class RuleSettlement:
    status: ResolutionStatus
    rule_version: str
    reason_codes: tuple[SettlementReasonCode, ...]


class MarketSettlementRule(Protocol):
    aliases: frozenset[str]
    version: str

    def settle(
        self,
        prediction: PublishedPredictionReference,
        match: FinishedMatchResult,
    ) -> RuleSettlement:
        ...


class MatchWinnerSettlementRule:
    aliases = frozenset({"MATCH WINNER", "1X2", "WINNER"})
    version = "match-winner-v1"

    _HOME_SELECTIONS = frozenset({"HOME", "HOME WIN", "1"})
    _AWAY_SELECTIONS = frozenset({"AWAY", "AWAY WIN", "2"})
    _DRAW_SELECTIONS = frozenset({"DRAW", "X"})

    def settle(
        self,
        prediction: PublishedPredictionReference,
        match: FinishedMatchResult,
    ) -> RuleSettlement:
        selection = prediction.selection.strip().upper()
        if selection in self._HOME_SELECTIONS:
            selected_outcome = "HOME"
        elif selection in self._AWAY_SELECTIONS:
            selected_outcome = "AWAY"
        elif selection in self._DRAW_SELECTIONS:
            selected_outcome = "DRAW"
        else:
            return RuleSettlement(
                status=ResolutionStatus.UNRESOLVED,
                rule_version=self.version,
                reason_codes=(SettlementReasonCode.MALFORMED_PREDICTION,),
            )

        if match.home_score is None or match.away_score is None:
            return RuleSettlement(
                status=ResolutionStatus.UNRESOLVED,
                rule_version=self.version,
                reason_codes=(SettlementReasonCode.FINAL_SCORE_MISSING,),
            )
        if match.home_score > match.away_score:
            actual_outcome = "HOME"
        elif match.away_score > match.home_score:
            actual_outcome = "AWAY"
        else:
            actual_outcome = "DRAW"

        return RuleSettlement(
            status=(
                ResolutionStatus.WON
                if selected_outcome == actual_outcome
                else ResolutionStatus.LOST
            ),
            rule_version=self.version,
            reason_codes=(SettlementReasonCode.MATCH_RESULT_SETTLED,),
        )


class MarketSettlementRegistry:
    def __init__(self, rules: tuple[MarketSettlementRule, ...]) -> None:
        if not rules:
            raise ValueError("At least one market settlement rule is required.")
        self._rules: dict[str, MarketSettlementRule] = {}
        for rule in rules:
            if not rule.aliases:
                raise ValueError("Settlement rules must define market aliases.")
            for alias in rule.aliases:
                normalized = alias.strip().upper()
                if not normalized:
                    raise ValueError("Market aliases must not be empty.")
                if normalized in self._rules:
                    raise ValueError(f"Duplicate market alias: {normalized}")
                self._rules[normalized] = rule

    def find(self, market: str) -> MarketSettlementRule | None:
        return self._rules.get(market.strip().upper())


DEFAULT_MARKET_SETTLEMENT_REGISTRY = MarketSettlementRegistry(
    (MatchWinnerSettlementRule(),)
)
