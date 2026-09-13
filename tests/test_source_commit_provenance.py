"""Reviewed source identity and bootstrap-only audit regressions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.database import Database
from app.lab_combo.cli import _analysis_input as lab_combo_analysis_input
from app.model_activation import RuntimeArtifactReference
from app.model_activation.repository import SQLiteModelActivationRepository
from app.model_activation_audit import (
    ReviewedSourceProvenanceError,
    resolve_reviewed_source_provenance,
)
from app.model_activation_audit.models import AuditSeverity, AuditStatus
from app.model_activation_audit.repository import ReadOnlyAuditRepository
from app.model_activation_audit.service import (
    AuditInputError,
    ModelActivationAuditService,
)
from app.model_operations_rehearsal.fixtures import seed_lab_fixture
from app.real_match_lab_analysis.engine import (
    EngineRejected,
    _require_reviewed_source_commit,
)


REVIEWED_COMMIT = "27fb6a2966a817dff5a3671e4b92bf87c79f05d4"


def reviewed_reference() -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        model_artifact_id=(
            "historical-model-artifact-"
            "b1c0cc430f55bd6872426e15291c2f2dee37bf3f09f83d231c9d647e71fa9399"
        ),
        model_artifact_fingerprint=(
            "b1c0cc430f55bd6872426e15291c2f2dee37bf3f09f83d231c9d647e71fa9399"
        ),
        preprocessing_fingerprint=(
            "0a734fb5891ea44da194385eb5abffc4b7a91573f8d6740213bcdebbc1d680d0"
        ),
        calibration_artifact_set_id=(
            "historical-calibration-artifact-set-"
            "240eb571a7a337925f05b3510404e357f69e33f3f4a5bc0d2e46619d23d1351c"
        ),
        calibration_artifact_set_fingerprint=(
            "240eb571a7a337925f05b3510404e357f69e33f3f4a5bc0d2e46619d23d1351c"
        ),
        feature_schema_version="v1",
        feature_schema_fingerprint=(
            "048405d961c2752d492819479788274942cd65c3397f9c9120c83c1a93e5be8a"
        ),
        target_contract_version="historical_raw_market_targets_v1",
        probability_contract_version="canonical-11-target-contract-v1",
        runtime_compatibility_version="probability-calibration-v1",
    )


def test_reviewed_source_commit_resolves_exactly_and_replays() -> None:
    first = resolve_reviewed_source_provenance(
        reviewed_reference(), "OFFICIAL_GLOBAL"
    )
    second = resolve_reviewed_source_provenance(
        reviewed_reference(), "OFFICIAL_GLOBAL"
    )
    assert first == second
    assert first.source_commit == REVIEWED_COMMIT
    assert first.evidence_fingerprint == (
        "9a5120cc40ab79715cdc757198f6e4d7ae2757119168ab99802454fec420458f"
    )


def test_missing_or_tampered_review_evidence_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ReviewedSourceProvenanceError):
        resolve_reviewed_source_provenance(
            reviewed_reference(), "OFFICIAL_GLOBAL", project_root=tmp_path
        )

    source = Path(
        "docs/rehearsals/live_78_recent_calibration_champion_2026-07-31.json"
    )
    target = tmp_path / source
    target.parent.mkdir(parents=True)
    document = json.loads(source.read_text(encoding="utf-8"))
    document["source_commit"] = "f" * 40
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ReviewedSourceProvenanceError):
        resolve_reviewed_source_provenance(
            reviewed_reference(), "OFFICIAL_GLOBAL", project_root=tmp_path
        )


def test_engine_accepts_only_the_reviewed_commit() -> None:
    resolved = SimpleNamespace(source_commit=REVIEWED_COMMIT)
    with patch(
        "app.real_match_lab_analysis.engine.resolve_reviewed_source_provenance",
        return_value=resolved,
    ):
        assert (
            _require_reviewed_source_commit(
                reviewed_reference(), "OFFICIAL_GLOBAL", REVIEWED_COMMIT
            )
            == REVIEWED_COMMIT
        )
        with pytest.raises(EngineRejected) as missing:
            _require_reviewed_source_commit(
                reviewed_reference(), "OFFICIAL_GLOBAL", None
            )
        assert missing.value.reason_code == "CALIBRATION_REVIEW_MISSING"
        with pytest.raises(EngineRejected) as mismatch:
            _require_reviewed_source_commit(
                reviewed_reference(), "OFFICIAL_GLOBAL", "f" * 40
            )
        assert mismatch.value.reason_code == (
            "CALIBRATION_REVIEW_SOURCE_COMMIT_MISMATCH"
        )


def test_lab_combo_input_propagates_reviewed_commit_deterministically() -> None:
    captured = datetime(2026, 9, 13, 9, 0, tzinfo=timezone.utc)
    quote = SimpleNamespace(
        quote_id="quote-1",
        provider_source_id="API_FOOTBALL",
        provider_event_id="123",
        bookmaker_name="Book A",
        market="HOME_WIN",
        decimal_odds="2.10",
        captured_at_utc=captured,
    )
    odds = SimpleNamespace(sealed_at_utc=captured, quotes=(quote,))
    selected = {
        "provider_fixture_id": "123",
        "competition_id": "78",
        "competition": "Bundesliga",
        "season": "2026",
        "home_team_id": "1",
        "home_team": "Home",
        "away_team_id": "2",
        "away_team": "Away",
        "kickoff_utc": "2026-09-13T12:00:00+00:00",
        "provider_update_timestamp_utc": captured.isoformat(),
        "feature_baseline": {
            "home_recent_form": {"matches": []},
            "away_recent_form": {"matches": []},
        },
    }

    first = lab_combo_analysis_input(
        "combo-run", selected, odds, source_commit=REVIEWED_COMMIT
    )
    replay = lab_combo_analysis_input(
        "combo-run", selected, odds, source_commit=REVIEWED_COMMIT
    )

    assert first == replay
    assert first["source_commit"] == REVIEWED_COMMIT
    assert first["request_id"] == "real-match-lab-combo-run"


def test_bootstrap_only_audit_passes_and_partial_activity_blocks() -> None:
    with tempfile.TemporaryDirectory(dir="var") as directory:
        path = Path(directory) / "bootstrap.db"
        database = Database(path)
        manifest = seed_lab_fixture(database)
        SQLiteModelActivationRepository(database, migrate=False).bootstrap_champion(
            "OFFICIAL_GLOBAL",
            manifest.champion,
            "2026-07-24T23:10:00Z",
            "Reviewed bootstrap-only Lab champion",
            "test-reviewer",
        )
        database.close()

        def audit(
            source_commit: str = REVIEWED_COMMIT,
            *,
            verify_reviewed_artifact: bool = False,
        ) -> object:
            repository = ReadOnlyAuditRepository(str(path))
            try:
                return ModelActivationAuditService(repository).audit(
                    source_commit=source_commit,
                    generated_timestamp_utc="2026-07-25T00:30:00Z",
                    environment="LAB",
                    scope="OFFICIAL_GLOBAL",
                    reviewed_artifact=(
                        reviewed_reference() if verify_reviewed_artifact else None
                    ),
                )
            finally:
                repository.close()

        passed = audit(verify_reviewed_artifact=True)
        assert passed.overall_status is AuditStatus.AUDIT_PASSED
        assert passed.source_commit == REVIEWED_COMMIT
        assert dict(passed.summary_counts)["PASS"] == 35
        with pytest.raises(AuditInputError, match="does not match"):
            audit("f" * 40, verify_reviewed_artifact=True)
        connection = Database(path)
        connection.connection.execute(
            "INSERT INTO model_activation_requests VALUES (?,?,?,?,?,?)",
            (
                "partial-request",
                "OFFICIAL_GLOBAL",
                "partial-fingerprint",
                "missing-plan",
                "2026-07-25T00:31:00Z",
                "{}",
            ),
        )
        connection.connection.commit()
        connection.close()
        blocked = audit()
        assert blocked.overall_status is AuditStatus.AUDIT_BLOCKED
        check = next(
            item
            for item in blocked.checks
            if item.check_id == "activation.plan_execution_chain"
        )
        assert check.severity is AuditSeverity.BLOCKER
