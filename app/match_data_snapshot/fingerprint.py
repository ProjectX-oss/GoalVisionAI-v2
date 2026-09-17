import hashlib
import json
from dataclasses import replace

from .models import MatchDataSnapshotRegistrationCommand
from .normalization import canonical_data, canonical_json


class MatchDataSnapshotFingerprint:
    LOGICAL_VERSION = "match-data-snapshot-logical-v1"
    CONTENT_VERSION = "match-data-snapshot-content-v1"

    def logical_identity(self, command: MatchDataSnapshotRegistrationCommand) -> str:
        return _digest({
            "version": self.LOGICAL_VERSION,
            "match_id": command.match_id,
            "source_provider": command.source_provider,
            "source_event_id": command.source_event_id,
            "kickoff_timestamp": canonical_data(command.kickoff_timestamp),
        })

    def content(self, command: MatchDataSnapshotRegistrationCommand) -> str:
        material = replace(command, registration_timestamp=command.source_updated_timestamp)
        values = canonical_data(material)
        assert isinstance(values, dict)
        values.pop("registration_timestamp", None)
        return _digest({"version": self.CONTENT_VERSION, **values})

    def serialize(self, command: MatchDataSnapshotRegistrationCommand) -> str:
        return canonical_json(command)


def _digest(material: dict[str, object]) -> str:
    payload = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
