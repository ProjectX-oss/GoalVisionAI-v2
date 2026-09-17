"""Inert manual-only CLI for reviewed champion model operations."""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Sequence

from .commands import build_service, dispatch
from .configuration import ModelOperationsConfigurationError
from .formatting import format_result_human, format_result_json
from .models import OperationMode, OperatorResult, OperatorStatus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goalvision-model-operations",
        description=(
            "Manual reviewed champion bootstrap, activation, rollback, "
            "inspection, and diagnostics. Never scheduled."
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    bootstrap = subcommands.add_parser(
        "bootstrap-champion",
        help="One-time explicit champion bootstrap.",
    )
    _common(bootstrap)
    _artifact_arguments(bootstrap)
    bootstrap.add_argument("--timestamp", required=True)
    bootstrap.add_argument("--reason", required=True)
    bootstrap.add_argument("--operator", required=True)

    prepare_activation = subcommands.add_parser(
        "prepare-activation",
        help="Prepare and persist an immutable activation plan only.",
    )
    _common(prepare_activation)
    prepare_activation.add_argument("--request-id", required=True)
    prepare_activation.add_argument("--name", required=True)
    prepare_activation.add_argument("--current-generation-id", required=True)
    prepare_activation.add_argument(
        "--current-generation-fingerprint",
        required=True,
    )
    _artifact_arguments(prepare_activation, "current")
    _artifact_arguments(prepare_activation, "challenger")
    prepare_activation.add_argument("--comparison-run-id", required=True)
    prepare_activation.add_argument(
        "--comparison-run-fingerprint",
        required=True,
    )
    prepare_activation.add_argument(
        "--challenger-candidate-id",
        required=True,
    )
    prepare_activation.add_argument("--recommendation-id", required=True)
    prepare_activation.add_argument(
        "--recommendation-fingerprint",
        required=True,
    )
    prepare_activation.add_argument(
        "--shadow-evidence-fingerprint",
        required=True,
    )
    prepare_activation.add_argument("--evidence-cutoff", required=True)
    prepare_activation.add_argument("--requested-at", required=True)
    prepare_activation.add_argument("--reason", required=True)
    prepare_activation.add_argument("--operator", required=True)
    prepare_activation.add_argument("--warning-override-reason")

    execute_activation = subcommands.add_parser(
        "execute-activation",
        help="Explicitly execute one exact reviewed activation plan.",
    )
    _common(execute_activation)
    execute_activation.add_argument(
        "--execution-request-id",
        required=True,
    )
    execute_activation.add_argument("--plan-id", required=True)
    execute_activation.add_argument("--plan-fingerprint", required=True)
    execute_activation.add_argument("--executed-at", required=True)
    execute_activation.add_argument("--operator", required=True)
    execute_activation.add_argument("--confirm", required=True)

    prepare_rollback = subcommands.add_parser(
        "prepare-rollback",
        help="Prepare and persist an immutable rollback plan only.",
    )
    _common(prepare_rollback)
    prepare_rollback.add_argument("--request-id", required=True)
    prepare_rollback.add_argument("--name", required=True)
    prepare_rollback.add_argument("--current-generation-id", required=True)
    prepare_rollback.add_argument(
        "--current-generation-fingerprint",
        required=True,
    )
    prepare_rollback.add_argument("--target-generation-id", required=True)
    prepare_rollback.add_argument("--reason", required=True)
    prepare_rollback.add_argument("--incident-reference", required=True)
    prepare_rollback.add_argument("--operator", required=True)
    prepare_rollback.add_argument("--requested-at", required=True)

    execute_rollback = subcommands.add_parser(
        "execute-rollback",
        help="Explicitly execute one exact reviewed rollback plan.",
    )
    _common(execute_rollback)
    execute_rollback.add_argument(
        "--execution-request-id",
        required=True,
    )
    execute_rollback.add_argument("--plan-id", required=True)
    execute_rollback.add_argument("--plan-fingerprint", required=True)
    execute_rollback.add_argument("--executed-at", required=True)
    execute_rollback.add_argument("--operator", required=True)
    execute_rollback.add_argument("--confirm", required=True)

    show_champion = subcommands.add_parser(
        "show-champion",
        help="Resolve and inspect the current champion without writes.",
    )
    _common(show_champion)

    show_activation = subcommands.add_parser(
        "show-activation",
        help="Inspect one activation or rollback audit chain without writes.",
    )
    _common(show_activation)
    show_activation.add_argument("--plan-id", required=True)

    generations = subcommands.add_parser(
        "list-generations",
        help="List immutable champion generations without writes.",
    )
    _common(generations)
    generations.add_argument("--limit", type=int, default=20)

    diagnose = subcommands.add_parser(
        "diagnose-state",
        help="Fail-closed read-only champion and activation diagnostics.",
    )
    _common(diagnose)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    service_builder: Callable = build_service,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    opened = None
    try:
        service, opened = service_builder(args)
        result = dispatch(args, service)
    except ModelOperationsConfigurationError as exc:
        result = _failure(
            args.command,
            OperatorStatus.DATABASE_REJECTED,
            "CONFIGURATION_REJECTED",
            str(exc),
        )
    except Exception:
        result = _failure(
            args.command,
            OperatorStatus.INTERNAL_FAILURE,
            "UNEXPECTED_INTERNAL_FAILURE",
            (
                "Run read-only diagnostics and inspect the audit trail; "
                "do not retry an ambiguous execution automatically."
            ),
        )
    finally:
        if opened is not None:
            opened.close()
    output = (
        format_result_json(result)
        if args.output == "json"
        else format_result_human(result)
    )
    print(output)
    return result.exit_code


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", required=True)
    parser.add_argument(
        "--environment",
        required=True,
        choices=("lab", "staging", "production"),
    )
    parser.add_argument(
        "--scope",
        required=True,
        choices=("OFFICIAL_GLOBAL",),
    )
    parser.add_argument(
        "--output",
        choices=("human", "json"),
        default="human",
    )


def _artifact_arguments(
    parser: argparse.ArgumentParser,
    prefix: str | None = None,
) -> None:
    option_prefix = f"{prefix}-" if prefix else ""
    destination_prefix = f"{prefix}_" if prefix else ""
    fields = (
        "model-artifact-id",
        "model-artifact-fingerprint",
        "preprocessing-fingerprint",
        "calibration-artifact-set-id",
        "calibration-artifact-set-fingerprint",
        "feature-schema-version",
        "feature-schema-fingerprint",
        "target-contract-version",
        "probability-contract-version",
        "runtime-compatibility-version",
    )
    for field in fields:
        parser.add_argument(
            f"--{option_prefix}{field}",
            dest=destination_prefix + field.replace("-", "_"),
            required=True,
        )


def _failure(
    command: str,
    status: OperatorStatus,
    reason: str,
    recovery: str,
) -> OperatorResult:
    return OperatorResult(
        command=command,
        status=status.value,
        success=False,
        mode=(
            OperationMode.READ_ONLY
            if command
            in {
                "show-champion",
                "show-activation",
                "list-generations",
                "diagnose-state",
            }
            else OperationMode.STATE_CHANGING
        ),
        production_state_changed=False,
        reason_codes=(reason,),
        recovery_guidance=(recovery,),
    )


if __name__ == "__main__":
    sys.exit(main())
