from types import MappingProxyType

from .config import QualityScoreConfig
from .models import QualityScoreResult, QualitySignal, QualitySignals


class QualityScoreEngine:
    """Deterministically evaluates supporting-data quality."""

    def __init__(self, config: QualityScoreConfig) -> None:
        self._validate_config(config)
        self._weights = MappingProxyType(dict(config.signal_weights))
        self._critical_signals = config.critical_signals
        self._conflict_penalty_weight = config.conflict_penalty_weight
        self._missing_penalty_weight = config.missing_penalty_weight
        self._critical_missing_penalty_weight = (
            config.critical_missing_penalty_weight
        )

    def evaluate(self, signals: QualitySignals) -> QualityScoreResult:
        """Return data quality without choosing or modifying a prediction."""
        values = signals.values()
        self._validate_signals(signals, values)

        ordered_signals = tuple(QualitySignal)
        available = tuple(
            signal for signal in ordered_signals if values[signal] is not None
        )
        missing = tuple(
            signal for signal in ordered_signals if values[signal] is None
        )

        total_weight = sum(self._weights.values())
        available_weight = sum(self._weights[signal] for signal in available)
        completeness = available_weight / total_weight
        weighted_quality = sum(
            self._weights[signal] * (values[signal] or 0.0)
            for signal in ordered_signals
        ) / total_weight

        consistency = 1.0 - signals.conflicting_signal_penalty
        critical_weight = sum(
            self._weights[signal] for signal in self._critical_signals
        )
        missing_critical_weight = sum(
            self._weights[signal]
            for signal in missing
            if signal in self._critical_signals
        )
        critical_missing_ratio = missing_critical_weight / critical_weight

        score_value = weighted_quality
        score_value *= 1.0 - (
            signals.conflicting_signal_penalty
            * self._conflict_penalty_weight
        )
        score_value *= 1.0 - (
            signals.missing_data_penalty
            * self._missing_penalty_weight
        )
        score_value *= 1.0 - (
            critical_missing_ratio
            * self._critical_missing_penalty_weight
        )

        warnings, reason_codes = self._explanations(
            missing=missing,
            critical_missing_ratio=critical_missing_ratio,
            conflicting_penalty=signals.conflicting_signal_penalty,
            missing_penalty=signals.missing_data_penalty,
        )

        return QualityScoreResult(
            score=max(0, min(round(score_value * 100), 100)),
            completeness=round(completeness, 6),
            consistency=round(consistency, 6),
            available_signals=available,
            missing_signals=missing,
            warnings=warnings,
            reason_codes=reason_codes,
        )

    @staticmethod
    def _validate_config(config: QualityScoreConfig) -> None:
        configured_signals = set(config.signal_weights)
        expected_signals = set(QualitySignal)

        if configured_signals != expected_signals:
            raise ValueError("Quality score weights must cover every signal.")

        for weight in config.signal_weights.values():
            QualityScoreEngine._validate_number(weight, "Signal weight")
            if weight <= 0.0:
                raise ValueError("Signal weights must be greater than zero.")

        if not config.critical_signals:
            raise ValueError("At least one critical quality signal is required.")
        if not config.critical_signals.issubset(expected_signals):
            raise ValueError("Critical quality signals must be configured signals.")

        for penalty_weight in (
            config.conflict_penalty_weight,
            config.missing_penalty_weight,
            config.critical_missing_penalty_weight,
        ):
            QualityScoreEngine._validate_unit_interval(
                penalty_weight,
                "Penalty weight",
            )

    @staticmethod
    def _validate_signals(
        signals: QualitySignals,
        values: dict[QualitySignal, float | None],
    ) -> None:
        for value in values.values():
            if value is not None:
                QualityScoreEngine._validate_unit_interval(
                    value,
                    "Quality signal",
                )

        QualityScoreEngine._validate_unit_interval(
            signals.conflicting_signal_penalty,
            "Conflicting-signal penalty",
        )
        QualityScoreEngine._validate_unit_interval(
            signals.missing_data_penalty,
            "Missing-data penalty",
        )

    @staticmethod
    def _validate_unit_interval(value: float, label: str) -> None:
        QualityScoreEngine._validate_number(value, label)
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{label} must be between 0.0 and 1.0.")

    @staticmethod
    def _validate_number(value: float, label: str) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{label} must be numeric.")

    @staticmethod
    def _explanations(
        missing: tuple[QualitySignal, ...],
        critical_missing_ratio: float,
        conflicting_penalty: float,
        missing_penalty: float,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        warnings: list[str] = []
        reason_codes: list[str] = []

        if missing:
            warnings.append("Supporting data is incomplete.")
            reason_codes.append("DATA_PARTIAL")
        else:
            reason_codes.append("DATA_COMPLETE")

        if critical_missing_ratio > 0.0:
            warnings.append("Critical supporting data is missing.")
            reason_codes.append("CRITICAL_DATA_MISSING")
        if conflicting_penalty > 0.0:
            warnings.append("Supporting signals conflict.")
            reason_codes.append("SIGNALS_CONFLICT")
        if missing_penalty > 0.0:
            warnings.append("An additional missing-data penalty applies.")
            reason_codes.append("MISSING_DATA_PENALTY")

        return tuple(warnings), tuple(reason_codes)
