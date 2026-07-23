"""Read-only registry and plan inspection."""

from .fingerprint import sha256_fingerprint


def inspect_active_champion(repository, model_scope):
    try:
        return repository.resolve_current_champion(model_scope)
    except Exception:
        return None


def inspect_champion_history(repository, model_scope):
    return repository.list_generations(model_scope)


def inspect_activation_plan(repository, plan_id):
    return repository.load_activation_plan(plan_id)


def inspect_rollback_plan(repository, plan_id):
    return repository.load_rollback_plan(plan_id)


def verify_generation_chain(repository, model_scope):
    rows = repository.list_generations(model_scope)
    failures = []
    for index, item in enumerate(rows, 1):
        if item.generation_number != index:
            failures.append(f"{item.champion_generation_id}:GENERATION_SEQUENCE_GAP")
        expected_previous = rows[index - 2].champion_generation_id if index > 1 else None
        if item.previous_champion_generation_id != expected_previous:
            failures.append(f"{item.champion_generation_id}:PREVIOUS_GENERATION_MISMATCH")
    return tuple(failures)


def export_activation_audit(repository, model_scope):
    rows = repository.list_generations(model_scope)
    return tuple({
        "generation_id": item.champion_generation_id,
        "generation_number": item.generation_number,
        "model_artifact_id": item.artifact.model_artifact_id,
        "reason": item.activation_reason.value,
        "fingerprint": item.generation_fingerprint,
    } for item in rows)
