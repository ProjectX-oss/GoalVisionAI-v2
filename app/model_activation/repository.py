"""Atomic append-only champion registry, activation, and rollback persistence."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from app.database import Database, MigrationManager

from .exceptions import (
    ActivationConflictError, ActivationPersistenceError, ActivationStalePlanError,
    ChampionStateInvalidError,
)
from .fingerprint import canonical_json, sha256_fingerprint
from .models import (
    ActivationEvidence, ActivationPlan, ActivationRequest, ActivationValidation,
    ChampionGeneration, GenerationReason, RollbackPlan, RollbackRequest,
    RuntimeArtifactReference, ValidationStatus,
)


class SQLiteModelActivationRepository:
    def __init__(self, database: Database, *, migrate=True):
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def bootstrap_champion(self, scope, artifact, timestamp, reason, operator):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            if self._current_row(scope) is not None:
                raise ActivationConflictError("Champion scope is already initialized.")
            generation = _generation(
                scope, 1, artifact, timestamp, GenerationReason.INITIAL_REGISTRATION,
                reason, None, None, None, None, None, None,
            )
            self._insert_generation(generation)
            self._insert_event(generation, "INITIAL_REGISTERED", operator, timestamp)
            self._connection.commit()
            return generation
        except (ActivationConflictError, ChampionStateInvalidError):
            self._rollback(); raise
        except sqlite3.DatabaseError as exc:
            self._rollback()
            raise ActivationPersistenceError(f"Champion bootstrap failed: {exc}") from exc

    def append_activation_plan(self, plan):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT request_fingerprint,activation_plan_id FROM model_activation_requests WHERE activation_request_id=?",
                (plan.request.activation_request_id,),
            ).fetchone()
            if row:
                if row["request_fingerprint"] != plan.request_fingerprint:
                    raise ActivationConflictError("Activation request ID has different immutable content.")
                existing = self.load_activation_plan(row["activation_plan_id"])
                self._connection.commit()
                return existing
            pending = self._connection.execute(
                """SELECT p.activation_plan_id FROM model_activation_plans p
                   JOIN model_activation_requests r ON r.activation_request_id=p.activation_request_id
                   LEFT JOIN model_activation_executions e ON e.activation_plan_id=p.activation_plan_id
                   WHERE r.model_scope=? AND e.activation_plan_id IS NULL LIMIT 1""",
                (plan.request.model_scope,),
            ).fetchone()
            if pending:
                raise ActivationConflictError("A pending activation plan already exists for this scope.")
            self._connection.execute(
                """INSERT INTO model_activation_requests
                (activation_request_id,model_scope,request_fingerprint,activation_plan_id,requested_timestamp_utc,request_snapshot)
                VALUES (?,?,?,?,?,?)""",
                (plan.request.activation_request_id, plan.request.model_scope, plan.request_fingerprint,
                 plan.activation_plan_id, _text(plan.request.requested_timestamp_utc), canonical_json(plan.request)),
            )
            self._connection.execute(
                """INSERT INTO model_activation_plans
                (activation_plan_id,activation_request_id,activation_plan_fingerprint,expected_generation_number,
                 expected_registry_fingerprint,prepared_timestamp_utc,policy_snapshot,evidence_snapshot,plan_snapshot)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (plan.activation_plan_id, plan.request.activation_request_id, plan.activation_plan_fingerprint,
                 plan.expected_registry_generation_number, plan.expected_registry_fingerprint,
                 plan.prepared_timestamp_utc, plan.policy_snapshot, canonical_json(plan.evidence), canonical_json(plan)),
            )
            self._insert_validations(plan.activation_plan_id, None, plan.validations)
            for order, (execution_id, execution_fp, settlement_fp) in enumerate(zip(
                plan.evidence.shadow_execution_ids, plan.evidence.shadow_execution_fingerprints,
                plan.evidence.shadow_settlement_fingerprints,
            )):
                link_fp = sha256_fingerprint((plan.activation_plan_id, execution_fp, settlement_fp))
                self._connection.execute(
                    "INSERT INTO model_activation_evidence_links VALUES (?,?,?,?,?,?,?)",
                    (f"activation-evidence-{link_fp}", plan.activation_plan_id, execution_id,
                     execution_fp, settlement_fp, order, link_fp),
                )
            self._connection.commit()
            return plan
        except ActivationConflictError:
            self._rollback(); raise
        except sqlite3.DatabaseError as exc:
            self._rollback()
            raise ActivationPersistenceError(f"Activation plan transaction failed: {exc}") from exc

    def execute_activation(self, plan, execution_request_id, execution_timestamp, operator):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT activation_plan_fingerprint,champion_generation_id FROM model_activation_executions WHERE activation_execution_request_id=?",
                (execution_request_id,),
            ).fetchone()
            if existing:
                if existing["activation_plan_fingerprint"] != plan.activation_plan_fingerprint:
                    raise ActivationConflictError("Activation execution request conflicts.")
                generation = self.load_generation(existing["champion_generation_id"])
                self._connection.commit()
                return generation, True
            current = self._current_generation_locked(plan.request.model_scope)
            if (
                current.champion_generation_id != plan.request.current_champion_generation_id
                or current.generation_fingerprint != plan.expected_registry_fingerprint
                or current.generation_number != plan.expected_registry_generation_number
            ):
                raise ActivationStalePlanError("Active champion changed after plan preparation.")
            generation = _generation(
                plan.request.model_scope, current.generation_number + 1, plan.request.challenger,
                execution_timestamp, GenerationReason.APPROVED_ACTIVATION,
                plan.request.activation_reason, plan.request.recommendation_id,
                plan.request.recommendation_fingerprint, plan.evidence.evidence_fingerprint,
                current.champion_generation_id, plan.activation_plan_id, None,
            )
            self._insert_generation(generation)
            self._insert_event(current, "RETIRED_BY_ACTIVATION", operator, execution_timestamp)
            self._insert_event(generation, "CHAMPION_ACTIVATED", operator, execution_timestamp)
            execution_fp = sha256_fingerprint((execution_request_id, plan.activation_plan_fingerprint, generation.generation_fingerprint, _text(execution_timestamp), operator))
            self._connection.execute(
                "INSERT INTO model_activation_executions VALUES (?,?,?,?,?,?,?)",
                (f"activation-execution-{execution_fp}", execution_request_id, plan.activation_plan_id,
                 plan.activation_plan_fingerprint, generation.champion_generation_id,
                 _text(execution_timestamp), execution_fp),
            )
            self._connection.commit()
            return generation, False
        except (ActivationConflictError, ActivationStalePlanError, ChampionStateInvalidError):
            self._rollback(); raise
        except sqlite3.DatabaseError as exc:
            self._rollback()
            raise ActivationPersistenceError(f"Activation execution transaction failed: {exc}") from exc

    def append_rollback_plan(self, plan):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT request_fingerprint,rollback_plan_id FROM model_rollback_requests WHERE rollback_request_id=?",
                (plan.request.rollback_request_id,),
            ).fetchone()
            if row:
                if row["request_fingerprint"] != plan.request_fingerprint:
                    raise ActivationConflictError("Rollback request ID has different immutable content.")
                existing = self.load_rollback_plan(row["rollback_plan_id"])
                self._connection.commit()
                return existing
            pending = self._connection.execute(
                """SELECT p.rollback_plan_id FROM model_rollback_plans p
                   JOIN model_rollback_requests r ON r.rollback_request_id=p.rollback_request_id
                   LEFT JOIN model_rollback_executions e ON e.rollback_plan_id=p.rollback_plan_id
                   WHERE r.model_scope=? AND e.rollback_plan_id IS NULL LIMIT 1""",
                (plan.request.model_scope,),
            ).fetchone()
            if pending:
                raise ActivationConflictError("A pending rollback plan already exists for this scope.")
            self._connection.execute(
                "INSERT INTO model_rollback_requests VALUES (?,?,?,?,?,?)",
                (plan.request.rollback_request_id, plan.request.model_scope, plan.request_fingerprint,
                 plan.rollback_plan_id, _text(plan.request.requested_timestamp_utc), canonical_json(plan.request)),
            )
            self._connection.execute(
                "INSERT INTO model_rollback_plans VALUES (?,?,?,?,?,?,?,?,?)",
                (plan.rollback_plan_id, plan.request.rollback_request_id, plan.rollback_plan_fingerprint,
                 plan.expected_registry_generation_number, plan.expected_registry_fingerprint,
                 plan.prepared_timestamp_utc, plan.policy_snapshot,
                 plan.target_generation.champion_generation_id, canonical_json(plan)),
            )
            self._insert_validations(None, plan.rollback_plan_id, plan.validations)
            self._connection.commit()
            return plan
        except ActivationConflictError:
            self._rollback(); raise
        except sqlite3.DatabaseError as exc:
            self._rollback()
            raise ActivationPersistenceError(f"Rollback plan transaction failed: {exc}") from exc

    def execute_rollback(self, plan, execution_request_id, execution_timestamp, operator):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT rollback_plan_fingerprint,champion_generation_id FROM model_rollback_executions WHERE rollback_execution_request_id=?",
                (execution_request_id,),
            ).fetchone()
            if existing:
                if existing["rollback_plan_fingerprint"] != plan.rollback_plan_fingerprint:
                    raise ActivationConflictError("Rollback execution request conflicts.")
                generation = self.load_generation(existing["champion_generation_id"])
                self._connection.commit()
                return generation, True
            current = self._current_generation_locked(plan.request.model_scope)
            if (
                current.champion_generation_id != plan.request.current_champion_generation_id
                or current.generation_fingerprint != plan.expected_registry_fingerprint
                or current.generation_number != plan.expected_registry_generation_number
            ):
                raise ActivationStalePlanError("Active champion changed after rollback preparation.")
            target = self.load_generation(plan.request.target_champion_generation_id)
            if target is None or target.model_scope != plan.request.model_scope:
                raise ActivationStalePlanError("Rollback target is no longer valid.")
            generation = _generation(
                plan.request.model_scope, current.generation_number + 1, target.artifact,
                execution_timestamp, GenerationReason.MANUAL_ROLLBACK,
                f"{plan.request.rollback_reason} [{plan.request.incident_reference}]",
                target.source_recommendation_id, target.source_recommendation_fingerprint,
                target.source_shadow_evidence_fingerprint, current.champion_generation_id,
                None, plan.rollback_plan_id,
            )
            self._insert_generation(generation)
            self._insert_event(current, "RETIRED_BY_ROLLBACK", operator, execution_timestamp)
            self._insert_event(generation, "CHAMPION_ROLLED_BACK", operator, execution_timestamp)
            execution_fp = sha256_fingerprint((execution_request_id, plan.rollback_plan_fingerprint, generation.generation_fingerprint, _text(execution_timestamp), operator))
            self._connection.execute(
                "INSERT INTO model_rollback_executions VALUES (?,?,?,?,?,?,?)",
                (f"rollback-execution-{execution_fp}", execution_request_id, plan.rollback_plan_id,
                 plan.rollback_plan_fingerprint, generation.champion_generation_id,
                 _text(execution_timestamp), execution_fp),
            )
            self._connection.commit()
            return generation, False
        except (ActivationConflictError, ActivationStalePlanError, ChampionStateInvalidError):
            self._rollback(); raise
        except sqlite3.DatabaseError as exc:
            self._rollback()
            raise ActivationPersistenceError(f"Rollback execution transaction failed: {exc}") from exc

    def resolve_current_champion(self, scope):
        rows = self._connection.execute(
            "SELECT champion_generation_id FROM model_champion_generations WHERE model_scope=? ORDER BY generation_number DESC LIMIT 2",
            (scope,),
        ).fetchall()
        if not rows:
            raise ChampionStateInvalidError("Champion scope is not initialized.")
        current = self.load_generation(rows[0][0])
        expected = self._connection.execute(
            "SELECT COUNT(*) FROM model_champion_generations WHERE model_scope=? AND generation_number=?",
            (scope, current.generation_number),
        ).fetchone()[0]
        if expected != 1:
            raise ChampionStateInvalidError("Champion registry contains duplicate current state.")
        return current

    def load_generation(self, generation_id):
        row = self._connection.execute(
            "SELECT generation_snapshot FROM model_champion_generations WHERE champion_generation_id=?", (generation_id,),
        ).fetchone()
        return _load_generation(json.loads(row[0])) if row else None

    def list_generations(self, scope):
        rows = self._connection.execute(
            "SELECT champion_generation_id FROM model_champion_generations WHERE model_scope=? ORDER BY generation_number", (scope,),
        )
        return tuple(self.load_generation(row[0]) for row in rows)

    def load_activation_plan(self, plan_id):
        row = self._connection.execute("SELECT plan_snapshot FROM model_activation_plans WHERE activation_plan_id=?", (plan_id,)).fetchone()
        return _load_activation_plan(json.loads(row[0])) if row else None

    def load_rollback_plan(self, plan_id):
        row = self._connection.execute("SELECT plan_snapshot FROM model_rollback_plans WHERE rollback_plan_id=?", (plan_id,)).fetchone()
        return _load_rollback_plan(json.loads(row[0])) if row else None

    def _insert_validations(self, activation_plan_id, rollback_plan_id, validations):
        for item in validations:
            self._connection.execute(
                "INSERT INTO model_activation_validations VALUES (?,?,?,?,?,?,?,?,?)",
                (item.validation_id, activation_plan_id, rollback_plan_id, item.category,
                 item.name, item.status.value, item.detail_snapshot,
                 item.validation_fingerprint, item.deterministic_order),
            )

    def _insert_generation(self, generation):
        self._connection.execute(
            """INSERT INTO model_champion_generations
            (champion_generation_id,model_scope,generation_number,model_artifact_id,
             calibration_artifact_set_id,previous_champion_generation_id,activation_plan_id,
             rollback_plan_id,activation_timestamp_utc,generation_fingerprint,generation_snapshot)
             VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (generation.champion_generation_id, generation.model_scope, generation.generation_number,
             generation.artifact.model_artifact_id, generation.artifact.calibration_artifact_set_id,
             generation.previous_champion_generation_id, generation.activation_plan_id,
             generation.rollback_plan_id, generation.activation_timestamp_utc,
             generation.generation_fingerprint, canonical_json(generation)),
        )

    def _insert_event(self, generation, event_type, operator, timestamp):
        fingerprint = sha256_fingerprint((generation.generation_fingerprint, event_type, operator, _text(timestamp)))
        self._connection.execute(
            "INSERT INTO model_champion_registry_events VALUES (?,?,?,?,?,?,?,?)",
            (f"champion-event-{fingerprint}", generation.model_scope,
             generation.champion_generation_id, generation.generation_number,
             event_type, operator, _text(timestamp), fingerprint),
        )

    def _current_row(self, scope):
        return self._connection.execute(
            "SELECT champion_generation_id FROM model_champion_generations WHERE model_scope=? ORDER BY generation_number DESC LIMIT 1", (scope,),
        ).fetchone()

    def _current_generation_locked(self, scope):
        row = self._current_row(scope)
        if row is None:
            raise ChampionStateInvalidError("Champion scope is not initialized.")
        return self.load_generation(row[0])

    def _rollback(self):
        if self._connection.in_transaction:
            self._connection.rollback()


def _generation(scope, number, artifact, timestamp, reason, detail, recommendation_id, recommendation_fp, evidence_fp, previous_id, activation_plan_id, rollback_plan_id):
    core = {
        "scope": scope, "number": number, "artifact": artifact, "timestamp": _text(timestamp),
        "reason": reason, "detail": detail, "recommendation_id": recommendation_id,
        "recommendation_fp": recommendation_fp, "evidence_fp": evidence_fp,
        "previous_id": previous_id, "activation_plan_id": activation_plan_id,
        "rollback_plan_id": rollback_plan_id,
    }
    fingerprint = sha256_fingerprint(core)
    return ChampionGeneration(
        champion_generation_id=f"champion-generation-{fingerprint}", model_scope=scope,
        generation_number=number, artifact=artifact, activation_timestamp_utc=_text(timestamp),
        activation_reason=reason, activation_reason_detail=detail,
        source_recommendation_id=recommendation_id,
        source_recommendation_fingerprint=recommendation_fp,
        source_shadow_evidence_fingerprint=evidence_fp,
        previous_champion_generation_id=previous_id,
        activation_plan_id=activation_plan_id, rollback_plan_id=rollback_plan_id,
        generation_status="ACTIVE_AT_CREATION", generation_fingerprint=fingerprint,
    )


def _text(value):
    return value if isinstance(value, str) else value.isoformat().replace("+00:00", "Z")


def _reference(d): return RuntimeArtifactReference(**d)
def _request(d): return ActivationRequest(**{**d, "current_champion": _reference(d["current_champion"]), "challenger": _reference(d["challenger"])})
def _rollback_request(d): return RollbackRequest(**d)
def _validation(d): return ActivationValidation(**{**d, "status": ValidationStatus(d["status"])})
def _evidence(d):
    decimal_fields = ("observation_days", "agreement_ratio", "critical_disagreement_ratio", "predictive_degradation", "calibration_degradation", "betting_performance_degradation", "drawdown_deterioration", "evidence_completeness")
    return ActivationEvidence(**{**d, **{key: Decimal(d[key]) for key in decimal_fields}, "shadow_execution_ids": tuple(d["shadow_execution_ids"]), "shadow_execution_fingerprints": tuple(d["shadow_execution_fingerprints"]), "shadow_settlement_fingerprints": tuple(d["shadow_settlement_fingerprints"])})
def _load_generation(d): return ChampionGeneration(**{**d, "artifact": _reference(d["artifact"]), "activation_reason": GenerationReason(d["activation_reason"])})
def _load_activation_plan(d):
    return ActivationPlan(**{**d, "request": _request(d["request"]), "validations": tuple(_validation(x) for x in d["validations"]), "evidence": _evidence(d["evidence"])})
def _load_rollback_plan(d):
    return RollbackPlan(**{**d, "request": _rollback_request(d["request"]), "target_generation": _load_generation(d["target_generation"]), "validations": tuple(_validation(x) for x in d["validations"])})
