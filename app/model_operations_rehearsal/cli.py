"""Manual database preparation CLI for the isolated Lab rehearsal."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from app.database import Database

from .fixtures import seed_lab_fixture
from .safety import (
    RehearsalSafetyError,
    create_rehearsal_database_copies,
    resolve_database_source,
    sha256_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goalvision-model-operations-rehearsal",
        description="Create one isolated, fictional Lab model-operations database.",
    )
    parser.add_argument("prepare-lab-db", choices=("prepare-lab-db",))
    parser.add_argument("--source-database", type=Path, required=True)
    parser.add_argument("--destination-directory", type=Path, required=True)
    parser.add_argument("--timestamp")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
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


if __name__ == "__main__":
    sys.exit(main())
