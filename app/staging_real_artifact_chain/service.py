"""Compose the real historical ML and evidence services for staging."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256 as hashlib_sha256

from app.database import Database, MigrationManager
from app.historical_backtesting import (
    BacktestStatus,
    HistoricalBacktestCommand,
    HistoricalOddsSnapshot,
    OddsMarketStatus,
    SQLiteHistoricalBacktestingRepository,
    SupportedMarket,
    build_historical_backtesting_service,
    create_odds_dataset,
    odds_source_fingerprint,
)
from app.historical_backtesting.prediction_loader import reproduce_predictions
from app.historical_data_import import (
    HISTORICAL_DATASET_SCHEMA,
    HistoricalDataset,
    HistoricalMatchInput,
    HistoricalTeamStatisticsInput,
    build_historical_match_importer,
)
from app.historical_dataset_split import (
    DatasetSplitCommand,
    DatasetSplitStatus,
    ExplicitTimeBoundaries,
    GapConfiguration,
    MinimumPartitionSizes,
    Partition,
    RatioByChronology,
    SQLiteHistoricalDatasetSplitRepository,
    SplitStrategy,
    build_historical_dataset_split_service,
)
from app.historical_model_training import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_FINGERPRINT,
    EstimatorConfiguration,
    HistoricalModelTrainingCommand,
    SQLiteHistoricalModelTrainingRepository,
    TrainingStatus,
    build_historical_model_training_service,
)
from app.historical_probability_calibration import (
    CalibrationMethod,
    CalibrationStatus,
    DEFAULT_HISTORICAL_CALIBRATION_POLICY,
    HistoricalCalibrationCommand,
    SQLiteHistoricalProbabilityCalibrationRepository,
    build_historical_probability_calibration_service,
)
from app.historical_training_dataset import (
    DatasetBuildCommand,
    DatasetBuildStatus,
    SQLiteHistoricalTrainingDatasetRepository,
    build_historical_training_dataset_service,
)
from app.model_activation import ActivationRequest, RuntimeArtifactReference
from app.model_activation.evidence import build_activation_evidence
from app.model_comparison_promotion import (
    ChallengerCandidate,
    ComparisonScope,
    ComparisonStatus,
    ModelComparisonCommand,
    Recommendation,
    SQLiteModelComparisonRepository,
    build_model_comparison_promotion_service,
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
    sha256_fingerprint,
)

from .models import (
    CHAIN_SCHEMA_VERSION,
    CONTROLLED_SOURCE_LABEL,
    RealArtifactChainManifest,
)


UTC = timezone.utc
BASE_KICKOFF = datetime(2022, 1, 1, 12, tzinfo=UTC)
IMPORT_AT = datetime(2026, 7, 1, 10, tzinfo=UTC)
BUILD_AT = datetime(2026, 7, 1, 11, tzinfo=UTC)
SPLIT_AT = datetime(2026, 7, 1, 12, tzinfo=UTC)
TRAIN_AT = datetime(2026, 7, 1, 13, tzinfo=UTC)
CALIBRATE_AT = datetime(2026, 7, 1, 14, tzinfo=UTC)
BACKTEST_AT = datetime(2026, 7, 1, 15, tzinfo=UTC)
COMPARE_AT = datetime(2026, 7, 1, 16, tzinfo=UTC)
EVIDENCE_CUTOFF = datetime(2026, 8, 1, 12, tzinfo=UTC)


class RealArtifactChainError(RuntimeError):
    """A genuine staging chain failed closed."""


def build_real_artifact_chain(database: Database) -> RealArtifactChainManifest:
    """Build every artifact through its production domain service."""
    MigrationManager(database.connection).migrate()
    imported = _import_history(database)
    dataset = _build_dataset(database, imported.import_id)
    (
        champion_split_outcome,
        champion_split,
        champion_fold,
        split_outcome,
        split,
        fold,
    ) = _split_dataset(database, dataset)
    champion_training = _train(
        database,
        champion_split,
        champion_fold,
        request_id="controlled-staging-champion-training-v1",
        name="Controlled staging conservative champion",
        estimator=EstimatorConfiguration(
            convergence_tolerance=Decimal("0.001"),
        ),
    )
    challenger_training = _train(
        database,
        split,
        fold,
        request_id="controlled-staging-challenger-training-v1",
        name="Controlled staging fully fitted challenger",
        estimator=EstimatorConfiguration(
            convergence_tolerance=Decimal("0.001"),
        ),
    )
    champion_calibration = _calibrate(
        database,
        champion_split,
        champion_fold,
        champion_training,
        "controlled-staging-champion-calibration-v1",
        CalibrationMethod.ISOTONIC_REGRESSION_V1,
    )
    challenger_calibration = _calibrate(
        database,
        split,
        fold,
        challenger_training,
        "controlled-staging-challenger-calibration-v1",
        CalibrationMethod.PLATT_SCALING_V1,
    )
    examples = _partition_examples(database, fold.fold_id, Partition.TEST)
    odds = _historical_odds(
        examples,
        champion_training,
        champion_calibration,
        challenger_training,
        challenger_calibration,
    )
    champion_backtest = _backtest(
        database,
        champion_split,
        champion_fold,
        champion_training,
        champion_calibration,
        odds,
        "controlled-staging-champion-backtest-v1",
    )
    challenger_backtest = _backtest(
        database,
        split,
        fold,
        challenger_training,
        challenger_calibration,
        odds,
        "controlled-staging-challenger-backtest-v1",
    )
    comparison, evaluation, recommendation = _compare(
        database,
        champion_training,
        champion_calibration,
        champion_backtest,
        challenger_training,
        challenger_calibration,
        challenger_backtest,
    )
    champion = _runtime_reference(champion_training, champion_calibration)
    challenger = _runtime_reference(challenger_training, challenger_calibration)
    evidence = _shadow(
        database,
        examples,
        champion,
        challenger,
        comparison,
        evaluation,
        recommendation,
    )
    values = dict(
        schema_version=CHAIN_SCHEMA_VERSION,
        label=CONTROLLED_SOURCE_LABEL,
        model_scope="OFFICIAL_GLOBAL",
        source_import_id=imported.import_id,
        source_dataset_fingerprint=imported.dataset_fingerprint,
        source_match_count=imported.supplied_match_count,
        dataset_build_id=dataset.dataset_build_id,
        dataset_fingerprint=dataset.dataset_fingerprint,
        included_example_count=dataset.included_examples,
        split_id=split.split_id,
        split_fingerprint=split.split_fingerprint,
        fold_id=fold.fold_id,
        fold_fingerprint=fold.fold_fingerprint,
        train_count=split_outcome.train_count,
        validation_count=split_outcome.validation_count,
        test_count=split_outcome.test_count,
        champion_training_run_id=champion_training.training_run_id,
        challenger_training_run_id=challenger_training.training_run_id,
        champion=champion,
        challenger=challenger,
        champion_calibration_run_id=champion_calibration.calibration_run_id,
        challenger_calibration_run_id=challenger_calibration.calibration_run_id,
        champion_backtest_run_id=champion_backtest.backtest_run_id,
        challenger_backtest_run_id=challenger_backtest.backtest_run_id,
        champion_backtest_fingerprint=champion_backtest.backtest_run_fingerprint,
        challenger_backtest_fingerprint=challenger_backtest.backtest_run_fingerprint,
        comparison_run_id=comparison.comparison_run_id,
        comparison_run_fingerprint=comparison.comparison_run_fingerprint,
        challenger_candidate_id=evaluation.candidate.challenger_candidate_id,
        recommendation_id=recommendation.recommendation_id,
        recommendation_fingerprint=recommendation.recommendation_fingerprint,
        promotion_recommendation=evaluation.recommendation.value,
        promotion_score=str(evaluation.promotion_score),
        evidence_cutoff_timestamp_utc=_utc(EVIDENCE_CUTOFF),
        shadow_evidence_fingerprint=evidence.evidence_fingerprint,
        settled_shadow_count=evidence.settled_count,
        observation_days=str(evidence.observation_days),
        chain_fingerprint="",
    )
    fingerprint = sha256_fingerprint(values)
    return RealArtifactChainManifest(**{**values, "chain_fingerprint": fingerprint})


def _import_history(database):
    result = build_historical_match_importer(database, migrate=False).import_dataset(
        HistoricalDataset(
            schema_version=HISTORICAL_DATASET_SCHEMA,
            provider=CONTROLLED_SOURCE_LABEL,
            dataset_id="controlled-staging-history-v1",
            dataset_version="v1",
            matches=_source_matches(),
        ),
        import_timestamp=IMPORT_AT,
    )
    if result.supplied_match_count != 1200:
        raise RealArtifactChainError("Controlled historical import is incomplete.")
    return result


def _source_matches() -> tuple[HistoricalMatchInput, ...]:
    schedule = (
        (("Alpha", "Delta", 1, 0), ("Bravo", "Charlie", 1, 0)),
        (("Delta", "Alpha", 0, 1), ("Charlie", "Bravo", 0, 0)),
        (("Alpha", "Bravo", 2, 2), ("Charlie", "Delta", 2, 1)),
        (("Bravo", "Alpha", 0, 1), ("Delta", "Charlie", 1, 2)),
        (("Alpha", "Charlie", 4, 1), ("Bravo", "Delta", 2, 0)),
        (("Charlie", "Alpha", 0, 3), ("Delta", "Bravo", 1, 1)),
    )
    matches = []
    fixtures = tuple(item for pair in schedule for item in pair)
    for day in range(1200):
        home, away, home_score, away_score = fixtures[day % len(fixtures)]
        noise = hashlib_sha256(
            f"{CONTROLLED_SOURCE_LABEL}:{day}".encode("utf-8")
        ).digest()
        if day < 240:
            result = (
                "HOME"
                if home_score > away_score
                else "AWAY"
                if away_score > home_score
                else "DRAW"
            )
            high_total = home_score + away_score >= 2
            if high_total:
                home_score, away_score = {
                    "HOME": (0, 1),
                    "AWAY": (1, 0),
                    "DRAW": (0, 0),
                }[result]
            else:
                home_score, away_score = {
                    "HOME": (0, 4),
                    "AWAY": (4, 0),
                    "DRAW": (2, 2),
                }[result]
        elif noise[0] < 90:
            home_score, away_score = (
                (0, 0),
                (1, 0),
                (0, 1),
                (3, 2),
                (2, 2),
                (4, 0),
            )[noise[1] % 6]
        seed = day
        home_possession = 44 + seed % 13
        matches.append(
            HistoricalMatchInput(
                    source_match_id=f"controlled-staging-match-{day:03d}",
                    competition=(
                        "Controlled Staging League A"
                        if day % 2 == 0
                        else "Controlled Staging League B"
                    ),
                    season=(
                        "2024/25"
                        if day % 2 == 0
                        else "2025/26"
                    ),
                    round=f"Round {day + 1}",
                    kickoff_utc=BASE_KICKOFF + timedelta(days=day),
                    home_team=home,
                    away_team=away,
                    full_time_home_score=home_score,
                    full_time_away_score=away_score,
                    full_time_result=(
                        "H"
                        if home_score > away_score
                        else "D"
                        if home_score == away_score
                        else "A"
                    ),
                    venue=f"{home} Controlled Ground",
                    home_statistics=_statistics(seed, home_possession, home_score),
                    away_statistics=_statistics(seed + 1, 100 - home_possession, away_score),
            )
        )
    return tuple(matches)


def _statistics(seed: int, possession: int, goals: int):
    shots_on_target = 2 + goals + seed % 3
    return HistoricalTeamStatisticsInput(
        possession=str(possession),
        shots=shots_on_target + 4 + seed % 5,
        shots_on_target=shots_on_target,
        expected_goals=str(Decimal("0.40") + Decimal(goals) * Decimal("0.65")),
        corners=2 + seed % 7,
        yellow_cards=seed % 4,
        red_cards=0,
        fouls=7 + seed % 8,
        offsides=seed % 4,
    )


def _build_dataset(database, import_id):
    result = build_historical_training_dataset_service(
        database, migrate=False
    ).build(
        DatasetBuildCommand(
            request_id="controlled-staging-dataset-build-v1",
            dataset_name="Controlled synthetic staging training dataset",
            source_import_ids=(import_id,),
            competition_filters=(
                "Controlled Staging League A",
                "Controlled Staging League B",
            ),
            season_filters=("2024/25", "2025/26"),
            kickoff_lower_bound=BASE_KICKOFF + timedelta(days=12),
            kickoff_upper_bound=BASE_KICKOFF + timedelta(days=1200),
            build_timestamp=BUILD_AT,
        )
    )
    if result.status not in {
        DatasetBuildStatus.DATASET_BUILT,
        DatasetBuildStatus.IDEMPOTENT_EXISTING,
    }:
        raise RealArtifactChainError(f"Dataset build failed: {result.status.value}")
    return result


def _split_dataset(database, dataset):
    service = build_historical_dataset_split_service(database, migrate=False)
    common = dict(
        source_dataset_build_id=dataset.dataset_build_id,
        source_dataset_fingerprint=dataset.dataset_fingerprint,
        strategy=SplitStrategy.EXPLICIT_TIME_BOUNDARIES_V1,
        minimum_partition_sizes=MinimumPartitionSizes(40, 40, 100),
        split_timestamp=SPLIT_AT,
    )
    champion_outcome = service.create(
        DatasetSplitCommand(
            split_request_id="controlled-staging-champion-split-v1",
            split_name="Controlled old-regime champion chronological split",
            explicit_boundaries=ExplicitTimeBoundaries(
                BASE_KICKOFF + timedelta(days=160),
                BASE_KICKOFF + timedelta(days=160),
                BASE_KICKOFF + timedelta(days=240),
                BASE_KICKOFF + timedelta(days=900),
                None,
            ),
            gaps=GapConfiguration(0, 660),
            **common,
        )
    )
    outcome = service.create(
        DatasetSplitCommand(
            split_request_id="controlled-staging-challenger-split-v1",
            split_name="Controlled current-regime challenger chronological split",
            explicit_boundaries=ExplicitTimeBoundaries(
                BASE_KICKOFF + timedelta(days=700),
                BASE_KICKOFF + timedelta(days=700),
                BASE_KICKOFF + timedelta(days=900),
                BASE_KICKOFF + timedelta(days=900),
                None,
            ),
            **common,
        )
    )
    allowed = {
        DatasetSplitStatus.SPLIT_CREATED,
        DatasetSplitStatus.IDEMPOTENT_EXISTING,
    }
    if champion_outcome.status not in allowed or outcome.status not in allowed:
        raise RealArtifactChainError(
            "One or both chronological dataset splits failed."
        )
    repository = SQLiteHistoricalDatasetSplitRepository(database, migrate=False)
    champion_split = repository.load_dataset_split(champion_outcome.split_id)
    split = repository.load_dataset_split(outcome.split_id)
    return (
        champion_outcome,
        champion_split,
        champion_split.folds[0],
        outcome,
        split,
        split.folds[0],
    )


def _train(database, split, fold, request_id, name, estimator):
    outcome = build_historical_model_training_service(
        database, migrate=False
    ).train(
        HistoricalModelTrainingCommand(
            training_request_id=request_id,
            training_run_name=name,
            source_split_id=split.split_id,
            source_split_fingerprint=split.split_fingerprint,
            fold_id=fold.fold_id,
            fold_fingerprint=fold.fold_fingerprint,
            feature_schema_fingerprint=FEATURE_SCHEMA_FINGERPRINT,
            ordered_feature_names=FEATURE_NAMES,
            estimator=estimator,
            training_timestamp=TRAIN_AT,
            environment_metadata_version=CONTROLLED_SOURCE_LABEL,
        )
    )
    if outcome.status not in {
        TrainingStatus.MODEL_TRAINED,
        TrainingStatus.IDEMPOTENT_EXISTING,
    }:
        raise RealArtifactChainError(
            f"Historical training failed: {outcome.status.value}"
        )
    return SQLiteHistoricalModelTrainingRepository(
        database, migrate=False
    ).load_training_run(outcome.training_run_id)


def _calibrate(database, split, fold, training, request_id, method):
    artifact = training.artifact
    policy = (
        replace(
            DEFAULT_HISTORICAL_CALIBRATION_POLICY,
            allow_identity_calibration=True,
        )
        if method is CalibrationMethod.IDENTITY_V1
        else DEFAULT_HISTORICAL_CALIBRATION_POLICY
    )
    outcome = build_historical_probability_calibration_service(
        database, policy=policy, migrate=False
    ).fit(
        HistoricalCalibrationCommand(
            calibration_request_id=request_id,
            calibration_run_name=request_id,
            source_training_run_id=training.training_run_id,
            source_training_run_fingerprint=training.training_run_fingerprint,
            source_model_artifact_id=artifact.artifact_id,
            source_model_artifact_fingerprint=artifact.artifact_fingerprint,
            source_split_id=split.split_id,
            source_split_fingerprint=split.split_fingerprint,
            fold_id=fold.fold_id,
            fold_fingerprint=fold.fold_fingerprint,
            feature_schema_fingerprint=FEATURE_SCHEMA_FINGERPRINT,
            match_result_method=method,
            totals_method=method,
            btts_method=method,
            calibration_timestamp=CALIBRATE_AT,
            environment_metadata_version=CONTROLLED_SOURCE_LABEL,
        )
    )
    if outcome.status not in {
        CalibrationStatus.CALIBRATION_FITTED,
        CalibrationStatus.IDEMPOTENT_EXISTING,
    }:
        raise RealArtifactChainError(
            f"Historical calibration failed: {outcome.status.value} "
            + ",".join(outcome.ordered_reason_codes)
        )
    return SQLiteHistoricalProbabilityCalibrationRepository(
        database, migrate=False
    ).load_calibration_run(outcome.calibration_run_id)


def _partition_examples(database, fold_id, partition):
    split_repository = SQLiteHistoricalDatasetSplitRepository(database, migrate=False)
    training_repository = SQLiteHistoricalTrainingDatasetRepository(
        database, migrate=False
    )
    return tuple(
        training_repository.load_training_example(item.training_example_id)
        for item in split_repository.list_assignments_by_partition(
            fold_id, partition
        )
    )


def _historical_odds(
    examples,
    champion_training,
    champion_calibration,
    challenger_training,
    challenger_calibration,
):
    snapshots = []
    predictions = reproduce_predictions(
        examples,
        challenger_training.artifact,
        challenger_calibration.artifact_set,
        run_namespace="controlled-staging-odds-market-maker-v1",
    )
    champion_predictions = reproduce_predictions(
        examples,
        champion_training.artifact,
        champion_calibration.artifact_set,
        run_namespace="controlled-staging-odds-champion-reference-v1",
    )
    probability_buckets = (
        (Decimal("0.50"), Decimal("0.60")),
        (Decimal("0.60"), Decimal("0.70")),
        (Decimal("0.70"), Decimal("0.80")),
        (Decimal("0.80"), Decimal("1.01")),
    )
    desired_edges = (
        Decimal("0.03"),
        Decimal("0.075"),
        Decimal("0.13"),
        Decimal("0.18"),
    )
    for example_index, (example, prediction, champion_prediction) in enumerate(
        zip(examples, predictions, champion_predictions)
    ):
        kickoff = datetime.fromisoformat(
            example.kickoff_utc.replace("Z", "+00:00")
        )
        lower, upper = probability_buckets[
            example_index % len(probability_buckets)
        ]
        probabilities = prediction.calibrated_probabilities.ordered_probabilities
        champion_probabilities = {
            item.target: item.probability
            for item in champion_prediction.calibrated_probabilities.ordered_probabilities
        }
        candidates = tuple(
            item
            for item in probabilities
            if lower <= item.probability < upper
            and champion_probabilities[item.target] >= Decimal("0.20")
            and abs(
                item.probability - champion_probabilities[item.target]
            )
            <= Decimal("0.02")
        )
        if candidates:
            ranked_candidates = sorted(
                candidates,
                key=lambda item: (
                    abs(item.probability - champion_probabilities[item.target]),
                    item.target.value,
                ),
            )
            retained = ranked_candidates[: min(3, len(ranked_candidates))]
            selected_probability = retained[example_index % len(retained)]
        else:
            midpoint = (lower + min(upper, Decimal(1))) / Decimal(2)
            mutually_supported = tuple(
                item
                for item in probabilities
                if champion_probabilities[item.target] >= Decimal("0.20")
            )
            selected_probability = min(
                mutually_supported or probabilities,
                key=lambda item: (
                    abs(item.probability - midpoint),
                    abs(
                        item.probability
                        - champion_probabilities[item.target]
                    ),
                    item.target.value,
                ),
            )
        market = SupportedMarket(selected_probability.target.value)
        desired_edge = desired_edges[example_index % len(desired_edges)]
        pricing_probability = min(
            selected_probability.probability,
            champion_probabilities[selected_probability.target],
        )
        price = max(
            Decimal("1.60"),
            ((Decimal(1) + desired_edge) / pricing_probability).quantize(
                Decimal("0.0001"),
                rounding=ROUND_CEILING,
            ),
        )
        price = min(price, Decimal("10.00"))
        row = HistoricalOddsSnapshot(
            odds_snapshot_id=(
                f"controlled-odds-{example.historical_match_id}-{market.value}"
            ),
            source_identity=CONTROLLED_SOURCE_LABEL,
            source_version="v1",
            historical_match_id=example.historical_match_id,
            competition=example.competition,
            kickoff_utc=example.kickoff_utc,
            snapshot_timestamp_utc=kickoff - timedelta(hours=2),
            bookmaker_identity="CONTROLLED_STAGING_MODEL_MARKET_MAKER",
            market_identity=market,
            selection_identity=market.value,
            decimal_odds=price,
            currency="EUR",
            market_status=OddsMarketStatus.ACTIVE,
            source_record_identity=(
                f"controlled-record-{example.historical_match_id}-{market.value}"
            ),
            source_fingerprint="0" * 64,
        )
        snapshots.append(
            replace(row, source_fingerprint=odds_source_fingerprint(row))
        )
    return create_odds_dataset("controlled-staging-test-odds-v1", tuple(snapshots))


def _backtest(database, split, fold, training, calibration, odds, request_id):
    artifact = training.artifact
    artifact_set = calibration.artifact_set
    outcome = build_historical_backtesting_service(
        database, migrate=False
    ).run(
        HistoricalBacktestCommand(
            backtest_request_id=request_id,
            backtest_run_name=request_id,
            source_split_id=split.split_id,
            source_split_fingerprint=split.split_fingerprint,
            fold_id=fold.fold_id,
            fold_fingerprint=fold.fold_fingerprint,
            source_training_run_id=training.training_run_id,
            source_training_run_fingerprint=training.training_run_fingerprint,
            model_artifact_id=artifact.artifact_id,
            model_artifact_fingerprint=artifact.artifact_fingerprint,
            calibration_run_id=calibration.calibration_run_id,
            calibration_run_fingerprint=calibration.calibration_run_fingerprint,
            calibration_artifact_set_id=artifact_set.artifact_set_id,
            calibration_artifact_set_fingerprint=(
                artifact_set.artifact_set_fingerprint
            ),
            odds_dataset_id=odds.odds_dataset_id,
            odds_dataset_fingerprint=odds.odds_dataset_fingerprint,
            initial_bankroll=Decimal("10000"),
            backtest_timestamp=BACKTEST_AT,
            environment_metadata_version=CONTROLLED_SOURCE_LABEL,
        ),
        odds_dataset=odds,
    )
    if outcome.status not in {
        BacktestStatus.BACKTEST_COMPLETED,
        BacktestStatus.IDEMPOTENT_EXISTING,
    }:
        raise RealArtifactChainError(
            f"Historical TEST backtest failed: {outcome.status.value} "
            + ",".join(outcome.ordered_reason_codes)
        )
    return SQLiteHistoricalBacktestingRepository(
        database, migrate=False
    ).load_backtest_run(outcome.backtest_run_id)


def _compare(
    database,
    champion_training,
    champion_calibration,
    champion_backtest,
    challenger_training,
    challenger_calibration,
    challenger_backtest,
):
    candidate = ChallengerCandidate(
        challenger_candidate_id="controlled-staging-challenger-v1",
        model_artifact_id=challenger_training.artifact.artifact_id,
        model_artifact_fingerprint=challenger_training.artifact.artifact_fingerprint,
        calibration_artifact_set_id=(
            challenger_calibration.artifact_set.artifact_set_id
        ),
        calibration_artifact_set_fingerprint=(
            challenger_calibration.artifact_set.artifact_set_fingerprint
        ),
        backtest_run_id=challenger_backtest.backtest_run_id,
        backtest_run_fingerprint=challenger_backtest.backtest_run_fingerprint,
        label="Genuine controlled staging challenger",
    )
    outcome = build_model_comparison_promotion_service(
        database, migrate=False
    ).compare(
        ModelComparisonCommand(
            comparison_request_id="controlled-staging-comparison-v1",
            comparison_run_name="Controlled genuine champion/challenger comparison",
            champion_model_artifact_id=champion_training.artifact.artifact_id,
            champion_model_artifact_fingerprint=(
                champion_training.artifact.artifact_fingerprint
            ),
            champion_calibration_artifact_set_id=(
                champion_calibration.artifact_set.artifact_set_id
            ),
            champion_calibration_artifact_set_fingerprint=(
                champion_calibration.artifact_set.artifact_set_fingerprint
            ),
            champion_backtest_run_id=champion_backtest.backtest_run_id,
            champion_backtest_run_fingerprint=(
                champion_backtest.backtest_run_fingerprint
            ),
            challengers=(candidate,),
            scope=ComparisonScope(
                comparison_scope_version="comparison-scope-v1",
            ),
            comparison_timestamp=COMPARE_AT,
            environment_metadata_version=CONTROLLED_SOURCE_LABEL,
        )
    )
    if outcome.status not in {
        ComparisonStatus.COMPARISON_COMPLETED,
        ComparisonStatus.IDEMPOTENT_EXISTING,
    }:
        raise RealArtifactChainError(
            f"Model comparison failed: {outcome.status.value}"
        )
    repository = SQLiteModelComparisonRepository(database, migrate=False)
    comparison = repository.load_comparison_run(outcome.comparison_run_id)
    evaluation = comparison.evaluations[0]
    if (
        comparison.final_recommendation is not Recommendation.PROMOTE_CHALLENGER
        or evaluation.recommendation is not Recommendation.PROMOTE_CHALLENGER
    ):
        failed = tuple(
            item.gate_name
            for item in evaluation.gate_evaluations
            if item.status.value != "PASS"
        )
        raise RealArtifactChainError(
            "Default promotion policy did not approve the genuine challenger: "
            f"recommendation={evaluation.recommendation.value};"
            f"score={evaluation.promotion_score};failed={failed}"
        )
    recommendation = next(
        item
        for item in repository.list_recommendations(comparison.comparison_run_id)
        if item.recommendation_scope == "CHALLENGER"
    )
    return comparison, evaluation, recommendation


def _runtime_reference(training, calibration):
    artifact = training.artifact
    artifact_set = calibration.artifact_set
    return RuntimeArtifactReference(
        model_artifact_id=artifact.artifact_id,
        model_artifact_fingerprint=artifact.artifact_fingerprint,
        preprocessing_fingerprint=artifact.preprocessing.preprocessing_fingerprint,
        calibration_artifact_set_id=artifact_set.artifact_set_id,
        calibration_artifact_set_fingerprint=(
            artifact_set.artifact_set_fingerprint
        ),
        feature_schema_version=artifact.feature_schema_version,
        feature_schema_fingerprint=artifact.feature_schema_fingerprint,
        target_contract_version=artifact.target_schema_version,
        probability_contract_version="canonical-11-target-contract-v1",
        runtime_compatibility_version="probability-calibration-v1",
    )


def _shadow(
    database,
    examples,
    champion,
    challenger,
    comparison,
    evaluation,
    recommendation,
):
    selected = examples[-30:]
    if len(selected) != 30:
        raise RealArtifactChainError("Thirty genuine TEST examples are required.")
    inputs = []
    odds_sets = []
    commands = []
    result_by_match = _historical_results(database, selected)
    first_kickoff = datetime.fromisoformat(
        selected[0].kickoff_utc.replace("Z", "+00:00")
    )
    for index, example in enumerate(selected):
        kickoff = datetime.fromisoformat(
            example.kickoff_utc.replace("Z", "+00:00")
        )
        snapshot_at = kickoff - timedelta(hours=3)
        evaluation_at = kickoff - timedelta(hours=2)
        model_input_fingerprint = sha256_fingerprint(
            (example.training_example_id, example.example_fingerprint, "shadow-input")
        )
        snapshot = fingerprint_input_snapshot(
            ShadowModelInputSnapshot(
                model_input_vector_id=(
                    f"controlled-shadow-input-{example.training_example_id}"
                ),
                model_input_fingerprint=model_input_fingerprint,
                match_id=example.historical_match_id,
                competition=example.competition,
                season=example.season,
                home_team=example.home_team_identity,
                away_team=example.away_team_identity,
                kickoff_utc=kickoff,
                snapshot_timestamp_utc=snapshot_at,
                feature_schema_version=example.feature_schema_version,
                feature_schema_fingerprint=champion.feature_schema_fingerprint,
                feature_provenance_fingerprint=sha256_fingerprint(
                    (
                        example.example_fingerprint,
                        example.feature_provenance,
                        example.historical_source_fingerprints,
                    )
                ),
                ordered_feature_names=FEATURE_NAMES,
                ordered_feature_values=example.ordered_feature_vector,
                missingness_mask=example.missingness_mask,
                ordered_missing_features=tuple(
                    name
                    for name, missing in zip(FEATURE_NAMES, example.missingness_mask)
                    if missing
                ),
                completeness_score=example.completeness_score,
                ordered_source_timestamps=tuple(
                    datetime.fromisoformat(
                        item.source_kickoff.replace("Z", "+00:00")
                    )
                    for item in example.sources
                ),
                input_snapshot_fingerprint="pending",
            )
        )
        odds_set = _shadow_odds(example, evaluation_at, kickoff)
        inputs.append(snapshot)
        odds_sets.append(odds_set)
        commands.append(
            ShadowEvaluationCommand(
                shadow_request_id=f"controlled-shadow-request-{index:02d}",
                shadow_run_name=CONTROLLED_SOURCE_LABEL,
                comparison_run_id=comparison.comparison_run_id,
                comparison_run_fingerprint=comparison.comparison_run_fingerprint,
                challenger_candidate_id=evaluation.candidate.challenger_candidate_id,
                recommendation_id=recommendation.recommendation_id,
                recommendation_fingerprint=(
                    recommendation.recommendation_fingerprint
                ),
                champion_model_artifact_id=champion.model_artifact_id,
                champion_model_artifact_fingerprint=(
                    champion.model_artifact_fingerprint
                ),
                champion_calibration_artifact_set_id=(
                    champion.calibration_artifact_set_id
                ),
                champion_calibration_artifact_set_fingerprint=(
                    champion.calibration_artifact_set_fingerprint
                ),
                champion_runtime_policy_version=(
                    champion.runtime_compatibility_version
                ),
                challenger_model_artifact_id=challenger.model_artifact_id,
                challenger_model_artifact_fingerprint=(
                    challenger.model_artifact_fingerprint
                ),
                challenger_calibration_artifact_set_id=(
                    challenger.calibration_artifact_set_id
                ),
                challenger_calibration_artifact_set_fingerprint=(
                    challenger.calibration_artifact_set_fingerprint
                ),
                challenger_runtime_policy_version=(
                    challenger.runtime_compatibility_version
                ),
                model_input_vector_id=snapshot.model_input_vector_id,
                model_input_fingerprint=snapshot.model_input_fingerprint,
                match_id=snapshot.match_id,
                competition=snapshot.competition,
                kickoff_utc=kickoff,
                input_snapshot_timestamp_utc=snapshot.snapshot_timestamp_utc,
                feature_schema_version=snapshot.feature_schema_version,
                feature_schema_fingerprint=snapshot.feature_schema_fingerprint,
                feature_provenance_fingerprint=(
                    snapshot.feature_provenance_fingerprint
                ),
                odds_snapshot_set_id=odds_set.odds_snapshot_set_id,
                odds_snapshot_set_fingerprint=(
                    odds_set.odds_snapshot_set_fingerprint
                ),
                evaluation_timestamp_utc=evaluation_at,
            )
        )
    evaluator = build_shadow_evaluation_service(
        database,
        StaticShadowInputSource(tuple(inputs), tuple(odds_sets)),
        migrate=False,
    )
    settler = build_shadow_settlement_service(database, migrate=False)
    for index, command in enumerate(commands):
        outcome = evaluator.run(command)
        home_score, away_score = result_by_match[command.match_id]
        settler.settle(
            ShadowSettlementCommand(
                settlement_request_id=f"controlled-shadow-settlement-{index:02d}",
                shadow_execution_id=outcome.shadow_execution_id,
                shadow_execution_fingerprint=outcome.execution_fingerprint,
                match_id=command.match_id,
                final_home_score=home_score,
                final_away_score=away_score,
                settlement_timestamp_utc=EVIDENCE_CUTOFF - timedelta(minutes=index),
                source_identity=CONTROLLED_SOURCE_LABEL,
                source_version="v1",
                source_record_identity=f"controlled-result-{command.match_id}",
                source_fingerprint=sha256_fingerprint(
                    (
                        CONTROLLED_SOURCE_LABEL,
                        command.match_id,
                        home_score,
                        away_score,
                    )
                ),
            )
        )
    request = ActivationRequest(
        activation_request_id="controlled-staging-evidence-preview-v1",
        activation_name=CONTROLLED_SOURCE_LABEL,
        model_scope="OFFICIAL_GLOBAL",
        current_champion_generation_id="not-yet-bootstrapped",
        current_champion_generation_fingerprint="not-yet-bootstrapped",
        current_champion=champion,
        challenger=challenger,
        comparison_run_id=comparison.comparison_run_id,
        comparison_run_fingerprint=comparison.comparison_run_fingerprint,
        challenger_candidate_id=evaluation.candidate.challenger_candidate_id,
        recommendation_id=recommendation.recommendation_id,
        recommendation_fingerprint=recommendation.recommendation_fingerprint,
        evidence_cutoff_timestamp_utc=EVIDENCE_CUTOFF,
        requested_timestamp_utc=EVIDENCE_CUTOFF,
        activation_reason=CONTROLLED_SOURCE_LABEL,
        operator_identity="controlled-staging-rehearsal",
    )
    evidence = build_activation_evidence(
        request, SQLiteShadowEvaluationRepository(database, migrate=False)
    )
    if evidence.settled_count != 30 or evidence.observation_days < 14:
        raise RealArtifactChainError("Shadow evidence is not activation-eligible.")
    return evidence


def _historical_results(database, examples):
    ids = tuple(item.historical_match_id for item in examples)
    placeholders = ",".join("?" for _ in ids)
    rows = database.connection.execute(
        f"""SELECT historical_match_id,full_time_home_score,full_time_away_score
            FROM historical_matches
            WHERE historical_match_id IN ({placeholders})""",
        ids,
    )
    return {row[0]: (row[1], row[2]) for row in rows}


def _shadow_odds(example, timestamp, kickoff):
    snapshots = []
    timestamp_text = _utc(timestamp)
    kickoff_text = _utc(kickoff)
    for market, value in (
        ("HOME_WIN", "1.01"),
        ("DRAW", "1.01"),
        ("AWAY_WIN", "1.01"),
        ("OVER_2_5", "1.01"),
    ):
        material = {
            "source_identity": CONTROLLED_SOURCE_LABEL,
            "source_version": "v1",
            "source_record_identity": (
                f"controlled-shadow-{example.historical_match_id}-{market}"
            ),
            "match_id": example.historical_match_id,
            "market_identity": market,
            "selection_identity": market,
            "bookmaker_identity": "CONTROLLED_STAGING_BOOK",
            "decimal_odds": Decimal(value),
            "market_status": "ACTIVE",
            "snapshot_timestamp_utc": timestamp_text,
            "kickoff_utc": kickoff_text,
        }
        snapshots.append(
            ShadowOddsSnapshot(
                odds_snapshot_id=(
                    f"controlled-shadow-odds-{example.historical_match_id}-{market}"
                ),
                source_identity=material["source_identity"],
                source_version=material["source_version"],
                source_record_identity=material["source_record_identity"],
                source_fingerprint=sha256_fingerprint(material),
                match_id=material["match_id"],
                market_identity=market,
                selection_identity=market,
                bookmaker_identity=material["bookmaker_identity"],
                decimal_odds=Decimal(value),
                market_status="ACTIVE",
                snapshot_timestamp_utc=timestamp,
                kickoff_utc=kickoff,
            )
        )
    fingerprint = sha256_fingerprint(
        tuple(item.source_fingerprint for item in snapshots)
    )
    return ShadowOddsSnapshotSet(
        f"controlled-shadow-odds-set-{example.historical_match_id}",
        fingerprint,
        tuple(snapshots),
    )


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
