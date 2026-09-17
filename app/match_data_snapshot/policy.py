from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MatchDataSnapshotPolicy:
    version: str = "match-data-snapshot-policy-v1"
    maximum_identifier_length: int = 160
    maximum_name_length: int = 200
    maximum_context_length: int = 500
    maximum_reason_code_length: int = 96

    def __post_init__(self) -> None:
        if not self.version.strip() or min(
            self.maximum_identifier_length,
            self.maximum_name_length,
            self.maximum_context_length,
            self.maximum_reason_code_length,
        ) <= 0:
            raise ValueError("Snapshot policy values must be positive.")


DEFAULT_MATCH_DATA_SNAPSHOT_POLICY = MatchDataSnapshotPolicy()
