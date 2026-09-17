"""Lazy, secret-safe API-Football credential resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values


CANONICAL_API_FOOTBALL_ENVIRONMENT_VARIABLE = "FOOTBALL_API_KEY"


class FootballCredentialError(RuntimeError):
    """Raised when the canonical API-Football credential is unavailable or ambiguous."""


class FootballCredentialConflictError(FootballCredentialError):
    """Raised when canonical credential sources disagree."""


def resolve_api_football_credential(
    explicit: str | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    env_file: Path | str = Path(".env"),
) -> str:
    """Resolve the existing canonical credential without mutating process state.

    Explicit dependency injection is authoritative. Otherwise a process value and
    a project ``.env`` value must agree when both are configured.
    """

    supplied = _clean(explicit)
    if supplied is not None:
        return supplied
    values = os.environ if environment is None else environment
    process_value = _clean(values.get(CANONICAL_API_FOOTBALL_ENVIRONMENT_VARIABLE))
    file_value = _clean(dotenv_values(env_file).get(CANONICAL_API_FOOTBALL_ENVIRONMENT_VARIABLE))
    if process_value is not None and file_value is not None and process_value != file_value:
        raise FootballCredentialConflictError(
            "Conflicting FOOTBALL_API_KEY values were found in the process and project environment."
        )
    resolved = process_value or file_value
    if resolved is None:
        raise FootballCredentialError("FOOTBALL_API_KEY not found.")
    return resolved


def api_football_credential_status(
    *, environment: Mapping[str, str] | None = None, env_file: Path | str = Path(".env")
) -> str:
    """Return a status label only; never return or expose the credential."""

    try:
        resolve_api_football_credential(environment=environment, env_file=env_file)
    except FootballCredentialConflictError:
        return "INVALID"
    except FootballCredentialError:
        return "NOT_CONFIGURED"
    return "CONFIGURED"


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    return result or None
