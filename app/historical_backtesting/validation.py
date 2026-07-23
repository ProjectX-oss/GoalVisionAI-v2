"""Strict command, schema, Decimal, identifier, and timestamp validation."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from re import fullmatch

from .exceptions import BacktestRequestValidationError
from .models import HistoricalBacktestCommand, NormalizedBacktestCommand, SupportedMarket
from .policy import HistoricalBacktestPolicy


def normalize_utc(value: datetime | str | None, label: str, *, optional: bool = False) -> str | None:
    if value is None or value == "":
        if optional:
            return None
        raise BacktestRequestValidationError(f"{label} is required.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    except (TypeError, ValueError) as exc:
        raise BacktestRequestValidationError(f"{label} is malformed.") from exc
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BacktestRequestValidationError(f"{label} must be timezone-aware.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_command(
    command: HistoricalBacktestCommand, policy: HistoricalBacktestPolicy
) -> NormalizedBacktestCommand:
    if not isinstance(command, HistoricalBacktestCommand):
        raise BacktestRequestValidationError("Backtest command must be a typed immutable command.")
    fields = (
        "backtest_request_id", "backtest_run_name", "source_split_id", "fold_id",
        "source_training_run_id", "model_artifact_id", "calibration_run_id",
        "calibration_artifact_set_id", "odds_dataset_id", "code_metadata_version",
        "dependency_metadata_version", "environment_metadata_version", "metadata_version",
    )
    for field in fields:
        _text(getattr(command, field), field)
    for field in (
        "source_split_fingerprint", "fold_fingerprint", "source_training_run_fingerprint",
        "model_artifact_fingerprint", "calibration_run_fingerprint",
        "calibration_artifact_set_fingerprint", "odds_dataset_fingerprint",
    ):
        _sha(getattr(command, field), field)
    if (command.closing_odds_dataset_id is None) != (
        command.closing_odds_dataset_fingerprint is None
    ):
        raise BacktestRequestValidationError("Closing odds identity and fingerprint must be supplied together.")
    if command.closing_odds_dataset_id is not None:
        _text(command.closing_odds_dataset_id, "closing_odds_dataset_id")
        _sha(command.closing_odds_dataset_fingerprint or "", "closing_odds_dataset_fingerprint")
    if not isinstance(command.initial_bankroll, Decimal) or not command.initial_bankroll.is_finite() or command.initial_bankroll <= 0:
        raise BacktestRequestValidationError("Initial bankroll must be a positive finite Decimal.")
    if command.currency != "EUR":
        raise BacktestRequestValidationError("Official historical backtests use EUR only.")
    expected = {
        "backtest_policy_version": policy.version,
        "odds_selection_policy_version": policy.odds_selection_policy_version,
        "decision_snapshot_policy": policy.decision_snapshot_policy,
        "market_eligibility_policy_version": policy.market_eligibility_policy_version,
        "value_policy_version": policy.value_policy_version,
        "selection_policy_version": policy.selection_policy_version,
        "staking_policy_version": policy.staking_policy_version,
        "settlement_policy_version": policy.settlement_policy_version,
        "bankroll_policy_version": policy.bankroll_policy_version,
        "metric_policy_version": policy.metric_policy_version,
        "metadata_version": policy.metadata_version,
    }
    for field, required in expected.items():
        if getattr(command, field) != required:
            raise BacktestRequestValidationError(f"Unsupported {field}.")
    try:
        markets = tuple(SupportedMarket(value) for value in command.markets) if command.markets else tuple(SupportedMarket)
    except ValueError as exc:
        raise BacktestRequestValidationError("A requested market is unsupported.") from exc
    if len(set(markets)) != len(markets):
        raise BacktestRequestValidationError("Market filters must not contain duplicates.")
    lower = normalize_utc(command.kickoff_lower_bound, "kickoff_lower_bound", optional=True)
    upper = normalize_utc(command.kickoff_upper_bound, "kickoff_upper_bound", optional=True)
    if lower is not None and upper is not None and lower >= upper:
        raise BacktestRequestValidationError("Kickoff bounds must increase.")
    return NormalizedBacktestCommand(
        **{
            field: getattr(command, field)
            for field in NormalizedBacktestCommand.__dataclass_fields__
            if field not in {"backtest_timestamp", "kickoff_lower_bound", "kickoff_upper_bound", "markets"}
        },
        backtest_timestamp=normalize_utc(command.backtest_timestamp, "backtest_timestamp") or "",
        kickoff_lower_bound=lower, kickoff_upper_bound=upper, markets=markets,
    )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise BacktestRequestValidationError(f"{label} is invalid.")
    return value.strip()


def _sha(value: object, label: str) -> None:
    if not isinstance(value, str) or fullmatch(r"[0-9a-f]{64}", value) is None:
        raise BacktestRequestValidationError(f"{label} must be a lowercase SHA-256 fingerprint.")
