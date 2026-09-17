"""Environment-only provider credential loading with no import-time reads."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .provider_models import HistoricalOddsProvider, ProviderCredentialConfig


PROVIDER_ENVIRONMENT_VARIABLES = {
    HistoricalOddsProvider.THESTATSAPI: "GOALVISION_THESTATSAPI_API_KEY",
    HistoricalOddsProvider.THE_ODDS_API: "GOALVISION_THE_ODDS_API_KEY",
}


def load_provider_credential(
    provider: HistoricalOddsProvider, environment: Mapping[str, str] | None = None,
) -> ProviderCredentialConfig:
    values = os.environ if environment is None else environment
    variable = PROVIDER_ENVIRONMENT_VARIABLES[provider]
    secret = values.get(variable, "").strip()
    return ProviderCredentialConfig(provider, variable, bool(secret), secret or None)
