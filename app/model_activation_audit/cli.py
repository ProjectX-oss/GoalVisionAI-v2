"""Manual read-only independent model activation audit CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .formatting import format_human, format_json
from .models import AuditStatus
from .repository import AuditConfigurationError, ReadOnlyAuditRepository
from .service import AuditInputError, ModelActivationAuditService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goalvision-model-activation-audit",
        description="Independent read-only activation/rollback evidence audit.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    audit = subcommands.add_parser("audit", help="Run all mandatory checks.")
    audit.add_argument("--database", required=True)
    audit.add_argument(
        "--environment",
        required=True,
        choices=("LAB", "STAGING", "PRODUCTION"),
    )
    audit.add_argument("--scope", required=True, choices=("OFFICIAL_GLOBAL",))
    audit.add_argument("--source-commit", required=True)
    audit.add_argument("--generated-at", required=True)
    audit.add_argument("--output", choices=("human", "json"), default="human")
    audit.add_argument("--evidence-export")
    audit.add_argument("--timeout-seconds", type=float, default=5.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = None
    try:
        repository = ReadOnlyAuditRepository(
            args.database, args.timeout_seconds
        )
        report = ModelActivationAuditService(repository).audit(
            source_commit=args.source_commit,
            generated_timestamp_utc=args.generated_at,
            environment=args.environment,
            scope=args.scope,
        )
        json_output = format_json(report)
        output = json_output if args.output == "json" else format_human(report)
        if args.evidence_export:
            _export(args.evidence_export, json_output)
        print(output)
        return (
            0
            if report.overall_status
            in {
                AuditStatus.AUDIT_PASSED,
                AuditStatus.AUDIT_PASSED_WITH_WARNINGS,
            }
            else 2
        )
    except (AuditConfigurationError, AuditInputError, OSError) as exc:
        print(f"AUDIT_INCOMPLETE: {exc}", file=sys.stderr)
        return 3
    except Exception:
        print(
            "AUDIT_INCOMPLETE: unexpected read-only audit failure; "
            "inspect the database copy and retry.",
            file=sys.stderr,
        )
        return 4
    finally:
        if repository is not None:
            repository.close()


def _export(value: str, content: str) -> None:
    path = Path(value).expanduser().resolve()
    if path.exists():
        raise AuditInputError("Evidence export target already exists.")
    if not path.parent.is_dir():
        raise AuditInputError("Evidence export parent directory does not exist.")
    path.write_text(content + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
