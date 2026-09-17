"""Atomic append-only SQLite persistence for complete comparison evidence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from decimal import Decimal

from app.database import Database, MigrationManager

from .exceptions import ComparisonConflictError, ComparisonPersistenceError
from .fingerprint import canonical_json, sha256_fingerprint
from .models import (
    ChallengerCandidate,
    ChallengerEvaluation,
    ComparisonExclusion,
    CompatibilityStatus,
    Direction,
    GateEvaluation,
    GateStatus,
    Materiality,
    MetricEvaluation,
    NormalizedComparisonCommand,
    NormalizedComparisonScope,
    PreparedComparisonRun,
    Recommendation,
    RecommendationRecord,
    ScoreComponent,
    SourceEvidence,
    StabilityGroup,
    StabilityStatus,
    StatisticalEvidence,
    UncertaintyClassification,
    ComparisonMode,
)


class SQLiteModelComparisonRepository:
    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def append_comparison_run(self, run: PreparedComparisonRun) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT request_fingerprint FROM model_comparison_runs WHERE comparison_request_id=?",
                (run.command.comparison_request_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != run.request_fingerprint:
                    raise ComparisonConflictError(
                        "Comparison request ID has different immutable content."
                    )
                self._connection.commit()
                return
            self._insert_run(run)
            candidate_rows = self._insert_candidates(run)
            self._insert_evidence(run, candidate_rows)
            self._insert_metrics(run, candidate_rows)
            self._insert_stability(run, candidate_rows)
            self._insert_statistics(run, candidate_rows)
            self._insert_gates(run, candidate_rows)
            self._insert_scores(run, candidate_rows)
            self._insert_recommendations(run, candidate_rows)
            self._insert_exclusions(run)
            self._connection.commit()
        except ComparisonConflictError:
            self._rollback()
            raise
        except sqlite3.DatabaseError as exc:
            self._rollback()
            raise ComparisonPersistenceError(
                f"Model comparison transaction failed: {exc}"
            ) from exc

    def find_by_comparison_run_fingerprint(self, fingerprint):
        row = self._connection.execute(
            "SELECT comparison_run_id FROM model_comparison_runs WHERE comparison_run_fingerprint=?",
            (fingerprint,),
        ).fetchone()
        return self.load_comparison_run(row[0]) if row else None

    def find_by_request_id(self, request_id):
        row = self._connection.execute(
            "SELECT comparison_run_id FROM model_comparison_runs WHERE comparison_request_id=?",
            (request_id,),
        ).fetchone()
        return self.load_comparison_run(row[0]) if row else None

    def load_comparison_run(self, comparison_run_id):
        row = self._connection.execute(
            "SELECT * FROM model_comparison_runs WHERE comparison_run_id=?",
            (comparison_run_id,),
        ).fetchone()
        if row is None:
            return None
        snapshot = json.loads(row["deterministic_run_snapshot"])
        command = _command(snapshot["command"])
        evaluations = []
        for candidate_row, candidate in self._candidate_rows(comparison_run_id):
            candidate_id = candidate_row["candidate_row_id"]
            statistics = self.list_statistical_evidence(
                comparison_run_id, candidate_id
            )
            evaluations.append(
                ChallengerEvaluation(
                    candidate=candidate,
                    source_compatibility_fingerprint=candidate_row[
                        "source_compatibility_fingerprint"
                    ],
                    evaluation_fingerprint=candidate_row["evaluation_fingerprint"],
                    shared_prediction_count=_shared_count(
                        self.list_gate_evaluations(comparison_run_id, candidate_id),
                        "MINIMUM_SHARED_PREDICTIONS",
                    ),
                    shared_selected_bet_count=_shared_count(
                        self.list_gate_evaluations(comparison_run_id, candidate_id),
                        "MINIMUM_SELECTED_BETS",
                    ),
                    source_evidence=self.list_source_evidence(
                        comparison_run_id, candidate_id
                    ),
                    metric_evaluations=self.list_metric_evaluations(
                        comparison_run_id, candidate_id
                    ),
                    stability_groups=self.list_stability_groups(
                        comparison_run_id, candidate_id
                    ),
                    statistical_evidence=statistics,
                    gate_evaluations=self.list_gate_evaluations(
                        comparison_run_id, candidate_id
                    ),
                    score_components=self.list_score_components(
                        comparison_run_id, candidate_id
                    ),
                    promotion_score=Decimal(candidate_row["promotion_score"]),
                    recommendation=Recommendation(candidate_row["recommendation"]),
                    deterministic_rank=candidate_row["deterministic_rank"],
                    reason_codes=tuple(
                        json.loads(candidate_row["reason_codes_snapshot"])
                    ),
                    exclusions=tuple(
                        item
                        for item in self.list_exclusions(comparison_run_id)
                        if item.challenger_candidate_id
                        == candidate.challenger_candidate_id
                    ),
                )
            )
        return PreparedComparisonRun(
            comparison_run_id=comparison_run_id,
            command=command,
            request_fingerprint=row["request_fingerprint"],
            comparison_run_fingerprint=row["comparison_run_fingerprint"],
            evaluations=tuple(evaluations),
            final_recommended_challenger_id=row[
                "final_recommended_challenger_id"
            ],
            final_recommendation=Recommendation(row["final_recommendation"]),
            reason_codes=tuple(json.loads(row["reason_codes_snapshot"])),
            exclusions=self.list_exclusions(comparison_run_id),
            deterministic_run_snapshot=row["deterministic_run_snapshot"],
        )

    def list_candidates(self, run_id):
        return tuple(candidate for _, candidate in self._candidate_rows(run_id))

    def _candidate_rows(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM model_comparison_candidates WHERE comparison_run_id=? ORDER BY deterministic_rank",
            (run_id,),
        ).fetchall()
        return tuple(
            (
                row,
                ChallengerCandidate(
                    challenger_candidate_id=row["challenger_candidate_id"],
                    model_artifact_id=row["model_artifact_id"],
                    model_artifact_fingerprint=row["model_artifact_fingerprint"],
                    calibration_artifact_set_id=row[
                        "calibration_artifact_set_id"
                    ],
                    calibration_artifact_set_fingerprint=row[
                        "calibration_artifact_set_fingerprint"
                    ],
                    backtest_run_id=row["backtest_run_id"],
                    backtest_run_fingerprint=row["backtest_run_fingerprint"],
                    label=row["challenger_label"],
                ),
            )
            for row in rows
        )

    def list_source_evidence(self, run_id, candidate_row_id=None):
        rows = self._rows(
            "model_comparison_source_evidence", run_id, candidate_row_id
        )
        return tuple(
            SourceEvidence(
                evidence_row_id=row["evidence_row_id"],
                category=row["evidence_category"],
                name=row["evidence_name"],
                champion_value_snapshot=row["champion_value_snapshot"],
                challenger_value_snapshot=row["challenger_value_snapshot"],
                compatibility_status=CompatibilityStatus(
                    row["compatibility_status"]
                ),
                detail_snapshot=row["detail_snapshot"],
                evidence_fingerprint=row["evidence_fingerprint"],
                deterministic_order=row["deterministic_order"],
            )
            for row in rows
        )

    def list_metric_evaluations(self, run_id, candidate_row_id=None):
        return tuple(
            MetricEvaluation(
                metric_evaluation_id=row["metric_evaluation_id"],
                category=row["category"],
                group_identity=row["group_identity"],
                metric_name=row["metric_name"],
                direction=Direction(row["direction"]),
                champion_value=_decimal(row["champion_value"]),
                challenger_value=_decimal(row["challenger_value"]),
                absolute_delta=_decimal(row["absolute_delta"]),
                relative_delta=_decimal(row["relative_delta"]),
                normalized_score=Decimal(row["normalized_score"]),
                materiality=Materiality(row["materiality"]),
                gate_status=GateStatus(row["gate_status"]),
                reason_codes=tuple(json.loads(row["reason_codes_snapshot"])),
                metric_fingerprint=row["metric_fingerprint"],
                deterministic_order=row["deterministic_order"],
            )
            for row in self._rows(
                "model_comparison_metric_evaluations", run_id, candidate_row_id
            )
        )

    def list_stability_groups(self, run_id, candidate_row_id=None):
        return tuple(
            StabilityGroup(
                stability_row_id=row["stability_row_id"],
                group_category=row["group_category"],
                group_identity=row["group_identity"],
                champion_sample_count=row["champion_sample_count"],
                challenger_sample_count=row["challenger_sample_count"],
                champion_metric_snapshot=row["champion_metric_snapshot"],
                challenger_metric_snapshot=row["challenger_metric_snapshot"],
                delta_snapshot=row["delta_snapshot"],
                stability_status=StabilityStatus(row["stability_status"]),
                concentration_evidence_snapshot=row[
                    "concentration_evidence_snapshot"
                ],
                stability_fingerprint=row["stability_fingerprint"],
                deterministic_order=row["deterministic_order"],
            )
            for row in self._rows(
                "model_comparison_stability_groups", run_id, candidate_row_id
            )
        )

    def list_statistical_evidence(self, run_id, candidate_row_id=None):
        return tuple(
            StatisticalEvidence(
                statistical_row_id=row["statistical_row_id"],
                evidence_name=row["evidence_name"],
                paired_sample_count=row["paired_sample_count"],
                deterministic_seed=row["deterministic_seed"],
                bootstrap_iterations=row["bootstrap_iterations"],
                effect_size=_decimal(row["effect_size"]),
                lower_confidence_bound=_decimal(row["lower_confidence_bound"]),
                upper_confidence_bound=_decimal(row["upper_confidence_bound"]),
                uncertainty_classification=UncertaintyClassification(
                    row["uncertainty_classification"]
                ),
                detail_snapshot=row["detail_snapshot"],
                evidence_fingerprint=row["evidence_fingerprint"],
                deterministic_order=row["deterministic_order"],
            )
            for row in self._rows(
                "model_comparison_statistical_evidence", run_id, candidate_row_id
            )
        )

    def list_gate_evaluations(self, run_id, candidate_row_id=None):
        return tuple(
            GateEvaluation(
                gate_evaluation_id=row["gate_evaluation_id"],
                gate_category=row["gate_category"],
                gate_name=row["gate_name"],
                mandatory=bool(row["mandatory_flag"]),
                status=GateStatus(row["status"]),
                champion_value_snapshot=row["champion_value_snapshot"],
                challenger_value_snapshot=row["challenger_value_snapshot"],
                threshold_snapshot=row["threshold_snapshot"],
                reason_codes=tuple(json.loads(row["reason_codes_snapshot"])),
                deterministic_order=row["deterministic_order"],
            )
            for row in self._rows(
                "model_comparison_gate_evaluations", run_id, candidate_row_id
            )
        )

    def list_score_components(self, run_id, candidate_row_id=None):
        return tuple(
            ScoreComponent(
                score_component_id=row["score_component_id"],
                score_category=row["score_category"],
                raw_score=Decimal(row["raw_score"]),
                normalized_score=Decimal(row["normalized_score"]),
                weight=Decimal(row["weight"]),
                weighted_contribution=Decimal(row["weighted_contribution"]),
                gate_status=GateStatus(row["gate_status"]),
                detail_snapshot=row["detail_snapshot"],
                deterministic_order=row["deterministic_order"],
            )
            for row in self._rows(
                "model_comparison_score_components", run_id, candidate_row_id
            )
        )

    def list_recommendations(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM model_comparison_recommendations WHERE comparison_run_id=? ORDER BY CASE recommendation_scope WHEN 'FINAL' THEN 1 ELSE 0 END,promotion_rank,recommendation_id",
            (run_id,),
        ).fetchall()
        return tuple(_recommendation(row) for row in rows)

    def list_exclusions(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM model_comparison_exclusions WHERE comparison_run_id=? ORDER BY deterministic_order",
            (run_id,),
        ).fetchall()
        return tuple(
            ComparisonExclusion(
                exclusion_id=row["exclusion_id"],
                challenger_candidate_id=row["challenger_candidate_id"],
                exclusion_stage=row["exclusion_stage"],
                exclusion_reason=row["exclusion_reason"],
                detail_snapshot=row["detail_snapshot"],
                deterministic_order=row["deterministic_order"],
            )
            for row in rows
        )

    def list_comparisons_for_champion_model(self, artifact_id):
        return self._list_runs(
            "SELECT comparison_run_id FROM model_comparison_runs WHERE champion_model_artifact_id=? ORDER BY comparison_timestamp,comparison_run_id",
            artifact_id,
        )

    def list_comparisons_for_challenger_model(self, artifact_id):
        return self._list_runs(
            "SELECT r.comparison_run_id FROM model_comparison_runs r JOIN model_comparison_candidates c ON c.comparison_run_id=r.comparison_run_id WHERE c.model_artifact_id=? ORDER BY r.comparison_timestamp,r.comparison_run_id",
            artifact_id,
        )

    def list_promotion_recommendations(self):
        rows = self._connection.execute(
            "SELECT * FROM model_comparison_recommendations WHERE recommendation='PROMOTE_CHALLENGER' ORDER BY created_timestamp,recommendation_id"
        ).fetchall()
        return tuple(_recommendation(row) for row in rows)

    def stream_comparison_events(self, run_id):
        tables = (
            ("CANDIDATE", "model_comparison_candidates", "candidate_row_id", "deterministic_rank"),
            ("SOURCE", "model_comparison_source_evidence", "evidence_row_id", "deterministic_order"),
            ("METRIC", "model_comparison_metric_evaluations", "metric_evaluation_id", "deterministic_order"),
            ("STABILITY", "model_comparison_stability_groups", "stability_row_id", "deterministic_order"),
            ("STATISTICAL", "model_comparison_statistical_evidence", "statistical_row_id", "deterministic_order"),
            ("GATE", "model_comparison_gate_evaluations", "gate_evaluation_id", "deterministic_order"),
            ("SCORE", "model_comparison_score_components", "score_component_id", "deterministic_order"),
            ("EXCLUSION", "model_comparison_exclusions", "exclusion_id", "deterministic_order"),
        )
        for event_type, table, identity, order in tables:
            cursor = self._connection.execute(
                f"SELECT {identity},{order} FROM {table} WHERE comparison_run_id=? ORDER BY {order}",
                (run_id,),
            )
            while True:
                rows = cursor.fetchmany(100)
                if not rows:
                    break
                for row in rows:
                    yield event_type, row[0], row[1]

    def _insert_run(self, run):
        c = run.command
        self._connection.execute(
            "INSERT INTO model_comparison_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run.comparison_run_id,
                c.comparison_request_id,
                run.request_fingerprint,
                run.comparison_run_fingerprint,
                c.champion_model_artifact_id,
                c.champion_model_artifact_fingerprint,
                c.champion_calibration_artifact_set_id,
                c.champion_calibration_artifact_set_fingerprint,
                c.champion_backtest_run_id,
                c.champion_backtest_run_fingerprint,
                canonical_json(c.scope),
                canonical_json(_policy_versions(c)),
                len(c.challengers),
                len(run.evaluations),
                run.final_recommended_challenger_id,
                run.final_recommendation.value,
                canonical_json(run.reason_codes),
                run.deterministic_run_snapshot,
                "COMPARISON_COMPLETED",
                c.comparison_timestamp,
                c.comparison_timestamp,
            ),
        )

    def _insert_candidates(self, run):
        result = {}
        for item in run.evaluations:
            candidate = item.candidate
            row_id = f"model-comparison-candidate-{sha256_fingerprint((run.comparison_run_id, candidate.challenger_candidate_id))}"
            result[candidate.challenger_candidate_id] = row_id
            self._connection.execute(
                "INSERT INTO model_comparison_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row_id,
                    run.comparison_run_id,
                    candidate.challenger_candidate_id,
                    candidate.label,
                    candidate.model_artifact_id,
                    candidate.model_artifact_fingerprint,
                    candidate.calibration_artifact_set_id,
                    candidate.calibration_artifact_set_fingerprint,
                    candidate.backtest_run_id,
                    candidate.backtest_run_fingerprint,
                    item.source_compatibility_fingerprint,
                    item.evaluation_fingerprint,
                    str(item.promotion_score),
                    item.recommendation.value,
                    item.deterministic_rank,
                    canonical_json(item.reason_codes),
                    run.command.comparison_timestamp,
                ),
            )
        return result

    def _insert_evidence(self, run, rows):
        for evaluation in run.evaluations:
            candidate_row = rows[evaluation.candidate.challenger_candidate_id]
            for item in evaluation.source_evidence:
                identity = _child_id("source", candidate_row, item.evidence_row_id)
                self._connection.execute(
                    "INSERT INTO model_comparison_source_evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        identity, run.comparison_run_id, candidate_row, item.category,
                        item.name, item.champion_value_snapshot,
                        item.challenger_value_snapshot,
                        item.compatibility_status.value, item.detail_snapshot,
                        item.evidence_fingerprint, item.deterministic_order,
                        run.command.comparison_timestamp,
                    ),
                )

    def _insert_metrics(self, run, rows):
        for evaluation in run.evaluations:
            candidate_row = rows[evaluation.candidate.challenger_candidate_id]
            for item in evaluation.metric_evaluations:
                self._connection.execute(
                    "INSERT INTO model_comparison_metric_evaluations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        _child_id("metric", candidate_row, item.metric_evaluation_id),
                        run.comparison_run_id, candidate_row, item.category,
                        item.group_identity, item.metric_name, item.direction.value,
                        _text(item.champion_value), _text(item.challenger_value),
                        _text(item.absolute_delta), _text(item.relative_delta),
                        str(item.normalized_score), item.materiality.value,
                        item.gate_status.value, canonical_json(item.reason_codes),
                        item.metric_fingerprint, item.deterministic_order,
                        run.command.comparison_timestamp,
                    ),
                )

    def _insert_stability(self, run, rows):
        for evaluation in run.evaluations:
            candidate_row = rows[evaluation.candidate.challenger_candidate_id]
            for item in evaluation.stability_groups:
                self._connection.execute(
                    "INSERT INTO model_comparison_stability_groups VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        _child_id("stability", candidate_row, item.stability_row_id),
                        run.comparison_run_id, candidate_row, item.group_category,
                        item.group_identity, item.champion_sample_count,
                        item.challenger_sample_count, item.champion_metric_snapshot,
                        item.challenger_metric_snapshot, item.delta_snapshot,
                        item.stability_status.value,
                        item.concentration_evidence_snapshot,
                        item.stability_fingerprint, item.deterministic_order,
                        run.command.comparison_timestamp,
                    ),
                )

    def _insert_statistics(self, run, rows):
        for evaluation in run.evaluations:
            candidate_row = rows[evaluation.candidate.challenger_candidate_id]
            for item in evaluation.statistical_evidence:
                self._connection.execute(
                    "INSERT INTO model_comparison_statistical_evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        _child_id("statistical", candidate_row, item.statistical_row_id),
                        run.comparison_run_id, candidate_row, item.evidence_name,
                        item.paired_sample_count, item.deterministic_seed,
                        item.bootstrap_iterations, _text(item.effect_size),
                        _text(item.lower_confidence_bound),
                        _text(item.upper_confidence_bound),
                        item.uncertainty_classification.value,
                        item.detail_snapshot, item.evidence_fingerprint,
                        item.deterministic_order, run.command.comparison_timestamp,
                    ),
                )

    def _insert_gates(self, run, rows):
        for evaluation in run.evaluations:
            candidate_row = rows[evaluation.candidate.challenger_candidate_id]
            for item in evaluation.gate_evaluations:
                self._connection.execute(
                    "INSERT INTO model_comparison_gate_evaluations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        _child_id("gate", candidate_row, item.gate_evaluation_id),
                        run.comparison_run_id, candidate_row, item.gate_category,
                        item.gate_name, int(item.mandatory), item.status.value,
                        item.champion_value_snapshot,
                        item.challenger_value_snapshot, item.threshold_snapshot,
                        canonical_json(item.reason_codes), item.deterministic_order,
                        run.command.comparison_timestamp,
                    ),
                )

    def _insert_scores(self, run, rows):
        for evaluation in run.evaluations:
            candidate_row = rows[evaluation.candidate.challenger_candidate_id]
            for item in evaluation.score_components:
                self._connection.execute(
                    "INSERT INTO model_comparison_score_components VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        _child_id("score", candidate_row, item.score_component_id),
                        run.comparison_run_id, candidate_row, item.score_category,
                        str(item.raw_score), str(item.normalized_score),
                        str(item.weight), str(item.weighted_contribution),
                        item.gate_status.value, item.detail_snapshot,
                        item.deterministic_order, run.command.comparison_timestamp,
                    ),
                )

    def _insert_recommendations(self, run, rows):
        for evaluation in run.evaluations:
            candidate_row = rows[evaluation.candidate.challenger_candidate_id]
            strongest = _strongest(evaluation.statistical_evidence)
            material = {
                "comparison_run_id": run.comparison_run_id,
                "candidate": evaluation.candidate.challenger_candidate_id,
                "recommendation": evaluation.recommendation,
                "rank": evaluation.deterministic_rank,
                "score": evaluation.promotion_score,
                "evidence": strongest,
                "reasons": evaluation.reason_codes,
            }
            self._connection.execute(
                "INSERT INTO model_comparison_recommendations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"model-comparison-recommendation-{sha256_fingerprint(material)}",
                    run.comparison_run_id, candidate_row, "CHALLENGER",
                    evaluation.recommendation.value,
                    evaluation.deterministic_rank, str(evaluation.promotion_score),
                    strongest.value, canonical_json(evaluation.reason_codes),
                    sha256_fingerprint(material), run.command.comparison_timestamp,
                ),
            )
        material = {
            "comparison_run_id": run.comparison_run_id,
            "scope": "FINAL",
            "recommendation": run.final_recommendation,
            "winner": run.final_recommended_challenger_id,
            "reasons": run.reason_codes,
        }
        self._connection.execute(
            "INSERT INTO model_comparison_recommendations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"model-comparison-recommendation-{sha256_fingerprint(material)}",
                run.comparison_run_id, None, "FINAL",
                run.final_recommendation.value, None,
                str(max((item.promotion_score for item in run.evaluations), default=Decimal(0))),
                _strongest(tuple(row for item in run.evaluations for row in item.statistical_evidence)).value,
                canonical_json(run.reason_codes), sha256_fingerprint(material),
                run.command.comparison_timestamp,
            ),
        )

    def _insert_exclusions(self, run):
        values = list(run.exclusions)
        values.extend(row for item in run.evaluations for row in item.exclusions)
        for order, item in enumerate(values):
            self._connection.execute(
                "INSERT INTO model_comparison_exclusions VALUES (?,?,?,?,?,?,?,?)",
                (
                    _child_id("exclusion", run.comparison_run_id, item.exclusion_id),
                    run.comparison_run_id, item.challenger_candidate_id,
                    item.exclusion_stage, item.exclusion_reason,
                    item.detail_snapshot, order, run.command.comparison_timestamp,
                ),
            )

    def _rows(self, table, run_id, candidate_row_id):
        query = f"SELECT * FROM {table} WHERE comparison_run_id=?"
        params = [run_id]
        if candidate_row_id is not None:
            query += " AND candidate_row_id=?"
            params.append(candidate_row_id)
        query += " ORDER BY candidate_row_id,deterministic_order"
        return self._connection.execute(query, tuple(params)).fetchall()

    def _list_runs(self, query, value):
        rows = self._connection.execute(query, (value,)).fetchall()
        return tuple(self.load_comparison_run(row[0]) for row in rows)

    def _rollback(self):
        if self._connection.in_transaction:
            self._connection.rollback()


def _command(value):
    scope_value = value["scope"]
    scope = NormalizedComparisonScope(
        comparison_scope_version=scope_value["comparison_scope_version"],
        mode=ComparisonMode(scope_value["mode"]),
        required_competitions=tuple(scope_value["required_competitions"]),
        required_seasons=tuple(scope_value["required_seasons"]),
        required_markets=tuple(scope_value["required_markets"]),
        kickoff_lower_bound=scope_value["kickoff_lower_bound"],
        kickoff_upper_bound=scope_value["kickoff_upper_bound"],
        required_odds_policy_version=scope_value["required_odds_policy_version"],
        required_selection_policy_version=scope_value["required_selection_policy_version"],
        required_staking_policy_version=scope_value["required_staking_policy_version"],
        required_settlement_policy_version=scope_value["required_settlement_policy_version"],
        required_metric_policy_version=scope_value["required_metric_policy_version"],
        required_minimum_shared_sample_size=scope_value["required_minimum_shared_sample_size"],
        required_minimum_selected_bet_count=scope_value["required_minimum_selected_bet_count"],
    )
    challengers = tuple(ChallengerCandidate(**item) for item in value["challengers"])
    return NormalizedComparisonCommand(
        **{
            **value,
            "scope": scope,
            "challengers": challengers,
        }
    )


def _recommendation(row):
    return RecommendationRecord(
        recommendation_id=row["recommendation_id"],
        recommendation_scope=row["recommendation_scope"],
        recommendation=Recommendation(row["recommendation"]),
        promotion_rank=row["promotion_rank"],
        promotion_score=Decimal(row["promotion_score"]),
        evidence_classification=UncertaintyClassification(
            row["evidence_classification"]
        ),
        reason_codes=tuple(json.loads(row["reason_codes_snapshot"])),
        recommendation_fingerprint=row["recommendation_fingerprint"],
    )


def _shared_count(gates, name):
    row = next((item for item in gates if item.gate_name == name), None)
    if row is None:
        return 0
    value = json.loads(row.challenger_value_snapshot)
    return int(value) if value is not None else 0


def _strongest(values):
    order = {
        UncertaintyClassification.INCONCLUSIVE: 0,
        UncertaintyClassification.WEAK_EVIDENCE: 1,
        UncertaintyClassification.MODERATE_EVIDENCE: 2,
        UncertaintyClassification.STRONG_EVIDENCE: 3,
    }
    return max(
        (item.uncertainty_classification for item in values),
        key=lambda item: order[item],
        default=UncertaintyClassification.INCONCLUSIVE,
    )


def _child_id(category, parent, source):
    return f"model-comparison-{category}-{sha256_fingerprint((parent, source))}"


def _policy_versions(command):
    return (
        ("promotion", command.promotion_policy_version),
        ("evidence", command.evidence_policy_version),
        ("compatibility", command.compatibility_policy_version),
        ("significance", command.significance_policy_version),
        ("predictive_score", command.predictive_score_policy_version),
        ("calibration_score", command.calibration_score_policy_version),
        ("betting_score", command.betting_score_policy_version),
        ("risk_score", command.risk_score_policy_version),
        ("stability_score", command.stability_score_policy_version),
        ("tie_break", command.tie_break_policy_version),
    )


def _decimal(value):
    return Decimal(value) if value is not None else None


def _text(value):
    return str(value) if value is not None else None
