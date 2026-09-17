"""Disabled-by-default, fail-open-to-champion optional adapter."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    champion_candidate: object
    attempted: bool
    shadow_outcome: object | None
    safe_error: str | None


def evaluate_shadow_after_champion_candidate(
    champion_candidate, *, service=None, command=None, enabled=False,
):
    """Return the champion unchanged regardless of shadow availability/failure."""
    if not enabled or service is None or command is None:
        return ShadowObservation(champion_candidate, False, None, None)
    try:
        outcome = service.run(command)
        return ShadowObservation(champion_candidate, True, outcome, None)
    except Exception as exc:  # isolation boundary deliberately protects champion
        return ShadowObservation(champion_candidate, True, None, type(exc).__name__)
