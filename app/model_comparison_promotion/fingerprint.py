"""Canonical SHA-256 identities for comparison evidence."""

from app.historical_backtesting.fingerprint import (
    canonical_decimal,
    canonical_json,
    sha256_fingerprint,
)


def comparison_request_fingerprint(command) -> str:
    return sha256_fingerprint(command)


def source_compatibility_fingerprint(evidence) -> str:
    return sha256_fingerprint(
        tuple(
            (
                item.category,
                item.name,
                item.champion_value_snapshot,
                item.challenger_value_snapshot,
                item.compatibility_status,
                item.detail_snapshot,
                item.evidence_fingerprint,
                item.deterministic_order,
            )
            for item in evidence
        )
    )


def metric_comparison_fingerprint(evaluation) -> str:
    return sha256_fingerprint(evaluation)


def stability_fingerprint(groups, policy_version: str) -> str:
    return sha256_fingerprint((groups, policy_version))


def statistical_evidence_fingerprint(evidence) -> str:
    return sha256_fingerprint(evidence)


def challenger_evaluation_fingerprint(evaluation) -> str:
    return sha256_fingerprint(evaluation)


def comparison_run_fingerprint(
    request_fingerprint: str,
    evaluation_fingerprints: tuple[str, ...],
    ranking: tuple[str, ...],
    recommendation: str,
    policy_versions,
) -> str:
    return sha256_fingerprint(
        {
            "request_fingerprint": request_fingerprint,
            "evaluation_fingerprints": evaluation_fingerprints,
            "ranking": ranking,
            "recommendation": recommendation,
            "policy_versions": policy_versions,
        }
    )


__all__ = [
    "canonical_decimal",
    "canonical_json",
    "sha256_fingerprint",
    "comparison_request_fingerprint",
    "source_compatibility_fingerprint",
    "metric_comparison_fingerprint",
    "stability_fingerprint",
    "statistical_evidence_fingerprint",
    "challenger_evaluation_fingerprint",
    "comparison_run_fingerprint",
]
