"""Prevent transport log records from exposing Lab credentials."""
from __future__ import annotations

import logging


class SecretRedactionFilter(logging.Filter):
    def __init__(self, secrets: tuple[str, ...]) -> None:
        super().__init__()
        self.secrets = tuple(value for value in secrets if value)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secrets:
            message = message.replace(secret, "[REDACTED]")
        record.msg = message
        record.args = ()
        return True


def install_lab_secret_redaction(*secrets: str) -> SecretRedactionFilter:
    """Install process-local redaction before constructing Telegram clients."""
    value = SecretRedactionFilter(tuple(secrets))
    for name in ("httpx", "httpcore", "telegram"):
        logging.getLogger(name).addFilter(value)
    for handler in logging.getLogger().handlers:
        handler.addFilter(value)
    return value
