import asyncio
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.database import Database
from app.model_activation import (
    ActivationEvidence,
    ActivationExecutionCommand,
    ActivationNotEligibleError,
    ActivationRequest,
    ActivationStatus,
    ChampionResolution,
    ModelActivationPolicy,
    ModelActivationService,
    RollbackExecutionCommand,
    RollbackRequest,
    RuntimeArtifactReference,
    SQLiteModelActivationRepository,
    sha256_fingerprint,
)
from app.model_operations import (
    ACTIVATION_CONFIRMATION,
    ROLLBACK_CONFIRMATION,
    DiagnosticStatus,
    ModelOperationsService,
    OperationMode,
    OperatorResult,
    OperatorStatus,
    format_lab_preview,
    format_result_json,
)
from app.model_operations.cli import build_parser, main
from app.model_operations.configuration import (
    ModelOperationsConfigurationError,
)
from app.services.telegram_service import TelegramService


UTC = timezone.utc
NOW = datetime(2026, 8, 2, 12, tzinfo=UTC)
SCOPE = "OFFICIAL_GLOBAL"


def artifact(name):
    return RuntimeArtifactReference(
        model_artifact_id=f"model-{name}",
        model_artifact_fingerprint=f"model-fp-{name}",
        preprocessing_fingerprint=f"pre-fp-{name}",
        calibration_artifact_set_id=f"cal-{name}",
        calibration_artifact_set_fingerprint=f"cal-fp-{name}",
        feature_schema_version="historical_training_features_v1",
        feature_schema_fingerprint="schema-fp",
        target_contract_version="official_prediction_targets_v1",
        probability_contract_version="canonical-11-target-contract-v1",
        runtime_compatibility_version="probability-calibration-v1",
    )


def evidence():
    value = ActivationEvidence(
        settled_count=30,
        observation_days=Decimal("14"),
        agreement_ratio=Decimal(".8"),
        critical_disagreement_ratio=Decimal(".05"),
        predictive_degradation=Decimal("0"),
        calibration_degradation=Decimal("0"),
        betting_performance_degradation=Decimal("0"),
        drawdown_deterioration=Decimal("0"),
        evidence_completeness=Decimal("1"),
        shadow_execution_ids=(),
        shadow_execution_fingerprints=(),
        shadow_settlement_fingerprints=(),
        evidence_fingerprint="pending",
    )
    return replace(value, evidence_fingerprint=sha256_fingerprint(value))


def activation_request(current, request_id="activate-ops-1"):
    return ActivationRequest(
        activation_request_id=request_id,
        activation_name="Reviewed challenger",
        model_scope=SCOPE,
        current_champion_generation_id=current.champion_generation_id,
        current_champion_generation_fingerprint=current.generation_fingerprint,
        current_champion=current.artifact,
        challenger=artifact("b"),
        comparison_run_id="comparison-1",
        comparison_run_fingerprint="comparison-fp",
        challenger_candidate_id="candidate-1",
        recommendation_id="recommendation-1",
        recommendation_fingerprint="recommendation-fp",
        evidence_cutoff_timestamp_utc=NOW,
        requested_timestamp_utc=NOW,
        activation_reason="Reviewed promotion and shadow evidence",
        operator_identity="operator-1",
    )


class FakeResolver:
    def __init__(self, repository, failure=None):
        self.repository = repository
        self.failure = failure

    def resolve(self, scope):
        if self.failure:
            return ChampionResolution(
                ActivationStatus.CHAMPION_STATE_INVALID,
                scope,
                None,
                (self.failure,),
            )
        try:
            generation = self.repository.resolve_current_champion(scope)
        except Exception as exc:
            return ChampionResolution(
                ActivationStatus.CHAMPION_STATE_INVALID,
                scope,
                None,
                (str(exc),),
            )
        return ChampionResolution(
            ActivationStatus.CHAMPION_RESOLVED,
            scope,
            generation,
            (),
        )


class ModelOperationsTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.repository = SQLiteModelActivationRepository(self.database)
        self.database.connection.execute("PRAGMA foreign_keys=OFF")
        self.policy = ModelActivationPolicy()
        self.activation_service = ModelActivationService(
            self.repository,
            object(),
            object(),
            object(),
            object(),
            self.policy,
        )
        self.service = ModelOperationsService(
            repository=self.repository,
            activation_service=self.activation_service,
            resolver=FakeResolver(self.repository),
            model_repository=object(),
            calibration_repository=object(),
            shadow_repository=object(),
            policy=self.policy,
            connection=self.database.connection,
        )
        self.initial = None

    def tearDown(self):
        self.database.close()

    def bootstrap(self):
        with patch(
            "app.model_operations.service.verify_runtime_artifact"
        ):
            result = self.service.bootstrap_champion(
                scope=SCOPE,
                artifact=artifact("a"),
                timestamp=NOW,
                reason="Reviewed initial champion",
                operator="operator-1",
            )
        self.initial = self.repository.resolve_current_champion(SCOPE)
        return result

    def prepare_activation(self):
        if self.initial is None:
            self.bootstrap()
        request = activation_request(self.initial)
        expected = evidence()
        with (
            patch(
                "app.model_operations.service.build_activation_evidence",
                return_value=expected,
            ),
            patch("app.model_activation.service.verify_promotion"),
            patch(
                "app.model_activation.service.verify_runtime_artifact"
            ),
            patch(
                "app.model_activation.service.build_activation_evidence",
                return_value=expected,
            ),
        ):
            result = self.service.prepare_activation(
                request,
                expected_shadow_evidence_fingerprint=(
                    expected.evidence_fingerprint
                ),
            )
        return request, result

    def execute_activation(self):
        request, prepared = self.prepare_activation()
        command = ActivationExecutionCommand(
            "execute-ops-1",
            prepared.details["activation_plan_id"],
            prepared.details["activation_plan_fingerprint"],
            NOW,
            "operator-1",
        )
        expected = evidence()
        with (
            patch("app.model_activation.service.verify_promotion"),
            patch(
                "app.model_activation.service.verify_runtime_artifact"
            ),
            patch(
                "app.model_activation.service.build_activation_evidence",
                return_value=expected,
            ),
        ):
            executed = self.service.execute_activation(
                command,
                confirmation=ACTIVATION_CONFIRMATION,
            )
        return command, executed

    def prepare_rollback(self):
        _, executed = self.execute_activation()
        promoted = self.repository.resolve_current_champion(SCOPE)
        request = RollbackRequest(
            "rollback-ops-1",
            "Incident rollback",
            SCOPE,
            promoted.champion_generation_id,
            promoted.generation_fingerprint,
            self.initial.champion_generation_id,
            "Observed runtime incident",
            "INC-OPS-1",
            "operator-1",
            NOW,
        )
        with patch(
            "app.model_activation.service.verify_runtime_artifact"
        ):
            result = self.service.prepare_rollback(request)
        return request, result

    def test_bootstrap_success(self):
        result = self.bootstrap()
        self.assertEqual(result.status, OperatorStatus.BOOTSTRAP_EXECUTED.value)
        self.assertTrue(result.production_state_changed)
        self.assertEqual(len(self.repository.list_generations(SCOPE)), 1)

    def test_duplicate_bootstrap_rejection(self):
        self.bootstrap()
        result = self.bootstrap()
        self.assertEqual(result.status, OperatorStatus.BOOTSTRAP_REJECTED.value)
        self.assertFalse(result.production_state_changed)

    def test_bootstrap_conflict_does_not_replace_champion(self):
        self.bootstrap()
        original = self.repository.resolve_current_champion(SCOPE)
        with patch(
            "app.model_operations.service.verify_runtime_artifact"
        ):
            result = self.service.bootstrap_champion(
                scope=SCOPE,
                artifact=artifact("conflict"),
                timestamp=NOW,
                reason="Conflicting bootstrap",
                operator="operator-2",
            )
        self.assertFalse(result.success)
        self.assertEqual(
            self.repository.resolve_current_champion(SCOPE),
            original,
        )

    def test_bootstrap_missing_artifact_rejected(self):
        with patch(
            "app.model_operations.service.verify_runtime_artifact",
            side_effect=ActivationNotEligibleError("missing artifact"),
        ):
            result = self.service.bootstrap_champion(
                scope=SCOPE,
                artifact=artifact("missing"),
                timestamp=NOW,
                reason="Missing",
                operator="operator-1",
            )
        self.assertEqual(
            result.status,
            OperatorStatus.BOOTSTRAP_REJECTED.value,
        )

    def test_prepare_activation_success(self):
        _, result = self.prepare_activation()
        self.assertEqual(
            result.status,
            OperatorStatus.ACTIVATION_PLAN_PREPARED.value,
        )
        self.assertIn("activation_plan_fingerprint", result.details)

    def test_prepare_activation_does_not_change_champion(self):
        self.prepare_activation()
        self.assertEqual(
            self.repository.resolve_current_champion(SCOPE),
            self.initial,
        )

    def test_explicit_shadow_evidence_mismatch_rejected_before_plan(self):
        self.bootstrap()
        with patch(
            "app.model_operations.service.build_activation_evidence",
            return_value=evidence(),
        ):
            result = self.service.prepare_activation(
                activation_request(self.initial),
                expected_shadow_evidence_fingerprint="wrong",
            )
        self.assertFalse(result.success)
        self.assertEqual(
            self.database.connection.execute(
                "SELECT COUNT(*) FROM model_activation_plans"
            ).fetchone()[0],
            0,
        )

    def test_execute_activation_success(self):
        _, result = self.execute_activation()
        self.assertEqual(
            result.status,
            OperatorStatus.ACTIVATION_EXECUTED.value,
        )
        self.assertTrue(result.production_state_changed)
        self.assertEqual(
            self.repository.resolve_current_champion(SCOPE).artifact,
            artifact("b"),
        )

    def test_wrong_activation_confirmation_phrase(self):
        _, prepared = self.prepare_activation()
        result = self.service.execute_activation(
            ActivationExecutionCommand(
                "execute-wrong",
                prepared.details["activation_plan_id"],
                prepared.details["activation_plan_fingerprint"],
                NOW,
                "operator-1",
            ),
            confirmation="YES",
        )
        self.assertEqual(
            result.status,
            OperatorStatus.CONFIRMATION_REJECTED.value,
        )
        self.assertEqual(
            self.repository.resolve_current_champion(SCOPE),
            self.initial,
        )

    def test_stale_activation_plan(self):
        _, prepared = self.prepare_activation()
        result = self.service.execute_activation(
            ActivationExecutionCommand(
                "execute-stale",
                prepared.details["activation_plan_id"],
                "wrong-fingerprint",
                NOW,
                "operator-1",
            ),
            confirmation=ACTIVATION_CONFIRMATION,
        )
        self.assertEqual(
            result.status,
            OperatorStatus.ACTIVATION_STALE_PLAN.value,
        )

    def test_already_executed_activation_is_nonzero_outcome(self):
        command, first = self.execute_activation()
        self.assertTrue(first.success)
        expected = evidence()
        with (
            patch("app.model_activation.service.verify_promotion"),
            patch(
                "app.model_activation.service.verify_runtime_artifact"
            ),
            patch(
                "app.model_activation.service.build_activation_evidence",
                return_value=expected,
            ),
        ):
            second = self.service.execute_activation(
                command,
                confirmation=ACTIVATION_CONFIRMATION,
            )
        self.assertEqual(
            second.status,
            OperatorStatus.ACTIVATION_ALREADY_EXECUTED.value,
        )
        self.assertFalse(second.success)

    def test_activation_conflict_is_typed(self):
        outcome = SimpleNamespace(
            status=ActivationStatus.ACTIVATION_CONFLICT,
            model_scope=SCOPE,
            plan_id="plan",
            plan_fingerprint="fp",
            champion_generation=None,
            reason_codes=("conflict",),
        )
        self.service._activation_service = SimpleNamespace(
            execute_activation=lambda command: outcome
        )
        result = self.service.execute_activation(
            ActivationExecutionCommand(
                "execute-conflict", "plan", "fp", NOW, "operator-1"
            ),
            confirmation=ACTIVATION_CONFIRMATION,
        )
        self.assertEqual(
            result.status,
            OperatorStatus.ACTIVATION_CONFLICT.value,
        )

    def test_prepare_rollback_success(self):
        _, result = self.prepare_rollback()
        self.assertEqual(
            result.status,
            OperatorStatus.ROLLBACK_PLAN_PREPARED.value,
        )

    def test_prepare_rollback_does_not_change_champion(self):
        _, result = self.prepare_rollback()
        self.assertTrue(result.success)
        self.assertEqual(
            self.repository.resolve_current_champion(SCOPE).artifact,
            artifact("b"),
        )

    def test_execute_rollback_success(self):
        _, prepared = self.prepare_rollback()
        with patch(
            "app.model_activation.service.verify_runtime_artifact"
        ):
            result = self.service.execute_rollback(
                RollbackExecutionCommand(
                    "rollback-execute-1",
                    prepared.details["rollback_plan_id"],
                    prepared.details["rollback_plan_fingerprint"],
                    NOW,
                    "operator-1",
                ),
                confirmation=ROLLBACK_CONFIRMATION,
            )
        self.assertEqual(
            result.status,
            OperatorStatus.ROLLBACK_EXECUTED.value,
        )
        self.assertEqual(
            self.repository.resolve_current_champion(SCOPE).artifact,
            artifact("a"),
        )

    def test_wrong_rollback_confirmation_phrase(self):
        _, prepared = self.prepare_rollback()
        result = self.service.execute_rollback(
            RollbackExecutionCommand(
                "rollback-wrong",
                prepared.details["rollback_plan_id"],
                prepared.details["rollback_plan_fingerprint"],
                NOW,
                "operator-1",
            ),
            confirmation="YES",
        )
        self.assertEqual(
            result.status,
            OperatorStatus.CONFIRMATION_REJECTED.value,
        )

    def test_stale_rollback_plan(self):
        _, prepared = self.prepare_rollback()
        result = self.service.execute_rollback(
            RollbackExecutionCommand(
                "rollback-stale",
                prepared.details["rollback_plan_id"],
                "wrong",
                NOW,
                "operator-1",
            ),
            confirmation=ROLLBACK_CONFIRMATION,
        )
        self.assertEqual(
            result.status,
            OperatorStatus.ROLLBACK_STALE_PLAN.value,
        )

    def test_invalid_rollback_target(self):
        self.bootstrap()
        current = self.initial
        request = RollbackRequest(
            "rollback-invalid",
            "Invalid target",
            SCOPE,
            current.champion_generation_id,
            current.generation_fingerprint,
            "missing-generation",
            "Incident",
            "INC-2",
            "operator-1",
            NOW,
        )
        result = self.service.prepare_rollback(request)
        self.assertEqual(
            result.status,
            OperatorStatus.ROLLBACK_REJECTED.value,
        )

    def test_already_executed_rollback_is_typed(self):
        _, prepared = self.prepare_rollback()
        command = RollbackExecutionCommand(
            "rollback-replay",
            prepared.details["rollback_plan_id"],
            prepared.details["rollback_plan_fingerprint"],
            NOW,
            "operator-1",
        )
        with patch(
            "app.model_activation.service.verify_runtime_artifact"
        ):
            first = self.service.execute_rollback(
                command,
                confirmation=ROLLBACK_CONFIRMATION,
            )
            second = self.service.execute_rollback(
                command,
                confirmation=ROLLBACK_CONFIRMATION,
            )
        self.assertTrue(first.success)
        self.assertEqual(
            second.status,
            OperatorStatus.ROLLBACK_ALREADY_EXECUTED.value,
        )
        self.assertFalse(second.success)

    def test_rollback_conflict_is_typed(self):
        outcome = SimpleNamespace(
            status=ActivationStatus.ROLLBACK_CONFLICT,
            model_scope=SCOPE,
            plan_id="plan",
            plan_fingerprint="fp",
            champion_generation=None,
            reason_codes=("conflict",),
        )
        self.service._activation_service = SimpleNamespace(
            execute_rollback=lambda command: outcome
        )
        result = self.service.execute_rollback(
            RollbackExecutionCommand(
                "rollback-conflict", "plan", "fp", NOW, "operator-1"
            ),
            confirmation=ROLLBACK_CONFIRMATION,
        )
        self.assertEqual(
            result.status,
            OperatorStatus.ROLLBACK_CONFLICT.value,
        )

    def test_show_champion(self):
        self.bootstrap()
        result = self.service.show_champion(SCOPE)
        self.assertTrue(result.success)
        details = result.details["champion_generation"]
        self.assertEqual(details["model_artifact_id"], "model-a")
        self.assertFalse(result.production_state_changed)

    def test_show_activation(self):
        _, prepared = self.prepare_activation()
        result = self.service.show_activation(
            SCOPE,
            prepared.details["activation_plan_id"],
        )
        self.assertEqual(
            result.status,
            OperatorStatus.ACTIVATION_SHOWN.value,
        )
        self.assertEqual(result.details["typed_outcome"], "PREPARED")

    def test_list_generations_is_chronological_and_bounded(self):
        self.execute_activation()
        result = self.service.list_generations(SCOPE, 1)
        self.assertEqual(result.details["total_generations"], 2)
        self.assertEqual(result.details["returned_generations"], 1)
        self.assertEqual(
            result.details["generations"][0]["generation_number"],
            2,
        )

    def test_healthy_diagnostic_state(self):
        self.bootstrap()
        result = self.service.diagnose_state(SCOPE)
        self.assertEqual(result.status, DiagnosticStatus.HEALTHY.value)
        self.assertTrue(result.success)

    def test_missing_champion_diagnostic(self):
        result = self.service.diagnose_state(SCOPE)
        self.assertEqual(result.status, DiagnosticStatus.INVALID_STATE.value)
        codes = {
            item["code"] for item in result.details["findings"]
        }
        self.assertIn("MISSING_CHAMPION", codes)

    def test_prepared_plan_diagnostic_warning(self):
        self.prepare_activation()
        result = self.service.diagnose_state(SCOPE)
        self.assertEqual(result.status, DiagnosticStatus.WARNING.value)
        self.assertIn(
            "PREPARED_PLAN_REVIEW_REQUIRED",
            {item["code"] for item in result.details["findings"]},
        )

    def test_duplicate_active_generation_detection(self):
        self.bootstrap()
        duplicate = replace(
            self.initial,
            champion_generation_id="duplicate",
        )
        with patch.object(
            self.repository,
            "list_generations",
            return_value=(self.initial, duplicate),
        ):
            result = self.service.diagnose_state(SCOPE)
        self.assertEqual(result.status, DiagnosticStatus.INVALID_STATE.value)

    def test_corrupted_registry_detection(self):
        self.bootstrap()
        self.database.connection.execute(
            "DROP TRIGGER model_champion_generations_no_update"
        )
        result = self.service.diagnose_state(SCOPE)
        self.assertEqual(result.status, DiagnosticStatus.INVALID_STATE.value)
        self.assertIn(
            "APPEND_ONLY_GUARDS_MISSING",
            {item["code"] for item in result.details["findings"]},
        )

    def test_missing_artifact_detection(self):
        self.bootstrap()
        self.service._resolver = FakeResolver(
            self.repository,
            "Model artifact is missing.",
        )
        result = self.service.diagnose_state(SCOPE)
        self.assertEqual(result.status, DiagnosticStatus.INVALID_STATE.value)
        self.assertIn(
            "RUNTIME_RESOLUTION_FAILED",
            {item["code"] for item in result.details["findings"]},
        )

    def test_fingerprint_mismatch_detection(self):
        self.bootstrap()
        corrupt = replace(self.initial, generation_fingerprint="wrong")
        with patch.object(
            self.repository,
            "list_generations",
            return_value=(corrupt,),
        ):
            result = self.service.diagnose_state(SCOPE)
        self.assertIn(
            "GENERATION_FINGERPRINT_MISMATCH",
            {item["code"] for item in result.details["findings"]},
        )

    def test_json_output_stability_and_versioning(self):
        result = OperatorResult(
            "show-champion",
            "CHAMPION_SHOWN",
            True,
            OperationMode.READ_ONLY,
            False,
            SCOPE,
            details={"b": 2, "a": 1},
        )
        first = format_result_json(result)
        self.assertEqual(first, format_result_json(result))
        parsed = json.loads(first)
        self.assertEqual(
            parsed["output_schema_version"],
            "goalvision-model-operations-output-v1",
        )
        self.assertEqual(list(parsed["details"]), ["a", "b"])

    def test_secret_redaction(self):
        result = OperatorResult(
            "diagnose-state",
            "HEALTHY",
            True,
            OperationMode.READ_ONLY,
            False,
            details={
                "database_password": "never-print",
                "telegram_token": "never-print",
            },
        )
        rendered = format_result_json(result)
        self.assertNotIn("never-print", rendered)
        self.assertEqual(rendered.count("[REDACTED]"), 2)

    def test_lab_preview_is_formatting_only(self):
        with patch.object(
            TelegramService,
            "send_message",
            new=AsyncMock(),
        ) as sender:
            preview = format_lab_preview(
                OperatorResult(
                    "show-champion",
                    "CHAMPION_SHOWN",
                    True,
                    OperationMode.READ_ONLY,
                    False,
                    SCOPE,
                )
            )
        self.assertIn("PREVIEW", preview)
        sender.assert_not_awaited()

    def test_no_model_operation_sends_telegram(self):
        with patch.object(
            TelegramService,
            "send_message_receipt",
            new=AsyncMock(),
        ) as sender:
            self.bootstrap()
            self.service.show_champion(SCOPE)
            self.service.list_generations(SCOPE, 20)
            self.service.diagnose_state(SCOPE)
        sender.assert_not_awaited()


class ModelOperationsCliTests(unittest.TestCase):
    def test_cli_help_and_command_registration(self):
        parser = build_parser()
        subparser_action = next(
            action
            for action in parser._actions
            if isinstance(action, __import__("argparse")._SubParsersAction)
        )
        self.assertEqual(
            set(subparser_action.choices),
            {
                "bootstrap-champion",
                "prepare-activation",
                "execute-activation",
                "prepare-rollback",
                "execute-rollback",
                "show-champion",
                "show-activation",
                "list-generations",
                "diagnose-state",
            },
        )

    def test_known_failure_has_no_traceback_and_nonzero_exit(self):
        def failed_builder(args):
            raise ModelOperationsConfigurationError("bad database")

        output = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(
                [
                    "show-champion",
                    "--database",
                    "missing.db",
                    "--environment",
                    "lab",
                    "--scope",
                    SCOPE,
                ],
                service_builder=failed_builder,
            )
        self.assertNotEqual(code, 0)
        self.assertNotIn("Traceback", output.getvalue() + errors.getvalue())
        self.assertIn("DATABASE_REJECTED", output.getvalue())

    def test_json_cli_output_is_deterministic(self):
        result = OperatorResult(
            "show-champion",
            "CHAMPION_SHOWN",
            True,
            OperationMode.READ_ONLY,
            False,
            SCOPE,
        )
        service = SimpleNamespace(show_champion=lambda scope: result)
        opened = SimpleNamespace(close=Mock())
        builder = lambda args: (service, opened)
        argv = [
            "show-champion",
            "--database",
            "fictional.db",
            "--environment",
            "lab",
            "--scope",
            SCOPE,
            "--output",
            "json",
        ]
        outputs = []
        for _ in range(2):
            stream = io.StringIO()
            with redirect_stdout(stream):
                self.assertEqual(main(argv, service_builder=builder), 0)
            outputs.append(stream.getvalue())
        self.assertEqual(outputs[0], outputs[1])

    def test_import_and_help_do_not_execute_operations(self):
        service = Mock(spec=ModelOperationsService)
        with patch(
            "app.model_operations.commands.build_service"
        ) as builder:
            parser = build_parser()
            self.assertIn("manual", parser.description.casefold())
        builder.assert_not_called()
        service.bootstrap_champion.assert_not_called()
        service.execute_activation.assert_not_called()
        service.execute_rollback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
