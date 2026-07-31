"""Offline operator CLI for reviewed historical odds evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.reviewed_real_historical_data.models import SourceApprovalStatus

from .fingerprint import canonical_json, file_sha256
from .models import OddsSourceReview
from .pilot import run_pilot
from .service import prepare_source_review


INSPECTION_COMMANDS = (
    "inspect-source", "inspect-manifest", "inspect-linkage", "inspect-coverage",
    "inspect-pre-kickoff", "inspect-bets", "inspect-bankroll", "inspect-risk",
    "inspect-betting-evidence", "inspect-backtest-integrity", "compare-candidates",
    "inspect-shadow", "inspect-audit", "inspect-activation-eligibility",
    "register-odds-manifest", "run-quote-selection", "run-test-only-backtest",
    "run-backtest-integrity-audit", "run-shadow-evaluation", "run-model-audit",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reviewed historical pre-kickoff odds tools (offline only).")
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review-source"); review.add_argument("review_json"); review.add_argument("--output", choices=("human", "json"), default="human")
    validate = sub.add_parser("validate-source-file"); validate.add_argument("path"); validate.add_argument("sha256")
    for command in ("run-pilot", "import-historical-odds"):
        pilot = sub.add_parser(command)
        for name in ("base_database", "isolated_database", "odds_file", "review_json", "prior_evidence", "protected_database"):
            pilot.add_argument(name)
        pilot.add_argument("--source-version", required=True); pilot.add_argument("--timestamp", required=True)
        pilot.add_argument("--source-commit", required=True); pilot.add_argument("--branch", required=True); pilot.add_argument("--export")
        pilot.add_argument("--additional-review", action="append", default=[])
    for name in INSPECTION_COMMANDS:
        inspect = sub.add_parser(name); inspect.add_argument("evidence_json"); inspect.add_argument("--output", choices=("human", "json"), default="human")
    export = sub.add_parser("export-canonical-evidence"); export.add_argument("evidence_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "review-source":
        review = prepare_source_review(_load_review(args.review_json)); return _render({"status": "REVIEWED", "review": review}, args.output)
    if args.command == "validate-source-file":
        actual = file_sha256(args.path); ok = actual.lower() == args.sha256.lower()
        _render({"status": "VALID" if ok else "HASH_MISMATCH", "file": Path(args.path).name, "sha256": actual}, "human"); return 0 if ok else 2
    if args.command in {"run-pilot", "import-historical-odds"}:
        evidence = run_pilot(
            base_database_path=args.base_database, isolated_database_path=args.isolated_database,
            odds_file=args.odds_file, source_review=_load_review(args.review_json),
            source_version=args.source_version, execution_timestamp_utc=args.timestamp,
            prior_evidence_path=args.prior_evidence, protected_database_path=args.protected_database,
            source_commit=args.source_commit, branch=args.branch,
            candidate_reviews=tuple(_load_review(path) for path in args.additional_review),
        )
        if args.export: Path(args.export).write_text(canonical_json(evidence) + "\n", encoding="utf-8")
        return _render(evidence, "json")
    evidence = json.loads(Path(args.evidence_json).read_text(encoding="utf-8"))
    if args.command == "export-canonical-evidence": return _render(evidence, "json")
    sections = {
        "inspect-source": "odds_source_reviews", "inspect-manifest": "source_manifest",
        "inspect-linkage": "event_links", "inspect-coverage": "odds_coverage_report",
        "inspect-pre-kickoff": "odds_coverage_report", "inspect-bets": "betting_evidence",
        "inspect-bankroll": "betting_evidence", "inspect-risk": "betting_evidence",
        "inspect-betting-evidence": "betting_evidence", "inspect-backtest-integrity": "backtest_integrity",
        "compare-candidates": "comparison_result", "inspect-shadow": "shadow_result",
        "inspect-audit": "audit_result", "inspect-activation-eligibility": "staging_activation_result",
        "register-odds-manifest": "source_manifest", "run-quote-selection": "quote_selection_policy",
        "run-test-only-backtest": "betting_evidence", "run-backtest-integrity-audit": "backtest_integrity",
        "run-shadow-evaluation": "shadow_result", "run-model-audit": "audit_result",
    }
    return _render({"schema_version": evidence["schema_version"], "result": evidence[sections[args.command]]}, args.output)


def _load_review(path: str) -> OddsSourceReview:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    raw["approval_status"] = SourceApprovalStatus(raw["approval_status"])
    raw.pop("review_fingerprint", None)
    return OddsSourceReview(**raw)


def _render(value, output: str) -> int:
    document = json.loads(canonical_json(value))
    if output == "json": print(json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    else:
        status = document.get("status", "INSPECTION_COMPLETE") if isinstance(document, dict) else "INSPECTION_COMPLETE"
        print(f"status: {status}"); print(json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True))
    return 0
