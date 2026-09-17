"""Read-only grouping keys for future rolling evidence."""


def aggregate_group_keys(execution):
    command = execution.command
    return (
        ("OVERALL", "ALL"),
        ("MODEL_PAIR", f"{command.champion_model_artifact_id}:{command.challenger_model_artifact_id}"),
        ("MARKET", execution.comparison.disagreement_type.value),
        ("COMPETITION", command.competition),
        ("SEVERITY", execution.comparison.severity.value),
    )
