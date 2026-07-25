"""Manual-only controlled staging rehearsal CLI."""

from __future__ import annotations

import argparse
import json
import sys

from .execution import run_staging_rehearsal
from .models import ArtifactMode, StagingRehearsalCommand
from .reporting import canonical_json, format_human


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goalvision-staging-model-operations-rehearsal",
        description="Manual isolated STAGING activation/rollback rehearsal.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run one explicitly authorized rehearsal.")
    run.add_argument("--source-database", required=True)
    run.add_argument("--destination-directory", required=True)
    run.add_argument("--environment", required=True, choices=("STAGING", "PRODUCTION"))
    run.add_argument("--scope", required=True, choices=("OFFICIAL_GLOBAL",))
    run.add_argument("--timestamp", required=True)
    run.add_argument("--source-commit", required=True)
    run.add_argument(
        "--audit-output-mode",
        choices=("human", "json", "both"),
        default="both",
    )
    run.add_argument("--evidence-report-destination")
    run.add_argument(
        "--artifact-mode",
        choices=tuple(item.value for item in ArtifactMode),
        default=ArtifactMode.PREFER_REAL.value,
    )
    run.add_argument("--real-artifacts-required", action="store_true")
    run.add_argument("--allow-fixture-fallback", action="store_true")
    run.add_argument("--output", choices=("human", "json"), default="human")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        mode = (
            ArtifactMode.REAL_ONLY
            if args.real_artifacts_required
            else ArtifactMode(args.artifact_mode)
        )
        outcome = run_staging_rehearsal(
            StagingRehearsalCommand(
                source_database=args.source_database,
                destination_directory=args.destination_directory,
                environment=args.environment,
                scope=args.scope,
                timestamp=args.timestamp,
                source_commit=args.source_commit,
                audit_output_mode=args.audit_output_mode,
                evidence_report_destination=args.evidence_report_destination,
                artifact_mode=mode,
                allow_fixture_fallback=args.allow_fixture_fallback,
            )
        )
        print(canonical_json(outcome) if args.output == "json" else format_human(outcome))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "STAGING_REHEARSAL_REJECTED",
                    "reason": type(exc).__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
