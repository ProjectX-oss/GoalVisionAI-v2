"""Network-inert operator CLI for reviewed real historical data."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .fingerprint import canonical_json, file_sha256, sha256_fingerprint
from .models import SourceApprovalStatus, SourceReview
from .openligadb import parse_openligadb_files
from .pilot import run_openligadb_pilot
from .service import prepare_source_review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reviewed real historical data operator tools (offline only).")
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review-source", help="Validate and fingerprint a typed source-review JSON file.")
    review.add_argument("--review", required=True)
    review.add_argument("--output", choices=("human", "json"), default="human")
    validate = sub.add_parser("validate-source-files", help="Parse supplied OpenLigaDB JSON snapshots without persistence.")
    validate.add_argument("--source-file", action="append", required=True)
    validate.add_argument("--dataset-version", required=True)
    validate.add_argument("--output", choices=("human", "json"), default="human")
    pilot = sub.add_parser("run-pilot", help="Run the isolated import-to-TEST reviewed-real pilot.")
    pilot.add_argument("--database", required=True)
    pilot.add_argument("--source-file", action="append", required=True)
    pilot.add_argument("--review", required=True)
    pilot.add_argument("--source-version", required=True)
    pilot.add_argument("--execution-timestamp", required=True)
    pilot.add_argument("--source-commit", required=True)
    pilot.add_argument("--branch", required=True)
    pilot.add_argument("--protected-database")
    pilot.add_argument("--evidence")
    pilot.add_argument("--output", choices=("human", "json"), default="human")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "review-source":
            result = asdict(prepare_source_review(_load_review(args.review)))
        elif args.command == "validate-source-files":
            parsed = parse_openligadb_files(tuple(args.source_file), dataset_id="operator-validation", dataset_version=args.dataset_version)
            result = {"status": "SOURCE_FILES_VALID", "supplied_record_count": parsed.supplied_record_count,
                      "accepted_match_count": len(parsed.dataset.matches), "excluded_match_count": len(parsed.exclusions),
                      "exclusions": tuple((label, reason.value) for label, reason in parsed.exclusions)}
        else:
            result = run_openligadb_pilot(
                database_path=args.database, source_files=tuple(args.source_file), source_review=_load_review(args.review),
                source_version=args.source_version, execution_timestamp_utc=args.execution_timestamp,
                protected_database_path=args.protected_database,
                source_commit=args.source_commit, branch=args.branch,
            )
            result["isolated_database_hash"] = file_sha256(args.database)
            result.pop("evidence_fingerprint", None)
            result["evidence_fingerprint"] = sha256_fingerprint(result)
            if args.evidence:
                Path(args.evidence).write_text(canonical_json(result) + "\n", encoding="utf-8")
        _render(result, args.output)
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _load_review(path: str) -> SourceReview:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["approval_status"] = SourceApprovalStatus(payload["approval_status"])
    payload["data_fields_available"] = tuple(payload["data_fields_available"])
    return SourceReview(**payload)


def _render(value: dict[str, object], output: str) -> None:
    if output == "json":
        print(canonical_json(value))
        return
    for key in ("status", "evidence_tier", "publication_eligibility", "raw_source_match_count",
                "normalized_accepted_match_count", "excluded_match_count", "evidence_fingerprint"):
        if key in value:
            print(f"{key}: {value[key]}")
    if "source_review" in value:
        source = value["source_review"]
        print(f"source: {source['source_name']} ({source['approval_status']})")
    elif "source_name" in value:
        print(f"source: {value['source_name']}")
        print(f"approval_status: {getattr(value['approval_status'], 'value', value['approval_status'])}")
        print(f"review_fingerprint: {value['review_fingerprint']}")
    if "audit_result" in value:
        print(f"audit_result: {value['audit_result']}")
        print("Telegram sends: 0; Official publications: 0; production activation: 0")


if __name__ == "__main__":
    raise SystemExit(main())
