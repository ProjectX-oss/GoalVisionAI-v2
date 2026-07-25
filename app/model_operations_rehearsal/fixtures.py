"""Deterministic fictional evidence for the isolated Lab rehearsal only.

This module intentionally depends on repository test fixtures. It is not
imported by application startup and exposes no activation execution path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from unittest.mock import patch

from app.database import Database, MigrationManager
from app.model_activation import (
    ActivationRequest,
    RuntimeArtifactReference,
)
from app.model_activation.evidence import build_activation_evidence
from app.model_comparison_promotion import (
    DEFAULT_PROMOTION_POLICY,
    Recommendation,
    SQLiteModelComparisonRepository,
    calculate_promotion_score,
    canonical_json,
    challenger_evaluation_fingerprint,
    comparison_request_fingerprint,
    comparison_run_fingerprint,
    metric_comparison_fingerprint,
    recommend_challenger,
    sha256_fingerprint,
)
from app.shadow_evaluation import (
    ShadowEvaluationCommand,
    ShadowModelInputSnapshot,
    ShadowOddsSnapshot,
    ShadowOddsSnapshotSet,
    ShadowSettlementCommand,
    StaticShadowInputSource,
    SQLiteShadowEvaluationRepository,
    build_shadow_evaluation_service,
    build_shadow_settlement_service,
    fingerprint_input_snapshot,
)
from app.shadow_evaluation.fingerprint import (
    sha256_fingerprint as shadow_sha256_fingerprint,
)

UTC = timezone.utc
FIXTURE_LABEL = "FICTIONAL_LAB_REHEARSAL_ONLY"


@dataclass(frozen=True, slots=True)
class LabFixtureManifest:
    label: str
    model_scope: str
    champion: RuntimeArtifactReference
    challenger: RuntimeArtifactReference
    comparison_run_id: str
    comparison_run_fingerprint: str
    challenger_candidate_id: str
    recommendation_id: str
    recommendation_fingerprint: str
    evidence_cutoff_timestamp_utc: str
    shadow_evidence_fingerprint: str
    settled_shadow_count: int
    observation_days: str

    def as_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2)


def seed_lab_fixture(database: Database) -> LabFixtureManifest:
    """Seed one complete fictional chain through typed public boundaries."""
    return seed_fictional_fixture(database, FIXTURE_LABEL)


def seed_fictional_fixture(
    database: Database,
    fixture_label: str,
) -> LabFixtureManifest:
    """Seed the existing deterministic chain with one explicit safe marker."""
    if (
        not isinstance(fixture_label, str)
        or not fixture_label.startswith("FICTIONAL_")
        or not fixture_label.endswith("_REHEARSAL_ONLY")
    ):
        raise ValueError("A deterministic fictional rehearsal marker is required.")
    with patch(f"{__name__}.FIXTURE_LABEL", fixture_label):
        return _seed_fictional_fixture(database)


def _seed_fictional_fixture(database: Database) -> LabFixtureManifest:
    MigrationManager(database.connection).migrate()
    template = _seed_existing_artifact_fixture(database)
    comparison_repository = SQLiteModelComparisonRepository(database, migrate=False)
    base = comparison_repository.load_comparison_run(
        template.outcome.comparison_run_id
    )
    promoted = _append_fictional_promotion(comparison_repository, base)
    evaluation = promoted.evaluations[0]
    recommendations = comparison_repository.list_recommendations(
        promoted.comparison_run_id
    )
    recommendation = next(
        item
        for item in recommendations
        if item.recommendation_scope == "CHALLENGER"
    )
    champion = _runtime_reference(template.champion_training, template.champion_calibration)
    challenger = _runtime_reference(
        template.challenger_training,
        template.challenger_calibration,
    )
    cutoff = datetime(2026, 8, 1, 12, tzinfo=UTC)
    _seed_shadow_evidence(
        database,
        champion=champion,
        challenger=challenger,
        comparison=promoted,
        evaluation=evaluation,
        recommendation=recommendation,
    )
    request = ActivationRequest(
        activation_request_id="lab-rehearsal-evidence-preview",
        activation_name=FIXTURE_LABEL,
        model_scope="OFFICIAL_GLOBAL",
        current_champion_generation_id="not-yet-bootstrapped",
        current_champion_generation_fingerprint="not-yet-bootstrapped",
        current_champion=champion,
        challenger=challenger,
        comparison_run_id=promoted.comparison_run_id,
        comparison_run_fingerprint=promoted.comparison_run_fingerprint,
        challenger_candidate_id=evaluation.candidate.challenger_candidate_id,
        recommendation_id=recommendation.recommendation_id,
        recommendation_fingerprint=recommendation.recommendation_fingerprint,
        evidence_cutoff_timestamp_utc=cutoff,
        requested_timestamp_utc=cutoff,
        activation_reason=FIXTURE_LABEL,
        operator_identity="codex-lab-rehearsal",
    )
    evidence = build_activation_evidence(
        request,
        SQLiteShadowEvaluationRepository(database, migrate=False),
    )
    return LabFixtureManifest(
        label=FIXTURE_LABEL,
        model_scope="OFFICIAL_GLOBAL",
        champion=champion,
        challenger=challenger,
        comparison_run_id=promoted.comparison_run_id,
        comparison_run_fingerprint=promoted.comparison_run_fingerprint,
        challenger_candidate_id=evaluation.candidate.challenger_candidate_id,
        recommendation_id=recommendation.recommendation_id,
        recommendation_fingerprint=recommendation.recommendation_fingerprint,
        evidence_cutoff_timestamp_utc=cutoff.isoformat().replace("+00:00", "Z"),
        shadow_evidence_fingerprint=evidence.evidence_fingerprint,
        settled_shadow_count=evidence.settled_count,
        observation_days=str(evidence.observation_days),
    )


def _seed_existing_artifact_fixture(database: Database):
    from tests.test_model_comparison_promotion import (
        ModelComparisonPromotionTests,
    )

    with patch(
        "tests.test_model_comparison_promotion.Database",
        return_value=database,
    ):
        ModelComparisonPromotionTests.setUpClass()
    return ModelComparisonPromotionTests


def _append_fictional_promotion(repository, base):
    original = base.evaluations[0]
    metrics = tuple(
        replace(
            item,
            normalized_score=Decimal(1),
            metric_fingerprint=metric_comparison_fingerprint(
                {
                    "category": item.category,
                    "group": item.group_identity,
                    "metric": item.metric_name,
                    "direction": item.direction,
                    "champion": item.champion_value,
                    "challenger": item.challenger_value,
                    "delta": item.absolute_delta,
                    "relative": item.relative_delta,
                    "score": Decimal(1),
                    "materiality": item.materiality,
                    "gate": item.gate_status,
                    "reasons": item.reason_codes,
                }
            ),
        )
        for item in original.metric_evaluations
    )
    first_statistical = replace(
        original.statistical_evidence[0],
        effect_size=Decimal("0.05"),
        lower_confidence_bound=Decimal("0.02"),
        upper_confidence_bound=Decimal("0.08"),
        uncertainty_classification=type(
            original.statistical_evidence[0].uncertainty_classification
        ).STRONG_EVIDENCE,
        detail_snapshot=canonical_json(
            {"fixture": FIXTURE_LABEL, "effect_size": Decimal("0.05")}
        ),
        evidence_fingerprint=sha256_fingerprint(
            (FIXTURE_LABEL, "BRIER_DELTA", "0.05")
        ),
    )
    statistical = (first_statistical, *original.statistical_evidence[1:])
    components, score = calculate_promotion_score(
        metrics,
        original.stability_groups,
        original.gate_evaluations,
        statistical,
        DEFAULT_PROMOTION_POLICY,
    )
    recommendation, reasons = recommend_challenger(
        original.gate_evaluations,
        score,
        statistical,
        DEFAULT_PROMOTION_POLICY,
    )
    if recommendation is not Recommendation.PROMOTE_CHALLENGER:
        raise AssertionError("The unchanged default policy rejected the Lab fixture.")
    prior = challenger_evaluation_fingerprint(
        {
            "fixture": FIXTURE_LABEL,
            "metric_fingerprints": tuple(item.metric_fingerprint for item in metrics),
            "statistical_fingerprints": tuple(
                item.evidence_fingerprint for item in statistical
            ),
            "components": components,
            "score": score,
            "recommendation": recommendation,
            "reasons": reasons,
        }
    )
    evaluation = replace(
        original,
        metric_evaluations=metrics,
        statistical_evidence=statistical,
        score_components=components,
        promotion_score=score,
        recommendation=recommendation,
        deterministic_rank=1,
        reason_codes=(FIXTURE_LABEL, *reasons),
        evaluation_fingerprint=challenger_evaluation_fingerprint(
            {
                "prior_evaluation_fingerprint": prior,
                "rank": 1,
                "recommendation": recommendation,
                "reason_codes": (FIXTURE_LABEL, *reasons),
            }
        ),
    )
    command = replace(
        base.command,
        comparison_request_id="lab-rehearsal-promotion-comparison",
        comparison_run_name=FIXTURE_LABEL,
        comparison_timestamp="2026-07-15T04:00:00Z",
    )
    request_fingerprint = comparison_request_fingerprint(command)
    ranking = (evaluation.candidate.challenger_candidate_id,)
    run_fingerprint = comparison_run_fingerprint(
        request_fingerprint,
        (evaluation.evaluation_fingerprint,),
        ranking,
        recommendation.value,
        DEFAULT_PROMOTION_POLICY.versions,
    )
    run_material = {
        "request_fingerprint": request_fingerprint,
        "evaluation_fingerprints": (evaluation.evaluation_fingerprint,),
        "ranking": ranking,
        "final_recommendation": recommendation,
        "final_recommended_challenger_id": ranking[0],
        "policy_versions": DEFAULT_PROMOTION_POLICY.versions,
        "exclusions": (),
        "fixture_label": FIXTURE_LABEL,
    }
    prepared = replace(
        base,
        comparison_run_id=f"model-comparison-run-{run_fingerprint}",
        command=command,
        request_fingerprint=request_fingerprint,
        comparison_run_fingerprint=run_fingerprint,
        evaluations=(evaluation,),
        final_recommended_challenger_id=ranking[0],
        final_recommendation=recommendation,
        reason_codes=(FIXTURE_LABEL, "PROMOTION_RECOMMENDATION_ONLY_NO_ACTIVATION"),
        exclusions=(),
        deterministic_run_snapshot=canonical_json(
            {
                "command": command,
                "run_material": run_material,
                "reason_codes": (
                    FIXTURE_LABEL,
                    "PROMOTION_RECOMMENDATION_ONLY_NO_ACTIVATION",
                ),
            }
        ),
    )
    repository.append_comparison_run(prepared)
    return repository.load_comparison_run(prepared.comparison_run_id)


def _runtime_reference(training, calibration) -> RuntimeArtifactReference:
    artifact = training.artifact
    artifact_set = calibration.artifact_set
    return RuntimeArtifactReference(
        model_artifact_id=artifact.artifact_id,
        model_artifact_fingerprint=artifact.artifact_fingerprint,
        preprocessing_fingerprint=artifact.preprocessing.preprocessing_fingerprint,
        calibration_artifact_set_id=artifact_set.artifact_set_id,
        calibration_artifact_set_fingerprint=artifact_set.artifact_set_fingerprint,
        feature_schema_version=artifact.feature_schema_version,
        feature_schema_fingerprint=artifact.feature_schema_fingerprint,
        target_contract_version=artifact.target_schema_version,
        probability_contract_version="canonical-11-target-contract-v1",
        runtime_compatibility_version="probability-calibration-v1",
    )


def _seed_shadow_evidence(
    database,
    *,
    champion,
    challenger,
    comparison,
    evaluation,
    recommendation,
) -> None:
    from app.historical_model_training import SQLiteHistoricalModelTrainingRepository

    model_repository = SQLiteHistoricalModelTrainingRepository(
        database,
        migrate=False,
    )
    artifact = model_repository.load_model_artifact(champion.model_artifact_id)
    inputs = []
    odds_sets = []
    commands = []
    base = datetime(2026, 7, 1, 10, tzinfo=UTC)
    for index in range(30):
        evaluation_time = base + timedelta(days=14 * index / 29)
        kickoff = evaluation_time + timedelta(hours=2)
        identity = f"lab-rehearsal-{index:02d}"
        snapshot = ShadowModelInputSnapshot(
            model_input_vector_id=f"{identity}-input",
            model_input_fingerprint=sha256_fingerprint((identity, "input")),
            match_id=f"{identity}-match",
            competition="FICTIONAL_LAB",
            season="2026",
            home_team="LAB_HOME",
            away_team="LAB_AWAY",
            kickoff_utc=kickoff,
            snapshot_timestamp_utc=evaluation_time - timedelta(hours=1),
            feature_schema_version=artifact.feature_schema_version,
            feature_schema_fingerprint=artifact.feature_schema_fingerprint,
            feature_provenance_fingerprint=sha256_fingerprint(
                (identity, "provenance")
            ),
            ordered_feature_names=artifact.ordered_feature_names,
            ordered_feature_values=tuple(
                Decimal("0") for _ in artifact.ordered_feature_names
            ),
            missingness_mask=tuple(False for _ in artifact.ordered_feature_names),
            ordered_missing_features=(),
            completeness_score=Decimal(1),
            ordered_source_timestamps=(evaluation_time - timedelta(hours=1),),
            input_snapshot_fingerprint="pending",
        )
        snapshot = fingerprint_input_snapshot(snapshot)
        odds_set = _odds_set(identity, snapshot.match_id, evaluation_time, kickoff)
        command = ShadowEvaluationCommand(
            shadow_request_id=f"{identity}-request",
            shadow_run_name=FIXTURE_LABEL,
            comparison_run_id=comparison.comparison_run_id,
            comparison_run_fingerprint=comparison.comparison_run_fingerprint,
            challenger_candidate_id=evaluation.candidate.challenger_candidate_id,
            recommendation_id=recommendation.recommendation_id,
            recommendation_fingerprint=recommendation.recommendation_fingerprint,
            champion_model_artifact_id=champion.model_artifact_id,
            champion_model_artifact_fingerprint=champion.model_artifact_fingerprint,
            champion_calibration_artifact_set_id=champion.calibration_artifact_set_id,
            champion_calibration_artifact_set_fingerprint=champion.calibration_artifact_set_fingerprint,
            champion_runtime_policy_version="probability-calibration-v1",
            challenger_model_artifact_id=challenger.model_artifact_id,
            challenger_model_artifact_fingerprint=challenger.model_artifact_fingerprint,
            challenger_calibration_artifact_set_id=challenger.calibration_artifact_set_id,
            challenger_calibration_artifact_set_fingerprint=challenger.calibration_artifact_set_fingerprint,
            challenger_runtime_policy_version="probability-calibration-v1",
            model_input_vector_id=snapshot.model_input_vector_id,
            model_input_fingerprint=snapshot.model_input_fingerprint,
            match_id=snapshot.match_id,
            competition=snapshot.competition,
            kickoff_utc=kickoff,
            input_snapshot_timestamp_utc=snapshot.snapshot_timestamp_utc,
            feature_schema_version=snapshot.feature_schema_version,
            feature_schema_fingerprint=snapshot.feature_schema_fingerprint,
            feature_provenance_fingerprint=snapshot.feature_provenance_fingerprint,
            odds_snapshot_set_id=odds_set.odds_snapshot_set_id,
            odds_snapshot_set_fingerprint=odds_set.odds_snapshot_set_fingerprint,
            evaluation_timestamp_utc=evaluation_time,
        )
        inputs.append(snapshot)
        odds_sets.append(odds_set)
        commands.append(command)
    source = StaticShadowInputSource(tuple(inputs), tuple(odds_sets))
    evaluator = build_shadow_evaluation_service(
        database,
        source,
        migrate=False,
    )
    settler = build_shadow_settlement_service(database, migrate=False)
    for index, command in enumerate(commands):
        outcome = evaluator.run(command)
        settler.settle(
            ShadowSettlementCommand(
                settlement_request_id=f"lab-rehearsal-settlement-{index:02d}",
                shadow_execution_id=outcome.shadow_execution_id,
                shadow_execution_fingerprint=outcome.execution_fingerprint,
                match_id=command.match_id,
                final_home_score=1,
                final_away_score=0,
                settlement_timestamp_utc=datetime(
                    2026,
                    7,
                    16,
                    index // 2,
                    tzinfo=UTC,
                ),
                source_identity=FIXTURE_LABEL,
                source_version="v1",
                source_record_identity=f"lab-result-{index:02d}",
                source_fingerprint=sha256_fingerprint(
                    (FIXTURE_LABEL, "result", index)
                ),
            )
        )


def _odds_set(identity, match_id, timestamp, kickoff):
    timestamp_text = timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
    kickoff_text = kickoff.astimezone(UTC).isoformat().replace("+00:00", "Z")
    snapshots = []
    for order, (market, value) in enumerate(
        (("HOME_WIN", "2.20"), ("DRAW", "3.50"), ("OVER_2_5", "2.00"))
    ):
        material = {
            "source_identity": FIXTURE_LABEL,
            "source_version": "v1",
            "source_record_identity": f"{identity}-{market}",
            "match_id": match_id,
            "market_identity": market,
            "selection_identity": market,
            "bookmaker_identity": "LAB_BOOK",
            "decimal_odds": Decimal(value),
            "market_status": "ACTIVE",
            "snapshot_timestamp_utc": timestamp_text,
            "kickoff_utc": kickoff_text,
        }
        snapshots.append(
            ShadowOddsSnapshot(
                odds_snapshot_id=f"{identity}-odds-{order}",
                source_identity=FIXTURE_LABEL,
                source_version="v1",
                source_record_identity=f"{identity}-{market}",
                source_fingerprint=shadow_sha256_fingerprint(material),
                match_id=match_id,
                market_identity=market,
                selection_identity=market,
                bookmaker_identity="LAB_BOOK",
                decimal_odds=Decimal(value),
                market_status="ACTIVE",
                snapshot_timestamp_utc=timestamp,
                kickoff_utc=kickoff,
            )
        )
    fingerprint = shadow_sha256_fingerprint(
        tuple(item.source_fingerprint for item in snapshots)
    )
    return ShadowOddsSnapshotSet(
        odds_snapshot_set_id=f"{identity}-odds-set",
        odds_snapshot_set_fingerprint=fingerprint,
        snapshots=tuple(snapshots),
    )
