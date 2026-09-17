from dataclasses import dataclass, field

from .models import ResolutionStatus, SettlementReasonCode


@dataclass(frozen=True, slots=True)
class NonPlayableFixturePolicy:
    cancelled: ResolutionStatus = ResolutionStatus.VOID
    postponed: ResolutionStatus = ResolutionStatus.UNRESOLVED
    abandoned: ResolutionStatus = ResolutionStatus.VOID

    def __post_init__(self) -> None:
        permitted = {ResolutionStatus.VOID, ResolutionStatus.UNRESOLVED}
        if any(
            status not in permitted
            for status in (self.cancelled, self.postponed, self.abandoned)
        ):
            raise ValueError(
                "Non-playable fixtures must resolve to VOID or UNRESOLVED."
            )


@dataclass(frozen=True, slots=True)
class FixtureStatusPolicy:
    finished_statuses: frozenset[str] = field(
        default_factory=lambda: frozenset({"FT"})
    )
    pending_statuses: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"TBD", "NS", "1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
        )
    )
    cancelled_statuses: frozenset[str] = field(
        default_factory=lambda: frozenset({"CANC"})
    )
    postponed_statuses: frozenset[str] = field(
        default_factory=lambda: frozenset({"PST"})
    )
    abandoned_statuses: frozenset[str] = field(
        default_factory=lambda: frozenset({"ABD"})
    )
    non_playable: NonPlayableFixturePolicy = field(
        default_factory=NonPlayableFixturePolicy
    )

    def __post_init__(self) -> None:
        groups = (
            self.finished_statuses,
            self.pending_statuses,
            self.cancelled_statuses,
            self.postponed_statuses,
            self.abandoned_statuses,
        )
        normalized = tuple(
            frozenset(value.strip().upper() for value in group)
            for group in groups
        )
        if any(not value for group in normalized for value in group):
            raise ValueError("Fixture status codes must not be empty.")
        combined: set[str] = set()
        for group in normalized:
            if combined.intersection(group):
                raise ValueError("Fixture status groups must not overlap.")
            combined.update(group)
        object.__setattr__(self, "finished_statuses", normalized[0])
        object.__setattr__(self, "pending_statuses", normalized[1])
        object.__setattr__(self, "cancelled_statuses", normalized[2])
        object.__setattr__(self, "postponed_statuses", normalized[3])
        object.__setattr__(self, "abandoned_statuses", normalized[4])

    def classify_non_playable(
        self,
        status: str,
    ) -> tuple[ResolutionStatus, SettlementReasonCode] | None:
        normalized = status.strip().upper()
        if normalized in self.cancelled_statuses:
            return (
                self.non_playable.cancelled,
                SettlementReasonCode.FIXTURE_CANCELLED,
            )
        if normalized in self.postponed_statuses:
            return (
                self.non_playable.postponed,
                SettlementReasonCode.FIXTURE_POSTPONED,
            )
        if normalized in self.abandoned_statuses:
            return (
                self.non_playable.abandoned,
                SettlementReasonCode.FIXTURE_ABANDONED,
            )
        return None


DEFAULT_FIXTURE_STATUS_POLICY = FixtureStatusPolicy()
