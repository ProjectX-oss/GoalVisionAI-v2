"""Offline operator CLI for reviewed historical odds evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.reviewed_real_historical_data.models import SourceApprovalStatus

from .fingerprint import canonical_json, file_sha256
from .coverage_foundation import build_extended_coverage_evidence
from .football_data_foundation import build_football_data_foundation
from .models import OddsSourceReview
from .pilot import run_pilot
from .service import prepare_source_review
from .the_odds_api import parse_historical_archive
from .provider_config import load_provider_credential
from .provider_evidence import SPLIT_ID, build_credential_status_evidence
from .provider_export import assert_export_authorized, build_bulk_request_plan
from .provider_http import ProviderHttpError
from .provider_models import HistoricalOddsProvider
from .provider_probe import prepare_probe_request, run_coverage_probe


INSPECTION_COMMANDS = (
    "inspect-source", "inspect-manifest", "inspect-linkage", "inspect-coverage",
    "inspect-pre-kickoff", "inspect-bets", "inspect-bankroll", "inspect-risk",
    "inspect-betting-evidence", "inspect-backtest-integrity", "compare-candidates",
    "inspect-shadow", "inspect-audit", "inspect-activation-eligibility",
    "inspect-unmatched-events", "inspect-ambiguous-events",
    "inspect-partition-coverage", "inspect-quote-selections", "inspect-test-coverage",
    "inspect-confidence-intervals",
    "register-odds-manifest", "run-quote-selection", "run-test-only-backtest",
    "run-backtest-integrity-audit", "run-shadow-evaluation", "run-model-audit",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reviewed historical pre-kickoff odds tools (offline only).")
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review-source"); review.add_argument("review_json"); review.add_argument("--output", choices=("human", "json"), default="human")
    validate = sub.add_parser("validate-source-file"); validate.add_argument("path"); validate.add_argument("sha256")
    raw = sub.add_parser("validate-raw-odds-file"); raw.add_argument("path"); raw.add_argument("--output", choices=("human", "json"), default="human")
    extended = sub.add_parser("build-extended-coverage-foundation")
    extended.add_argument("prior_real_evidence"); extended.add_argument("prior_odds_evidence")
    extended.add_argument("protected_database"); extended.add_argument("isolated_database")
    extended.add_argument("--review", action="append", required=True)
    extended.add_argument("--branch", required=True); extended.add_argument("--starting-commit", required=True)
    extended.add_argument("--timestamp", required=True); extended.add_argument("--export")
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
    diagnose = sub.add_parser("provider-diagnose", help="explicit bounded provider authentication check")
    diagnose.add_argument("--provider", choices=("thestatsapi",), required=True); diagnose.add_argument("--output", choices=("human", "json"), default="human")
    probe = sub.add_parser("coverage-probe", help="explicit bounded historical coverage sample")
    probe.add_argument("--provider", choices=("thestatsapi",), required=True); probe.add_argument("--competition", required=True)
    probe.add_argument("--date-from", required=True); probe.add_argument("--date-to", required=True)
    probe.add_argument("--sample-limit", type=int, default=10); probe.add_argument("--max-requests", type=int, default=25)
    probe.add_argument("--output", choices=("human", "json"), default="human")
    plan = sub.add_parser("export-plan"); plan.add_argument("--provider", choices=("thestatsapi",), required=True)
    plan.add_argument("--split-id", default=SPLIT_ID); plan.add_argument("--competition", default="bundesliga"); plan.add_argument("--output", choices=("human", "json"), default="json")
    authorized = sub.add_parser("authorized-export"); authorized.add_argument("--provider", choices=("thestatsapi",), required=True)
    authorized.add_argument("--confirmation", required=True); authorized.add_argument("--destination", required=True); authorized.add_argument("--output", choices=("human", "json"), default="human")
    evidence = sub.add_parser("provider-evidence"); evidence.add_argument("--export"); evidence.add_argument("--output", choices=("human", "json"), default="json")
    football_data = sub.add_parser(
        "import-football-data-foundation",
        help="offline fail-closed import of bounded Football-Data raw CSV evidence",
    )
    football_data.add_argument("--odds-file", action="append", required=True)
    football_data.add_argument("--fixture-file", action="append", required=True)
    football_data.add_argument("--review", required=True)
    football_data.add_argument("--split-evidence", required=True)
    football_data.add_argument("--database", required=True)
    football_data.add_argument("--timestamp", required=True)
    football_data.add_argument("--export")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "review-source":
        review = prepare_source_review(_load_review(args.review_json)); return _render({"status": "REVIEWED", "review": review}, args.output)
    if args.command == "validate-source-file":
        actual = file_sha256(args.path); ok = actual.lower() == args.sha256.lower()
        _render({"status": "VALID" if ok else "HASH_MISMATCH", "file": Path(args.path).name, "sha256": actual}, "human"); return 0 if ok else 2
    if args.command == "validate-raw-odds-file":
        snapshots = parse_historical_archive(args.path)
        return _render({
            "status": "VALID", "file": Path(args.path).name,
            "sha256": file_sha256(args.path), "snapshot_count": len(snapshots),
            "event_count": sum(len(item.events) for item in snapshots),
            "quote_count": sum(len(item.quotes) for item in snapshots),
            "unsupported_market_rows": sum(item.unsupported_market_rows for item in snapshots),
        }, args.output)
    if args.command == "build-extended-coverage-foundation":
        evidence = build_extended_coverage_evidence(
            prior_real_evidence_path=args.prior_real_evidence,
            prior_odds_evidence_path=args.prior_odds_evidence,
            source_review_paths=tuple(args.review), protected_database_path=args.protected_database,
            isolated_database_path=args.isolated_database, branch=args.branch,
            starting_commit=args.starting_commit, execution_timestamp_utc=args.timestamp,
        )
        if args.export:
            Path(args.export).write_text(canonical_json(evidence) + "\n", encoding="utf-8")
        return _render(evidence, "json")
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
    if args.command == "provider-evidence":
        evidence = build_credential_status_evidence()
        if args.export: Path(args.export).write_text(canonical_json(evidence) + "\n", encoding="utf-8")
        return _render(evidence, args.output)
    if args.command == "import-football-data-foundation":
        evidence = build_football_data_foundation(
            football_data_files=tuple(args.odds_file),
            openligadb_files=tuple(args.fixture_file),
            source_review_path=args.review,
            split_evidence_path=args.split_evidence,
            isolated_database_path=args.database,
            execution_timestamp_utc=args.timestamp,
        )
        if args.export:
            Path(args.export).write_text(canonical_json(evidence) + "\n", encoding="utf-8")
        return _render(evidence, "json")
    if args.command == "export-plan":
        return _render(build_bulk_request_plan(provider=HistoricalOddsProvider(args.provider), split_id=args.split_id, competition_query=args.competition), args.output)
    if args.command in {"provider-diagnose", "coverage-probe"}:
        provider = HistoricalOddsProvider(args.provider); credential = load_provider_credential(provider)
        if not credential.configured:
            if args.command == "provider-diagnose": return _render({"provider": provider.value, "status": "PROVIDER_CREDENTIAL_NOT_CONFIGURED", "environment_variable": credential.environment_variable}, args.output)
            request = prepare_probe_request(provider, args.competition, args.date_from, args.date_to, args.sample_limit, args.max_requests)
            return _render(run_coverage_probe(request, None), args.output)
        from .thestatsapi_provider import TheStatsApiProvider
        adapter = TheStatsApiProvider(credential)
        if args.command == "provider-diagnose":
            try:
                valid, receipt = adapter.diagnose_credentials()
                return _render({"provider": provider.value, "status": "PROVIDER_CREDENTIAL_VALID" if valid else "PROVIDER_AUTHENTICATION_FAILED", "receipt": receipt}, args.output)
            except ProviderHttpError as exc:
                status = "PROVIDER_AUTHENTICATION_FAILED" if exc.status_code in (401, 403) else "PROVIDER_QUOTA_INSUFFICIENT" if exc.status_code == 429 else "PROVIDER_RESPONSE_INCOMPATIBLE"
                return _render({"provider": provider.value, "status": status, "http_status": exc.status_code}, args.output)
            except (KeyError, TypeError, ValueError):
                return _render({"provider": provider.value, "status": "PROVIDER_RESPONSE_INCOMPATIBLE"}, args.output)
        request = prepare_probe_request(provider, args.competition, args.date_from, args.date_to, args.sample_limit, args.max_requests)
        return _render(run_coverage_probe(request, adapter), args.output)
    if args.command == "authorized-export":
        credential = load_provider_credential(HistoricalOddsProvider(args.provider))
        plan = build_bulk_request_plan(provider=HistoricalOddsProvider(args.provider), split_id=SPLIT_ID, competition_query="bundesliga")
        request = prepare_probe_request(HistoricalOddsProvider(args.provider), "bundesliga", "2023-05-13T13:30:00Z", "2025-05-17T13:30:00Z")
        report = run_coverage_probe(request, None)
        try:
            assert_export_authorized(
                confirmation=args.confirmation, credential_configured=credential.configured,
                source_approval_status=SourceApprovalStatus.REVIEW_REQUIRED, coverage_report=report,
                available_quota=None, plan=plan,
            )
        except PermissionError as exc:
            return _render({"status": "AUTHORIZED_EXPORT_BLOCKED", "reason_codes": tuple(str(exc).split(",")), "destination_written": False}, args.output)
        return _render({"status": "AUTHORIZED_EXPORT_BLOCKED", "reason_codes": ("PERSISTED_APPROVAL_AND_PROBE_REQUIRED",), "destination_written": False}, args.output)
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
        "inspect-unmatched-events": "event_links", "inspect-ambiguous-events": "event_links",
        "inspect-partition-coverage": "coverage_report", "inspect-quote-selections": "quote_selection_policies",
        "inspect-test-coverage": "coverage_report", "inspect-confidence-intervals": "uncertainty_metrics",
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
