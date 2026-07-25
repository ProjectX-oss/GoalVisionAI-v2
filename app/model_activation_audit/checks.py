"""Independent schema, evidence, architecture, and documentation checks."""

from __future__ import annotations

import json
from pathlib import Path

from .models import AuditCheck, AuditSeverity
from .policy import (
    ACTIVATION_TABLES,
    REQUIRED_FOREIGN_KEYS,
    REQUIRED_INDEXES,
    REQUIRED_TRIGGERS,
)


def run_checks(repository, scope: str, project_root: Path) -> tuple[AuditCheck, ...]:
    checks: list[AuditCheck] = []

    def add(
        check_id: str,
        category: str,
        passed: bool,
        success: str,
        failure: str,
        evidence: tuple[str, ...] = (),
        *,
        mandatory: bool = True,
        success_severity: AuditSeverity = AuditSeverity.PASS,
    ) -> None:
        checks.append(
            AuditCheck(
                check_id,
                category,
                success_severity if passed else AuditSeverity.BLOCKER,
                success if passed else failure,
                evidence,
                mandatory=mandatory,
            )
        )

    version = _safe_scalar(
        repository, "SELECT MAX(version) FROM schema_migrations", default=0
    )
    add(
        "schema.version",
        "SCHEMA",
        int(version or 0) >= 31,
        f"Schema version {version} includes migration v31.",
        "Schema is older than required migration v31.",
        ("schema_migrations",),
    )
    tables = repository.object_names("table")
    missing_tables = sorted(set(ACTIVATION_TABLES) - tables)
    add(
        "schema.tables",
        "SCHEMA",
        not missing_tables,
        "All activation and rollback tables exist.",
        f"Missing required tables: {', '.join(missing_tables)}.",
        ACTIVATION_TABLES,
    )
    indexes = repository.object_names("index")
    missing_indexes = sorted(set(REQUIRED_INDEXES) - indexes)
    add(
        "schema.indexes",
        "SCHEMA",
        not missing_indexes,
        "All required lookup indexes exist.",
        f"Missing required indexes: {', '.join(missing_indexes)}.",
        REQUIRED_INDEXES,
    )
    triggers = repository.object_names("trigger")
    missing_triggers = sorted(set(REQUIRED_TRIGGERS) - triggers)
    malformed_triggers = sorted(
        name
        for name in REQUIRED_TRIGGERS
        if name in triggers
        and (
            "RAISE(ABORT" not in repository.object_sql("trigger", name).upper()
            or (
                "BEFORE UPDATE"
                if name.endswith("_no_update")
                else "BEFORE DELETE"
            )
            not in repository.object_sql("trigger", name).upper()
        )
    )
    add(
        "schema.append_only_triggers",
        "SCHEMA",
        not missing_triggers and not malformed_triggers,
        "Every activation table has update/delete prevention triggers.",
        (
            "Append-only triggers are missing or malformed: "
            + ", ".join(missing_triggers + malformed_triggers)
            + "."
        ),
        REQUIRED_TRIGGERS,
    )
    missing_fks = []
    for table, expected in REQUIRED_FOREIGN_KEYS.items():
        if table in tables:
            missing_fks.extend(
                f"{table}.{column}->{target}"
                for column, target in sorted(
                    expected - repository.foreign_keys(table)
                )
            )
    add(
        "schema.foreign_keys",
        "SCHEMA",
        not missing_fks and not repository.foreign_key_failures(),
        "Declared and stored foreign-key relationships are intact.",
        "Foreign-key declarations or stored references are incomplete.",
        tuple(missing_fks) or ("PRAGMA foreign_key_check",),
    )
    constraints = " ".join(
        repository.object_sql("table", table) for table in ACTIVATION_TABLES
    ).upper()
    required_constraint_fragments = (
        "UNIQUE (MODEL_SCOPE,GENERATION_NUMBER)",
        "ACTIVATION_EXECUTION_REQUEST_ID TEXT NOT NULL UNIQUE",
        "ROLLBACK_EXECUTION_REQUEST_ID TEXT NOT NULL UNIQUE",
        "ACTIVATION_PLAN_ID TEXT NOT NULL UNIQUE",
        "ROLLBACK_PLAN_ID TEXT NOT NULL UNIQUE",
    )
    missing_constraints = [
        item for item in required_constraint_fragments if item not in constraints
    ]
    add(
        "schema.uniqueness_idempotency",
        "SCHEMA",
        not missing_constraints,
        "Generation uniqueness and execution idempotency are enforced.",
        "Required uniqueness/idempotency constraints are absent.",
        tuple(missing_constraints) or ("sqlite_master",),
    )
    duplicate_generations = _safe_scalar(
        repository,
        """
        SELECT COUNT(*) FROM (
          SELECT model_scope,generation_number
          FROM model_champion_generations
          GROUP BY model_scope,generation_number HAVING COUNT(*)>1
        )
        """,
        default=1,
    )
    add(
        "registry.current_enforcement",
        "REGISTRY",
        (
            "UNIQUE (MODEL_SCOPE,GENERATION_NUMBER)" in constraints
            and duplicate_generations == 0
        ),
        (
            "One current champion is derived deterministically as the unique "
            "highest generation per scope; there is no mutable active flag."
        ),
        "Exactly-one-current champion enforcement is ineffective.",
        ("model_champion_generations",),
    )

    if missing_tables:
        return tuple(checks)
    if "model_champion_generations" not in tables:
        return tuple(checks)
    generations = repository.rows(
        """
        SELECT * FROM model_champion_generations
        WHERE model_scope=? ORDER BY generation_number,champion_generation_id
        """,
        (scope,),
    )
    ids = {row["champion_generation_id"] for row in generations}
    sequence_ok = bool(generations)
    bootstrap_count = 0
    for index, row in enumerate(generations, 1):
        expected_previous = (
            generations[index - 2]["champion_generation_id"]
            if index > 1
            else None
        )
        sequence_ok &= (
            row["generation_number"] == index
            and row["previous_champion_generation_id"] == expected_previous
        )
        if row["activation_plan_id"] is None and row["rollback_plan_id"] is None:
            bootstrap_count += 1
    add(
        "registry.generation_chain",
        "REGISTRY",
        sequence_ok,
        "Generation chain is contiguous, acyclic, and correctly linked.",
        "Generation chain is empty, cyclic, gapped, or incorrectly linked.",
        tuple(sorted(ids)),
    )
    add(
        "registry.bootstrap_unique",
        "REGISTRY",
        bootstrap_count == 1,
        "Exactly one bootstrap generation exists for the reviewed scope.",
        "The reviewed scope does not have exactly one bootstrap generation.",
        (f"bootstrap_count={bootstrap_count}",),
    )
    event_orphans = _safe_scalar(
        repository,
        """
        SELECT COUNT(*) FROM model_champion_registry_events e
        LEFT JOIN model_champion_generations g
          ON g.champion_generation_id=e.champion_generation_id
        WHERE g.champion_generation_id IS NULL
        """,
        default=1,
    )
    add(
        "registry.events_referential",
        "REGISTRY",
        event_orphans == 0,
        "Registry events have no orphan generation references.",
        "One or more registry events reference missing generations.",
        ("model_champion_registry_events",),
    )
    event_ok = _registry_events_consistent(repository, generations, scope)
    add(
        "registry.event_sequence",
        "REGISTRY",
        event_ok,
        "Bootstrap, retirement, activation, and rollback events are consistent.",
        "Registry event types or ordering are inconsistent with generations.",
        ("model_champion_registry_events",),
    )

    _activation_checks(repository, scope, add)
    _rollback_checks(repository, scope, add)
    _resolver_persistence_check(repository, scope, generations, add)
    _static_checks(project_root, add)
    return tuple(checks)


def _activation_checks(repository, scope, add) -> None:
    executions = repository.rows(
        """
        SELECT e.*, p.activation_request_id,p.expected_generation_number,
               p.expected_registry_fingerprint,p.plan_snapshot,
               r.request_snapshot
        FROM model_activation_executions e
        LEFT JOIN model_activation_plans p ON p.activation_plan_id=e.activation_plan_id
        LEFT JOIN model_activation_requests r ON r.activation_request_id=p.activation_request_id
        JOIN model_champion_generations g ON g.champion_generation_id=e.champion_generation_id
        WHERE g.model_scope=?
        """,
        (scope,),
    )
    references_ok = all(
        row["activation_request_id"]
        and row["activation_plan_fingerprint"] == json.loads(row["plan_snapshot"])[
            "activation_plan_fingerprint"
        ]
        for row in executions
    )
    add(
        "activation.plan_execution_chain",
        "ACTIVATION",
        bool(executions) and references_ok,
        "Each activation execution links to one immutable request and plan.",
        "Activation execution evidence chain is missing or inconsistent.",
        tuple(row["activation_plan_id"] for row in executions),
    )
    plan_ids = tuple(row["activation_plan_id"] for row in executions)
    validations_ok = bool(plan_ids)
    evidence_ok = bool(plan_ids)
    promotion_ok = bool(plan_ids)
    stale_ok = bool(plan_ids)
    artifact_ok = bool(plan_ids)
    for row in executions:
        request = json.loads(row["request_snapshot"])
        validations = repository.rows(
            """
            SELECT validation_status,deterministic_order
            FROM model_activation_validations
            WHERE activation_plan_id=? ORDER BY deterministic_order
            """,
            (row["activation_plan_id"],),
        )
        validations_ok &= len(validations) == 9 and all(
            item["validation_status"] == "PASS"
            and item["deterministic_order"] == index
            for index, item in enumerate(validations)
        )
        links = repository.rows(
            """
            SELECT l.*,s.execution_fingerprint,t.settlement_fingerprint,
                   s.comparison_run_id,s.challenger_candidate_id,
                   s.champion_model_artifact_id,s.challenger_model_artifact_id
            FROM model_activation_evidence_links l
            LEFT JOIN shadow_evaluation_executions s
              ON s.shadow_execution_id=l.shadow_execution_id
            LEFT JOIN shadow_evaluation_settlements t
              ON t.shadow_execution_id=l.shadow_execution_id
            WHERE l.activation_plan_id=? ORDER BY l.deterministic_order
            """,
            (row["activation_plan_id"],),
        )
        evidence_ok &= bool(links) and all(
            link["execution_fingerprint"] == link["shadow_execution_fingerprint"]
            and link["settlement_fingerprint"]
            == link["shadow_settlement_fingerprint"]
            and link["deterministic_order"] == index
            and link["comparison_run_id"] == request["comparison_run_id"]
            and link["challenger_candidate_id"]
            == request["challenger_candidate_id"]
            and link["champion_model_artifact_id"]
            == request["current_champion"]["model_artifact_id"]
            and link["challenger_model_artifact_id"]
            == request["challenger"]["model_artifact_id"]
            for index, link in enumerate(links)
        )
        rec = repository.rows(
            """
            SELECT recommendation,recommendation_fingerprint,comparison_run_id
            FROM model_comparison_recommendations WHERE recommendation_id=?
            """,
            (request["recommendation_id"],),
        )
        promotion_ok &= (
            len(rec) == 1
            and rec[0]["recommendation"] == "PROMOTE_CHALLENGER"
            and rec[0]["recommendation_fingerprint"]
            == request["recommendation_fingerprint"]
            and rec[0]["comparison_run_id"] == request["comparison_run_id"]
        )
        stale_ok &= (
            row["expected_generation_number"]
            == repository.scalar(
                """
                SELECT generation_number FROM model_champion_generations
                WHERE champion_generation_id=(
                  SELECT previous_champion_generation_id
                  FROM model_champion_generations
                  WHERE champion_generation_id=?
                )
                """,
                (row["champion_generation_id"],),
            )
            and row["expected_registry_fingerprint"]
            == repository.scalar(
                """
                SELECT generation_fingerprint FROM model_champion_generations
                WHERE champion_generation_id=(
                  SELECT previous_champion_generation_id
                  FROM model_champion_generations
                  WHERE champion_generation_id=?
                )
                """,
                (row["champion_generation_id"],),
            )
        )
        generation = repository.rows(
            "SELECT generation_snapshot FROM model_champion_generations WHERE champion_generation_id=?",
            (row["champion_generation_id"],),
        )
        artifact_ok &= bool(generation) and _artifact_references_exist(
            repository, json.loads(generation[0]["generation_snapshot"])["artifact"]
        )
    add(
        "activation.validations",
        "ACTIVATION",
        validations_ok,
        "Activation validations are complete, deterministic, and PASS.",
        "Activation validations are missing, non-deterministic, or not PASS.",
        plan_ids,
    )
    add(
        "activation.shadow_evidence",
        "ACTIVATION",
        evidence_ok,
        "Settled shadow evidence links and fingerprints match exactly.",
        "Required settled shadow evidence is missing or mismatched.",
        plan_ids,
    )
    add(
        "activation.promotion",
        "ACTIVATION",
        promotion_ok,
        "Promotion evidence is the exact PROMOTE_CHALLENGER recommendation.",
        "Promotion recommendation is missing, mismatched, or not PROMOTE_CHALLENGER.",
        plan_ids,
    )
    add(
        "activation.not_stale",
        "ACTIVATION",
        stale_ok,
        "Executed plans matched the replaced registry generation.",
        "An executed activation plan was stale against its replaced generation.",
        plan_ids,
    )
    add(
        "activation.artifact_provenance",
        "ACTIVATION",
        artifact_ok,
        "Activated model and calibration artifact references exist.",
        "Activated artifact provenance is incomplete.",
        plan_ids,
    )
    duplicate_execution = _safe_scalar(
        repository,
        """
        SELECT COUNT(*) FROM (
          SELECT activation_plan_id FROM model_activation_executions
          GROUP BY activation_plan_id HAVING COUNT(*)>1
        )
        """,
        default=1,
    )
    add(
        "activation.idempotency",
        "ACTIVATION",
        duplicate_execution == 0,
        "No activation plan was executed more than once.",
        "Duplicate activation execution rows exist.",
        ("model_activation_executions",),
    )


def _rollback_checks(repository, scope, add) -> None:
    rows = repository.rows(
        """
        SELECT e.*,p.rollback_request_id,p.target_champion_generation_id,
               p.expected_generation_number,p.expected_registry_fingerprint,
               p.plan_snapshot,r.request_snapshot,g.previous_champion_generation_id,
               g.model_artifact_id,g.calibration_artifact_set_id
        FROM model_rollback_executions e
        LEFT JOIN model_rollback_plans p ON p.rollback_plan_id=e.rollback_plan_id
        LEFT JOIN model_rollback_requests r ON r.rollback_request_id=p.rollback_request_id
        JOIN model_champion_generations g ON g.champion_generation_id=e.champion_generation_id
        WHERE g.model_scope=?
        """,
        (scope,),
    )
    chain_ok = bool(rows)
    semantics_ok = bool(rows)
    reason_ok = bool(rows)
    target_ok = bool(rows)
    validations_ok = bool(rows)
    for row in rows:
        request = json.loads(row["request_snapshot"])
        chain_ok &= bool(row["rollback_request_id"] and row["plan_snapshot"])
        target = repository.rows(
            "SELECT * FROM model_champion_generations WHERE champion_generation_id=?",
            (row["target_champion_generation_id"],),
        )
        replaced = repository.rows(
            "SELECT * FROM model_champion_generations WHERE champion_generation_id=?",
            (row["previous_champion_generation_id"],),
        )
        target_ok &= (
            len(target) == 1
            and target[0]["generation_number"] < row["expected_generation_number"]
            and target[0]["model_artifact_id"] == row["model_artifact_id"]
            and target[0]["calibration_artifact_set_id"]
            == row["calibration_artifact_set_id"]
        )
        semantics_ok &= (
            len(replaced) == 1
            and replaced[0]["generation_number"] == row["expected_generation_number"]
            and replaced[0]["generation_fingerprint"]
            == row["expected_registry_fingerprint"]
            and row["champion_generation_id"]
            != row["target_champion_generation_id"]
        )
        reason_ok &= bool(
            request.get("incident_reference", "").strip()
            and request.get("rollback_reason", "").strip()
            and request.get("operator_identity", "").strip()
        )
        validations = repository.rows(
            """
            SELECT validation_status,deterministic_order
            FROM model_activation_validations
            WHERE rollback_plan_id=? ORDER BY deterministic_order
            """,
            (row["rollback_plan_id"],),
        )
        validations_ok &= bool(validations) and all(
            item["validation_status"] == "PASS"
            and item["deterministic_order"] == index
            for index, item in enumerate(validations)
        )
    add(
        "rollback.plan_execution_chain",
        "ROLLBACK",
        chain_ok,
        "Each rollback execution links to one immutable request and plan.",
        "Rollback request, plan, or execution evidence is missing.",
        tuple(row["rollback_plan_id"] for row in rows),
    )
    add(
        "rollback.target_validity",
        "ROLLBACK",
        target_ok,
        "Rollback targets were previously active and retained compatible artifacts.",
        "Rollback target history or artifact compatibility is invalid.",
        tuple(row["target_champion_generation_id"] for row in rows),
    )
    add(
        "rollback.generation_semantics",
        "ROLLBACK",
        semantics_ok,
        "Rollback appended a new generation linked to the replaced champion.",
        "Rollback reused/mutated a target or has invalid previous linkage.",
        tuple(row["champion_generation_id"] for row in rows),
    )
    add(
        "rollback.incident_evidence",
        "ROLLBACK",
        reason_ok,
        "Rollback incident reference, reason, and operator are present.",
        "Rollback operational justification is incomplete.",
        tuple(row["rollback_request_id"] for row in rows),
    )
    duplicate = _safe_scalar(
        repository,
        """
        SELECT COUNT(*) FROM (
          SELECT rollback_plan_id FROM model_rollback_executions
          GROUP BY rollback_plan_id HAVING COUNT(*)>1
        )
        """,
        default=1,
    )
    add(
        "rollback.validations",
        "ROLLBACK",
        validations_ok,
        "Rollback validations are complete, deterministic, and PASS.",
        "Rollback validations are missing, non-deterministic, or not PASS.",
        tuple(row["rollback_plan_id"] for row in rows),
    )
    add(
        "rollback.idempotency",
        "ROLLBACK",
        duplicate == 0,
        "No rollback plan was executed more than once.",
        "Duplicate rollback execution rows exist.",
        ("model_rollback_executions",),
    )


def _static_checks(project_root: Path, add) -> None:
    cli = _read(project_root / "app/model_operations/cli.py")
    commands = _read(project_root / "app/model_operations/commands.py")
    resolver = _read(project_root / "app/model_activation/resolver.py")
    source_verification = _read(
        project_root / "app/model_activation/source_verification.py"
    )
    runbook = _read(project_root / "docs/model_operations_runbook.md")
    rehearsal = _read(
        project_root / "docs/rehearsals/model_operations_lab_rehearsal.md"
    ) + _read(
        project_root
        / "docs/rehearsals/model_activation_rollback_lab_rehearsal.md"
    )
    all_app = "\n".join(
        _read(path)
        for path in (project_root / "app").rglob("*.py")
        if "model_activation_audit" not in path.parts
    )
    add(
        "resolver.fail_closed",
        "RESOLVER",
        (
            "CHAMPION_STATE_INVALID" in resolver
            and "except Exception" in resolver
            and "verify_runtime_artifact" in resolver
            and all(
                term in source_verification
                for term in (
                    "preprocessing_fingerprint",
                    "feature_schema_fingerprint",
                    "probability_contract_version",
                    "runtime_compatibility_version",
                )
            )
        ),
        "Resolver verifies exact artifacts and fails closed without fallback.",
        "Resolver fail-closed or artifact-verification behavior is incomplete.",
        ("app/model_activation/resolver.py",),
    )
    integration_files = [
        line
        for line in all_app.splitlines()
        if "RuntimeChampionResolver(" in line
    ]
    add(
        "resolver.runtime_unwired",
        "RESOLVER",
        len(integration_files) <= 2 and "scheduler" not in resolver.lower(),
        "Resolver remains confined to manual operations and is not wired to inference.",
        "Resolver appears connected beyond manual inspection boundaries.",
        ("app/model_activation/factory.py", "app/model_operations/commands.py"),
    )
    allowed_manual_roots = {
        "model_activation",
        "model_operations",
        "model_operations_rehearsal",
        "model_activation_audit",
        "staging_model_operations_rehearsal",
    }
    automatic_paths = []
    for path in (project_root / "app").rglob("*.py"):
        relative = path.relative_to(project_root / "app")
        if relative.parts[0] in allowed_manual_roots:
            continue
        content = _read(path)
        if any(
            term in content
            for term in (
                "execute_activation(",
                "execute_rollback(",
                "bootstrap_champion(",
            )
        ):
            automatic_paths.append(str(Path("app") / relative))
    add(
        "activation.manual_only",
        "RESOLVER",
        not automatic_paths,
        "No startup, scheduler, worker, or inference path invokes model switching.",
        "An automatic or non-operations path can invoke model switching.",
        tuple(sorted(automatic_paths)) or ("app/",),
    )
    confirmations = _read(project_root / "app/model_operations/service.py")
    add(
        "cli.confirmations",
        "CLI",
        (
            "--yes" not in cli
            and "--confirm" in cli
            and 'ACTIVATION_CONFIRMATION = "ACTIVATE_CHAMPION"' in confirmations
            and 'ROLLBACK_CONFIRMATION = "ROLLBACK_CHAMPION"' in confirmations
        ),
        "Exact confirmations are required and no generic --yes exists.",
        "State-changing confirmation safety is incomplete.",
        ("app/model_operations/cli.py", "app/model_operations/service.py"),
    )
    add(
        "cli.read_only_inspection",
        "CLI",
        "read_only=args.command in READ_ONLY_COMMANDS" in commands,
        "Inspection commands select the read-only database boundary.",
        "Inspection commands are not demonstrably read-only.",
        ("app/model_operations/commands.py",),
    )
    add(
        "cli.no_side_effect_integrations",
        "CLI",
        "telegram" not in cli.lower() + commands.lower()
        and "bankroll" not in cli.lower() + commands.lower()
        and "publication" not in cli.lower() + commands.lower(),
        "Model operations CLI has no Telegram, bankroll, or publication calls.",
        "Model operations CLI contains an out-of-scope side-effect integration.",
        ("app/model_operations",),
    )
    add(
        "cli.known_failure_guidance",
        "CLI",
        "do not retry an ambiguous execution automatically" in cli.lower()
        and "except Exception:" in cli,
        "Known/ambiguous failures return guidance without raw tracebacks.",
        "CLI failure handling or ambiguous recovery guidance is incomplete.",
        ("app/model_operations/cli.py",),
    )
    rehearsal_terms = (
        "disposable",
        "sha-256",
        "atomic",
        "replay",
        "telegram",
        "runtime",
    )
    add(
        "rehearsal.fidelity",
        "REHEARSAL",
        all(term in rehearsal.lower() for term in rehearsal_terms),
        "Rehearsal evidence covers isolation, hashing, replay, atomicity, and no Telegram/runtime change.",
        "Rehearsal evidence omits a mandatory fidelity statement.",
        (
            "docs/rehearsals/model_operations_lab_rehearsal.md",
            "docs/rehearsals/model_activation_rollback_lab_rehearsal.md",
        ),
    )
    runbook_terms = (
        "do not edit",
        "stale",
        "idempotent",
        "backup",
        "lab-only",
        "runtime inference remains unwired",
        "forbidden in automation",
        "evidence retention",
    )
    add(
        "runbook.consistency",
        "RUNBOOK",
        all(term in runbook.lower() for term in runbook_terms)
        and "--confirm" in runbook
        and "generic confirmation and `--yes` are forbidden" in runbook,
        "Runbook reflects CLI flags, recovery, boundaries, and retention rules.",
        "Runbook is incomplete or inconsistent with operational safety.",
        ("docs/model_operations_runbook.md",),
    )
    add(
        "staging.human_authorization",
        "STAGING",
        "explicit human staging authorization" in runbook.lower(),
        "A separate explicit human staging authorization remains required.",
        "Runbook does not preserve the human staging authorization boundary.",
        ("docs/model_operations_runbook.md",),
    )


def _registry_events_consistent(repository, generations, scope: str) -> bool:
    events = repository.rows(
        """
        SELECT * FROM model_champion_registry_events WHERE model_scope=?
        ORDER BY event_timestamp_utc,registry_event_id
        """,
        (scope,),
    )
    by_generation: dict[str, set[str]] = {}
    for event in events:
        by_generation.setdefault(event["champion_generation_id"], set()).add(
            event["event_type"]
        )
    for index, generation in enumerate(generations):
        types = by_generation.get(generation["champion_generation_id"], set())
        expected_created = (
            "INITIAL_REGISTERED"
            if index == 0
            else (
                "CHAMPION_ACTIVATED"
                if generation["activation_plan_id"]
                else "CHAMPION_ROLLED_BACK"
            )
        )
        if expected_created not in types:
            return False
        if index < len(generations) - 1:
            next_generation = generations[index + 1]
            expected_retired = (
                "RETIRED_BY_ACTIVATION"
                if next_generation["activation_plan_id"]
                else "RETIRED_BY_ROLLBACK"
            )
            if expected_retired not in types:
                return False
    return True


def _resolver_persistence_check(repository, scope, generations, add) -> None:
    try:
        from app.historical_model_training import (
            SQLiteHistoricalModelTrainingRepository,
        )
        from app.historical_probability_calibration import (
            SQLiteHistoricalProbabilityCalibrationRepository,
        )
        from app.model_activation import (
            ActivationStatus,
            DEFAULT_MODEL_ACTIVATION_POLICY,
            RuntimeChampionResolver,
            SQLiteModelActivationRepository,
        )

        resolver = RuntimeChampionResolver(
            SQLiteModelActivationRepository(repository, migrate=False),
            SQLiteHistoricalModelTrainingRepository(repository, migrate=False),
            SQLiteHistoricalProbabilityCalibrationRepository(
                repository, migrate=False
            ),
            DEFAULT_MODEL_ACTIVATION_POLICY,
        )
        resolution = resolver.resolve(scope)
        expected = generations[-1]["champion_generation_id"] if generations else None
        passed = (
            resolution.status is ActivationStatus.CHAMPION_RESOLVED
            and resolution.champion_generation is not None
            and resolution.champion_generation.champion_generation_id == expected
        )
    except Exception:
        passed = False
    add(
        "resolver.exact_current",
        "RESOLVER",
        passed,
        "Existing resolver returns the exact current generation and verified artifact chain.",
        "Existing resolver failed closed or disagreed with the current registry generation.",
        ("app/model_activation/RuntimeChampionResolver",),
    )


def _artifact_references_exist(repository, artifact: dict) -> bool:
    model = repository.rows(
        """
        SELECT artifact_fingerprint,preprocessing_fingerprint,
               compatibility_snapshot
        FROM historical_model_artifacts WHERE artifact_id=?
        """,
        (artifact["model_artifact_id"],),
    )
    calibration = repository.rows(
        """
        SELECT artifact_set_fingerprint,runtime_compatibility_version,
               compatibility_snapshot
        FROM historical_probability_calibration_artifact_sets
        WHERE artifact_set_id=?
        """,
        (artifact["calibration_artifact_set_id"],),
    )
    if len(model) != 1 or len(calibration) != 1:
        return False
    model_compatibility = json.loads(model[0]["compatibility_snapshot"])
    calibration_compatibility = json.loads(
        calibration[0]["compatibility_snapshot"]
    )
    return bool(
        model[0]["artifact_fingerprint"] == artifact["model_artifact_fingerprint"]
        and model[0]["preprocessing_fingerprint"]
        == artifact["preprocessing_fingerprint"]
        and model_compatibility["feature_schema_version"]
        == artifact["feature_schema_version"]
        and model_compatibility["feature_schema_fingerprint"]
        == artifact["feature_schema_fingerprint"]
        and model_compatibility["target_schema_version"]
        == artifact["target_contract_version"]
        and calibration[0]["artifact_set_fingerprint"]
        == artifact["calibration_artifact_set_fingerprint"]
        and calibration_compatibility["source_model_artifact_id"]
        == artifact["model_artifact_id"]
        and calibration[0]["runtime_compatibility_version"]
        == artifact["runtime_compatibility_version"]
    )


def _safe_scalar(repository, sql: str, default):
    try:
        return repository.scalar(sql)
    except Exception:
        return default


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
