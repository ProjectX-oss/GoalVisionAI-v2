"""Persistence boundary for the deterministic assessment service."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from .models import (
    MarketOddsSnapshot,
    MarketSelection,
    MarketType,
    MarketValueAssessment,
)


class MarketValueRepository(Protocol):
    """Operations required by assessment and future read-only consumers."""

    def load_calibrated_assembly_fingerprint(
        self, calibrated_assembly_id: str
    ) -> str | None: ...

    def load_source_kickoff(self, snapshot_id: str) -> datetime | None: ...

    def append_assessment_with_odds(
        self,
        odds: MarketOddsSnapshot,
        assessment: MarketValueAssessment,
    ) -> tuple[MarketValueAssessment, bool]: ...

    def append_odds_snapshot(
        self, value: MarketOddsSnapshot
    ) -> tuple[MarketOddsSnapshot, bool]: ...

    def find_odds_by_fingerprint(
        self, fingerprint: str
    ) -> MarketOddsSnapshot | None: ...

    def load_odds_snapshot_by_id(
        self, odds_record_id: str
    ) -> MarketOddsSnapshot | None: ...

    def list_odds_for_match(self, match_id: str) -> tuple[MarketOddsSnapshot, ...]: ...

    def find_latest_odds_for_market(
        self,
        match_id: str,
        bookmaker_id: str,
        market_type: MarketType,
        selection: MarketSelection,
        market_line: Decimal | None,
    ) -> MarketOddsSnapshot | None: ...

    def list_odds_by_kickoff_window(
        self, start: datetime, end: datetime
    ) -> tuple[MarketOddsSnapshot, ...]: ...

    def append_value_assessment(
        self, value: MarketValueAssessment
    ) -> tuple[MarketValueAssessment, bool]: ...

    def find_assessment_by_fingerprint(
        self, fingerprint: str
    ) -> MarketValueAssessment | None: ...

    def load_assessment_by_id(
        self, value_assessment_id: str
    ) -> MarketValueAssessment | None: ...

    def list_assessments_for_calibrated_assembly(
        self, calibrated_assembly_id: str
    ) -> tuple[MarketValueAssessment, ...]: ...

    def list_assessments_for_match(
        self, match_id: str
    ) -> tuple[MarketValueAssessment, ...]: ...

    def find_latest_for_match_bookmaker_market(
        self,
        match_id: str,
        bookmaker_id: str,
        market_type: MarketType,
        selection: MarketSelection,
        market_line: Decimal | None,
    ) -> MarketValueAssessment | None: ...

    def list_actionable_assessments(self) -> tuple[MarketValueAssessment, ...]: ...
