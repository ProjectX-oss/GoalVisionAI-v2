"""Read-only integrity, reproduction, and evidence-export helpers."""

from .fingerprint import sha256_fingerprint
from .probability_contract import verify_probability_contract


def verify_shadow_execution_fingerprint(repository, execution_id):
    item = repository.load_shadow_execution(execution_id)
    if item is None:
        return ("MISSING_EXECUTION",)
    expected = sha256_fingerprint({
        "request_fingerprint": item.request_fingerprint,
        "input_snapshot_fingerprint": item.input_snapshot.input_snapshot_fingerprint,
        "odds_snapshot_set_fingerprint": item.odds_snapshot_set.odds_snapshot_set_fingerprint,
        "inferences": tuple(row.calibrated_inference_fingerprint for row in item.inferences),
        "assessments": tuple(row.assessment_fingerprint for row in item.market_assessments),
        "selections": tuple(row.selection_fingerprint for row in item.selections),
        "comparison": item.comparison.comparison_fingerprint,
        "metrics": tuple(row.metric_fingerprint for row in item.metrics if row.phase == "PRE_MATCH"),
        "policy": item.command.shadow_policy_version,
    })
    return () if expected == item.execution_fingerprint else ("EXECUTION_FINGERPRINT_MISMATCH",)


def verify_shared_input_identity(execution):
    return () if len(execution.inferences) == 2 else ("MISSING_MODEL_ROLE",)


def verify_shared_odds_identity(execution):
    supplied = {item.odds_snapshot_id for item in execution.odds_snapshot_set.snapshots}
    used = {item.odds_snapshot_id for item in execution.market_assessments if item.odds_snapshot_id}
    return () if used <= supplied else ("UNSUPPLIED_ODDS_USED",)


def verify_probability_contracts(execution):
    failures = []
    for item in execution.inferences:
        try:
            verify_probability_contract(item.raw_probabilities)
            verify_probability_contract(item.calibrated_probabilities)
        except Exception:
            failures.append(f"{item.model_role.value}:PROBABILITY_CONTRACT_FAILURE")
    return tuple(failures)


def reproduce_shadow_decisions(repository, execution_id):
    item = repository.load_shadow_execution(execution_id)
    return item.selections if item else ()


def reproduce_shadow_comparison(repository, execution_id):
    item = repository.load_shadow_execution(execution_id)
    return item.comparison if item else None


def verify_shadow_settlement(repository, execution_id):
    item = repository.find_settlement_for_execution(execution_id)
    return () if item else ("UNSETTLED",)


def export_shadow_evidence(repository, execution_id):
    item = repository.load_shadow_execution(execution_id)
    if item is None:
        return None
    settlement = repository.find_settlement_for_execution(execution_id)
    return {
        "shadow_execution_id": item.shadow_execution_id,
        "execution_fingerprint": item.execution_fingerprint,
        "champion_model_artifact_id": item.command.champion_model_artifact_id,
        "challenger_model_artifact_id": item.command.challenger_model_artifact_id,
        "disagreement_type": item.comparison.disagreement_type.value,
        "severity": item.comparison.severity.value,
        "settled": settlement is not None,
        "settlement_fingerprint": settlement.settlement_fingerprint if settlement else None,
    }


def inspect_shadow_execution(repository, execution_id):
    item = repository.load_shadow_execution(execution_id)
    return {
        "execution": item,
        "fingerprint_failures": verify_shadow_execution_fingerprint(repository, execution_id),
        "probability_failures": verify_probability_contracts(item) if item else ("MISSING_EXECUTION",),
        "settlement": repository.find_settlement_for_execution(execution_id) if item else None,
    }
