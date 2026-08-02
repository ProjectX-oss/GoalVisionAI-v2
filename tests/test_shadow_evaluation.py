from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import unittest


class _TestAssertions:
    raises = unittest.TestCase().assertRaises


pytest = _TestAssertions()

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.prediction_inference import OFFICIAL_TARGET_ORDER, RawProbability, RawProbabilitySet
from app.shadow_evaluation import (
    DEFAULT_SHADOW_EVALUATION_POLICY,
    DisagreementSeverity,
    DisagreementType,
    ModelRole,
    PreMatchOutcome,
    ShadowComparison,
    ShadowEvaluationCommand,
    ShadowExecution,
    ShadowInference,
    ShadowMarketAssessment,
    ShadowModelInputSnapshot,
    ShadowOddsSnapshot,
    ShadowOddsSnapshotSet,
    ShadowSelection,
    ShadowSettlementCommand,
    ShadowValidationError,
    SQLiteShadowEvaluationRepository,
    evaluate_shadow_after_champion_candidate,
    fingerprint_input_snapshot,
    sha256_fingerprint,
)
from app.shadow_evaluation.decision_comparison import compare, select_one
from app.shadow_evaluation.market_comparison import assess_inference
from app.shadow_evaluation.outcome_tracking import build_settlement
from app.shadow_evaluation.probability_contract import verify_probability_contract
from app.shadow_evaluation.validation import validate_command, validate_input, validate_odds

UTC = timezone.utc


def probabilities(home="0.50", draw="0.25", away="0.25", over="0.60"):
    values = {
        "HOME_WIN": Decimal(home), "DRAW": Decimal(draw), "AWAY_WIN": Decimal(away),
        "OVER_1_5": Decimal("0.75"), "UNDER_1_5": Decimal("0.25"),
        "OVER_2_5": Decimal(over), "UNDER_2_5": Decimal(1) - Decimal(over),
        "OVER_3_5": Decimal("0.30"), "UNDER_3_5": Decimal("0.70"),
        "BTTS_YES": Decimal("0.55"), "BTTS_NO": Decimal("0.45"),
    }
    return RawProbabilitySet(tuple(RawProbability(target, values[target.value]) for target in OFFICIAL_TARGET_ORDER))


def command():
    return ShadowEvaluationCommand(
        shadow_request_id="request-1", shadow_run_name="Lab shadow",
        comparison_run_id="comparison-1", comparison_run_fingerprint="c" * 64,
        challenger_candidate_id="candidate-1", recommendation_id="recommendation-1",
        recommendation_fingerprint="r" * 64,
        champion_model_artifact_id="model-champion",
        champion_model_artifact_fingerprint="a" * 64,
        champion_calibration_artifact_set_id="cal-champion",
        champion_calibration_artifact_set_fingerprint="b" * 64,
        champion_runtime_policy_version="runtime-v1",
        challenger_model_artifact_id="model-challenger",
        challenger_model_artifact_fingerprint="d" * 64,
        challenger_calibration_artifact_set_id="cal-challenger",
        challenger_calibration_artifact_set_fingerprint="e" * 64,
        challenger_runtime_policy_version="runtime-v1",
        model_input_vector_id="input-1", model_input_fingerprint="f" * 64,
        match_id="match-1", competition="League",
        kickoff_utc=datetime(2026, 8, 1, 15, tzinfo=UTC),
        input_snapshot_timestamp_utc=datetime(2026, 8, 1, 12, tzinfo=UTC),
        feature_schema_version="schema-v1", feature_schema_fingerprint="1" * 64,
        feature_provenance_fingerprint="2" * 64,
        odds_snapshot_set_id="odds-1", odds_snapshot_set_fingerprint="3" * 64,
        evaluation_timestamp_utc=datetime(2026, 8, 1, 13, tzinfo=UTC),
    )


def input_snapshot():
    item = ShadowModelInputSnapshot(
        model_input_vector_id="input-1", model_input_fingerprint="f" * 64,
        match_id="match-1", competition="League", season="2026",
        home_team="Home", away_team="Away",
        kickoff_utc=datetime(2026, 8, 1, 15, tzinfo=UTC),
        snapshot_timestamp_utc=datetime(2026, 8, 1, 12, tzinfo=UTC),
        feature_schema_version="schema-v1", feature_schema_fingerprint="1" * 64,
        feature_provenance_fingerprint="2" * 64,
        ordered_feature_names=("one", "two"), ordered_feature_values=(Decimal("1"), None),
        missingness_mask=(False, True), ordered_missing_features=("two",),
        completeness_score=Decimal("0.5"),
        ordered_source_timestamps=(datetime(2026, 7, 31, tzinfo=UTC),),
        input_snapshot_fingerprint="pending",
    )
    return fingerprint_input_snapshot(item)


def odds_set():
    kickoff = datetime(2026, 8, 1, 15, tzinfo=UTC)
    timestamp = datetime(2026, 8, 1, 13, tzinfo=UTC)
    rows = []
    for market, odds in (("HOME_WIN", "2.20"), ("DRAW", "3.50"), ("OVER_2_5", "2.00")):
        core = {
            "source_identity": "supplied", "source_version": "v1",
            "source_record_identity": f"record-{market}", "match_id": "match-1",
            "market_identity": market, "selection_identity": market,
            "bookmaker_identity": "book", "decimal_odds": Decimal(odds),
            "market_status": "ACTIVE", "snapshot_timestamp_utc": "2026-08-01T13:00:00Z",
            "kickoff_utc": "2026-08-01T15:00:00Z",
        }
        rows.append(ShadowOddsSnapshot(
            odds_snapshot_id=f"odds-{market}", source_identity="supplied",
            source_version="v1", source_record_identity=f"record-{market}",
            source_fingerprint=sha256_fingerprint(core), match_id="match-1",
            market_identity=market, selection_identity=market,
            bookmaker_identity="book", decimal_odds=Decimal(odds),
            market_status="ACTIVE", snapshot_timestamp_utc=timestamp, kickoff_utc=kickoff,
        ))
    fingerprint = sha256_fingerprint(tuple(item.source_fingerprint for item in rows))
    return ShadowOddsSnapshotSet("odds-1", fingerprint, tuple(rows))


def inference(role, values=None):
    probs = values or probabilities()
    marker = role.value.lower()
    return ShadowInference(
        inference_id=f"inference-{marker}", model_role=role,
        model_artifact_id=f"model-{marker}", model_artifact_fingerprint=marker,
        calibration_artifact_set_id=f"cal-{marker}",
        calibration_artifact_set_fingerprint=marker, raw_probabilities=probs,
        calibrated_probabilities=probs, raw_inference_fingerprint=f"raw-{marker}",
        calibrated_inference_fingerprint=f"calibrated-{marker}",
        preprocessing_fingerprint=f"pre-{marker}",
        reconciliation_snapshot="{}", monotonicity_snapshot="{}",
    )


def test_command_and_input_fail_closed_on_timing_and_provenance():
    validate_command(command(), DEFAULT_SHADOW_EVALUATION_POLICY)
    snapshot = input_snapshot()
    validate_input(replace(command(), odds_snapshot_set_fingerprint=odds_set().odds_snapshot_set_fingerprint), snapshot)
    with pytest.raises(ShadowValidationError):
        validate_command(replace(command(), evaluation_timestamp_utc=command().kickoff_utc), DEFAULT_SHADOW_EVALUATION_POLICY)
    with pytest.raises(Exception):
        validate_input(command(), replace(snapshot, ordered_missing_features=()))


def test_odds_are_exact_pre_match_and_fingerprinted():
    supplied = odds_set()
    validate_odds(replace(command(), odds_snapshot_set_fingerprint=supplied.odds_snapshot_set_fingerprint), supplied)
    bad = replace(supplied.snapshots[0], snapshot_timestamp_utc=supplied.snapshots[0].kickoff_utc)
    with pytest.raises(Exception):
        validate_odds(replace(command(), odds_snapshot_set_fingerprint=supplied.odds_snapshot_set_fingerprint), replace(supplied, snapshots=(bad, *supplied.snapshots[1:])))


def test_probability_market_selection_and_disagreement_are_deterministic():
    supplied = odds_set()
    champion = inference(ModelRole.CHAMPION)
    challenger = inference(ModelRole.CHALLENGER, probabilities(home="0.48", draw="0.25", away="0.27", over="0.62"))
    verify_probability_contract(champion.calibrated_probabilities)
    champion_rows = assess_inference(champion, supplied, DEFAULT_SHADOW_EVALUATION_POLICY)
    challenger_rows = assess_inference(challenger, supplied, DEFAULT_SHADOW_EVALUATION_POLICY)
    assert len(champion_rows) == 11
    assert next(item for item in champion_rows if item.market_identity == "HOME_WIN").expected_value == Decimal("0.100")
    champion_pick = select_one(ModelRole.CHAMPION, champion_rows, DEFAULT_SHADOW_EVALUATION_POLICY)
    challenger_pick = select_one(ModelRole.CHALLENGER, challenger_rows, DEFAULT_SHADOW_EVALUATION_POLICY)
    assert champion_pick.market_identity == "OVER_2_5"
    assert challenger_pick.market_identity in {"HOME_WIN", "OVER_2_5"}
    comparison = compare(champion, challenger, champion_pick, challenger_pick, DEFAULT_SHADOW_EVALUATION_POLICY)
    assert comparison.disagreement_type in {DisagreementType.SAME_MARKET_DIFFERENT_PROBABILITY, DisagreementType.DIFFERENT_MARKET}
    assert comparison.maximum_probability_delta == Decimal("0.02")


def test_isolation_adapter_never_changes_or_blocks_champion():
    champion = object()
    disabled = evaluate_shadow_after_champion_candidate(champion)
    assert disabled.champion_candidate is champion and not disabled.attempted

    class Broken:
        def run(self, _):
            raise RuntimeError("challenger failure")

    observed = evaluate_shadow_after_champion_candidate(champion, service=Broken(), command=object(), enabled=True)
    assert observed.champion_candidate is champion
    assert observed.safe_error == "RuntimeError"


def test_v30_migration_creates_ten_immutable_tables():
    database = Database(":memory:")
    MigrationManager(database.connection).migrate()
    version = database.connection.execute("SELECT max(version) FROM schema_migrations").fetchone()[0]
    tables = database.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'shadow_evaluation_%'"
    ).fetchall()
    triggers = database.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'shadow_evaluation_%'"
    ).fetchall()
    assert version == 39
    assert len(tables) == 10
    assert len(triggers) == 20


def test_existing_v29_database_upgrades_to_v30_without_rewriting_history():
    database = Database(":memory:")
    connection = database.connection
    connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    for migration in MIGRATIONS[:29]:
        for statement in migration.statements:
            connection.execute(statement)
        connection.execute("INSERT INTO schema_migrations VALUES (?, 'prior')", (migration.version,))
    connection.commit()
    before = tuple(row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version"))
    MigrationManager(connection).migrate()
    after = tuple(row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version"))
    assert before == tuple(range(1, 30))
    assert after == tuple(range(1, 40))


def test_repository_replay_load_and_immutable_trigger():
    database = Database(":memory:")
    repository = SQLiteShadowEvaluationRepository(database)
    database.connection.execute("PRAGMA foreign_keys=OFF")
    supplied = odds_set()
    cmd = replace(command(), odds_snapshot_set_fingerprint=supplied.odds_snapshot_set_fingerprint)
    champion_inf = inference(ModelRole.CHAMPION)
    challenger_inf = inference(ModelRole.CHALLENGER)
    assessments = assess_inference(champion_inf, supplied, DEFAULT_SHADOW_EVALUATION_POLICY)
    challenger_assessments = assess_inference(challenger_inf, supplied, DEFAULT_SHADOW_EVALUATION_POLICY)
    champion_pick = select_one(ModelRole.CHAMPION, assessments, DEFAULT_SHADOW_EVALUATION_POLICY)
    challenger_pick = select_one(ModelRole.CHALLENGER, challenger_assessments, DEFAULT_SHADOW_EVALUATION_POLICY)
    comparison = compare(champion_inf, challenger_inf, champion_pick, challenger_pick, DEFAULT_SHADOW_EVALUATION_POLICY)
    execution = ShadowExecution(
        shadow_execution_id="execution-1", command=cmd,
        request_fingerprint=sha256_fingerprint(cmd), input_snapshot=input_snapshot(),
        odds_snapshot_set=supplied, inferences=(champion_inf, challenger_inf),
        market_assessments=(*assessments, *challenger_assessments),
        selections=(champion_pick, challenger_pick), comparison=comparison,
        metrics=(), aggregate_snapshots=(), exclusions=(),
        execution_fingerprint="execution-fingerprint", deterministic_snapshot="{}",
    )
    repository.append_shadow_evaluation(execution)
    repository.append_shadow_evaluation(execution)
    loaded = repository.load_shadow_execution("execution-1")
    assert loaded.execution_fingerprint == execution.execution_fingerprint
    assert loaded.selections == execution.selections
    assert loaded.market_assessments == execution.market_assessments
    assert len(repository.list_unsettled()) == 1
    with pytest.raises(Exception):
        database.connection.execute(
            "UPDATE shadow_evaluation_executions SET competition='Changed' WHERE shadow_execution_id='execution-1'"
        )


def test_explicit_settlement_is_hypothetical_and_has_no_bankroll():
    supplied = odds_set()
    cmd = replace(command(), odds_snapshot_set_fingerprint=supplied.odds_snapshot_set_fingerprint)
    champion_pick = ShadowSelection(
        "s1", ModelRole.CHAMPION, "a1", "HOME_WIN", Decimal(".5"), Decimal("2.2"),
        Decimal(".1"), PreMatchOutcome.EVALUATED, (), "sf1",
    )
    challenger_pick = ShadowSelection(
        "s2", ModelRole.CHALLENGER, None, None, None, None, None,
        PreMatchOutcome.NO_SELECTION, ("NO_ELIGIBLE_SINGLE",), "sf2",
    )
    comparison = ShadowComparison(
        "cmp", DisagreementType.CHAMPION_ONLY_SELECTION,
        DisagreementSeverity.HIGH,
        (), Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0),
        None, None, True, True, None, (), "cfp",
    )
    execution = ShadowExecution(
        "execution", cmd, "request-fp", input_snapshot(), supplied,
        (inference(ModelRole.CHAMPION), inference(ModelRole.CHALLENGER)), (),
        (champion_pick, challenger_pick), comparison, (), (), (),
        "execution-fp", "{}",
    )
    settlement = build_settlement(
        ShadowSettlementCommand(
            "settle-1", "execution", "execution-fp", "match-1", 2, 1,
            datetime(2026, 8, 1, 18, tzinfo=UTC), "result-source", "v1",
            "result-1", "result-fp",
        ),
        execution,
    )
    assert settlement.champion_outcome.value == "WON"
    assert settlement.champion_profit_per_unit == Decimal("1.2")
    assert settlement.challenger_outcome.value == "NO_SELECTION"
    assert not hasattr(settlement, "bankroll")


class ShadowEvaluationTests(unittest.TestCase):
    test_command_and_input_fail_closed_on_timing_and_provenance = staticmethod(
        test_command_and_input_fail_closed_on_timing_and_provenance
    )
    test_odds_are_exact_pre_match_and_fingerprinted = staticmethod(
        test_odds_are_exact_pre_match_and_fingerprinted
    )
    test_probability_market_selection_and_disagreement_are_deterministic = staticmethod(
        test_probability_market_selection_and_disagreement_are_deterministic
    )
    test_isolation_adapter_never_changes_or_blocks_champion = staticmethod(
        test_isolation_adapter_never_changes_or_blocks_champion
    )
    test_v30_migration_creates_ten_immutable_tables = staticmethod(
        test_v30_migration_creates_ten_immutable_tables
    )
    test_existing_v29_database_upgrades_to_v30_without_rewriting_history = staticmethod(
        test_existing_v29_database_upgrades_to_v30_without_rewriting_history
    )
    test_repository_replay_load_and_immutable_trigger = staticmethod(
        test_repository_replay_load_and_immutable_trigger
    )
    test_explicit_settlement_is_hypothetical_and_has_no_bankroll = staticmethod(
        test_explicit_settlement_is_hypothetical_and_has_no_bankroll
    )
