from datetime import datetime, timedelta

from .models import MonitoringObservation, MonitoringWindow, MonitoringWindowKind, aware


class MonitoringWindowService:
    @staticmethod
    def fixed_count(
        observations: tuple[MonitoringObservation, ...],
        count: int,
        *,
        end_at: datetime,
    ) -> tuple[MonitoringWindow, tuple[MonitoringObservation, ...]]:
        aware(end_at, "Window end")
        if count <= 0:
            raise ValueError("Fixed count must be positive.")
        eligible = tuple(
            item
            for item in _ordered(observations)
            if item.prediction_timestamp < end_at
        )
        selected = eligible[-count:]
        start = selected[0].prediction_timestamp if selected else end_at - timedelta(microseconds=1)
        return MonitoringWindow(MonitoringWindowKind.FIXED_COUNT, start, end_at, count), selected

    @staticmethod
    def interval(
        observations: tuple[MonitoringObservation, ...],
        *,
        start_at: datetime,
        end_at: datetime,
        rolling: bool = False,
    ) -> tuple[MonitoringWindow, tuple[MonitoringObservation, ...]]:
        window = MonitoringWindow(
            MonitoringWindowKind.ROLLING_INTERVAL if rolling else MonitoringWindowKind.FIXED_INTERVAL,
            start_at,
            end_at,
        )
        return window, tuple(
            item
            for item in _ordered(observations)
            if start_at <= item.prediction_timestamp < end_at
        )

    @staticmethod
    def rolling_count(
        observations: tuple[MonitoringObservation, ...],
        count: int,
        *,
        generated_for: datetime,
    ) -> tuple[MonitoringWindow, tuple[MonitoringObservation, ...]]:
        window, selected = MonitoringWindowService.fixed_count(
            observations, count, end_at=generated_for
        )
        return (
            MonitoringWindow(
                MonitoringWindowKind.ROLLING_COUNT,
                window.start_at,
                window.end_at,
                count,
            ),
            selected,
        )

    @staticmethod
    def rolling_interval(
        observations: tuple[MonitoringObservation, ...],
        interval: timedelta,
        *,
        generated_for: datetime,
    ) -> tuple[MonitoringWindow, tuple[MonitoringObservation, ...]]:
        if interval <= timedelta(0):
            raise ValueError("Rolling interval must be positive.")
        return MonitoringWindowService.interval(
            observations,
            start_at=generated_for - interval,
            end_at=generated_for,
            rolling=True,
        )

    @staticmethod
    def explicit_range(
        observations: tuple[MonitoringObservation, ...],
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[MonitoringWindow, tuple[MonitoringObservation, ...]]:
        window, selected = MonitoringWindowService.interval(
            observations, start_at=start_at, end_at=end_at
        )
        return (
            MonitoringWindow(MonitoringWindowKind.EXPLICIT_RANGE, start_at, end_at),
            selected,
        )


def _ordered(
    observations: tuple[MonitoringObservation, ...],
) -> tuple[MonitoringObservation, ...]:
    return tuple(
        sorted(
            observations,
            key=lambda item: (
                item.prediction_timestamp,
                item.prediction_id,
                item.fixture_id,
                item.market,
            ),
        )
    )
