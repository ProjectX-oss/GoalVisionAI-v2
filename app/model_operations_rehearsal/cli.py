"""Manual database preparation CLI for the isolated Lab rehearsal."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from app.database import Database

from .execution import execute_activation_rollback_rehearsal
from .fixtures import seed_lab_fixture
from .safety import (
    create_rehearsal_database_copies,
    resolve_database_source,
    sha256_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goalvision-model-operations-rehearsal",
        description="Manual isolated fictional Lab model-operations rehearsals.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser(
        "prepare-lab-db",
        help="Create one prepared fictional evidence database.",
    )
    _database_arguments(prepare)
    execute = commands.add_parser(
        "execute-activation-rollback-rehearsal",
        help="Run activation and rollback through the real manual CLI.",
    )
    _database_arguments(execute)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "execute-activation-rollback-rehearsal":
            report = execute_activation_rollback_rehearsal(
                source_database=args.source_database,
                destination_directory=args.destination_directory,
                timestamp=(
                    args.timestamp
                    or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                ),
            )
            print("status=LAB_ACTIVATION_ROLLBACK_REHEARSAL_COMPLETED")
            print(f"source_fingerprint={report.source_fingerprint}")
            print(
                "foundation_fingerprint="
                f"{report.foundation_fingerprint}"
            )
            print(
                "disposable_before_fingerprint="
                f"{report.disposable_before_fingerprint}"
            )
            print(
                "disposable_after_fingerprint="
                f"{report.disposable_after_fingerprint}"
            )
            print(
                "activation_execution_fingerprint="
                f"{report.activation_execution_fingerprint}"
            )
            print(
                "rollback_execution_fingerprint="
                f"{report.rollback_execution_fingerprint}"
            )
            print(
                "disposable_database="
                f"{report.disposable_database_name}"
            )
            return 0
        source = resolve_database_source(explicit=args.source_database)
        timestamp = args.timestamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        copies = create_rehearsal_database_copies(
            source,
            args.destination_directory,
            timestamp=timestamp,
        )
        try:
            database = Database(str(copies.rehearsal))
            try:
                manifest = seed_lab_fixture(database)
            finally:
                database.close()
        except Exception:
            copies.rehearsal.unlink(missing_ok=True)
            copies.rehearsal.with_suffix(".manifest.json").unlink(missing_ok=True)
            raise
        manifest_path = copies.rehearsal.with_suffix(".manifest.json")
        manifest_path.write_text(manifest.as_json() + "\n", encoding="utf-8")
        print(f"status=LAB_REHEARSAL_PREPARED")
        print(f"source_fingerprint={copies.source_fingerprint}")
        print(f"backup_fingerprint={copies.backup_fingerprint}")
        print(f"rehearsal_fingerprint={sha256_file(copies.rehearsal)}")
        print(f"settled_shadow_count={manifest.settled_shadow_count}")
        print(f"observation_days={manifest.observation_days}")
        print(f"backup={copies.backup}")
        print(f"rehearsal={copies.rehearsal}")
        print(f"manifest={manifest_path}")
        return 0
    except Exception as exc:
        print(f"status=LAB_REHEARSAL_REJECTED")
        print(f"reason={type(exc).__name__}")
        return 2


def _database_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-database", type=Path, required=True)
    parser.add_argument("--destination-directory", type=Path, required=True)
    parser.add_argument("--timestamp")


if __name__ == "__main__":
    sys.exit(main())
