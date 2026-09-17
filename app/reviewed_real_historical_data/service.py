"""Fail-closed source review, manifest, identity, quality, and leakage services."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence

from app.historical_training_dataset import HistoricalTrainingExample
from app.model_input_builder import LIVE_MODEL_INPUT_CONTRACT

from .fingerprint import file_sha256, sha256_fingerprint
from .models import (
    DataQualityReport,
    FeatureCoverageRow,
    FeatureSupportStatus,
    LeakageAuditReport,
    LeakageAuditStatus,
    SourceApprovalStatus,
    SourceFile,
    SourceManifest,
    SourceReview,
    TeamAlias,
)


REVIEW_POLICY_VERSION = "reviewed-real-source-policy-v1"
MANIFEST_POLICY_VERSION = "reviewed-real-source-manifest-v1"
LEAKAGE_POLICY_VERSION = "reviewed-real-live78-leakage-audit-v1"


def utc_text(value: str | datetime) -> str:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must contain an explicit UTC offset.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def prepare_source_review(review: SourceReview) -> SourceReview:
    if not review.source_id.strip() or not review.public_url_or_api_identifier.strip():
        raise ValueError("Source identity and public provenance are required.")
    if not review.terms_of_use_status.strip() or not review.reviewer_operator_note.strip():
        raise ValueError("Terms review and an operator note are required.")
    normalized = replace(
        review,
        source_id=review.source_id.strip(),
        review_timestamp_utc=utc_text(review.review_timestamp_utc),
        data_fields_available=tuple(sorted(set(review.data_fields_available))),
        review_fingerprint="",
    )
    fingerprint = sha256_fingerprint({"policy": REVIEW_POLICY_VERSION, "review": normalized})
    return replace(normalized, review_fingerprint=fingerprint)


def build_source_manifest(
    *, source_review: SourceReview, source_version: str, acquisition_timestamp_utc: str,
    effective_date_start: str, effective_date_end: str, competition_scope: Sequence[str],
    season_scope: Sequence[str], files: Sequence[str | Path], match_count: int,
    field_coverage: Iterable[tuple[str, int]], provenance_references: Sequence[str],
    parser_version: str, normalization_version: str,
) -> SourceManifest:
    review = prepare_source_review(source_review)
    if not review.approval_status.permits_import:
        raise PermissionError(f"Source status {review.approval_status.value} does not permit import.")
    source_files = []
    for raw_path in sorted((Path(item) for item in files), key=lambda item: item.name):
        if not raw_path.is_file():
            raise FileNotFoundError(raw_path)
        with raw_path.open("rb") as stream:
            rows = sum(1 for _ in stream)
        source_files.append(SourceFile(raw_path.name, file_sha256(raw_path), raw_path.stat().st_size, rows))
    material = SourceManifest(
        source_id=review.source_id,
        source_version=source_version.strip(),
        acquisition_timestamp_utc=utc_text(acquisition_timestamp_utc),
        effective_date_start=effective_date_start,
        effective_date_end=effective_date_end,
        competition_scope=tuple(sorted(set(competition_scope))),
        season_scope=tuple(sorted(set(season_scope))),
        source_files=tuple(source_files),
        match_count=match_count,
        field_coverage=tuple(sorted(field_coverage)),
        usage_approval_status=review.approval_status,
        provenance_references=tuple(sorted(set(provenance_references))),
        parser_version=parser_version,
        normalization_version=normalization_version,
        manifest_fingerprint="",
    )
    if not material.source_version or match_count < 0 or not material.source_files:
        raise ValueError("Manifest version, files, and a non-negative match count are required.")
    return replace(material, manifest_fingerprint=sha256_fingerprint({"policy": MANIFEST_POLICY_VERSION, "manifest": material}))


def validate_manifest_files(manifest: SourceManifest, root: str | Path) -> None:
    for source_file in manifest.source_files:
        path = Path(root) / source_file.file_name
        if not path.is_file() or path.stat().st_size != source_file.byte_count or file_sha256(path) != source_file.sha256:
            raise ValueError(f"Source file fingerprint mismatch: {source_file.file_name}")


class TeamIdentityResolver:
    """Exact source-ID/name aliases only; fuzzy matching is intentionally absent."""

    def __init__(self, aliases: Iterable[TeamAlias]) -> None:
        self._by_source_id: dict[tuple[str, str, str, str], TeamAlias] = {}
        self._by_name: dict[tuple[str, str, str, str], list[TeamAlias]] = defaultdict(list)
        for raw in aliases:
            alias = replace(raw, alias_fingerprint="")
            alias = replace(alias, alias_fingerprint=sha256_fingerprint(alias))
            id_key = (alias.source_id, alias.source_team_id, alias.competition, alias.season)
            existing = self._by_source_id.get(id_key)
            if existing is not None and existing.canonical_team_id != alias.canonical_team_id:
                raise ValueError("Conflicting source team identity alias.")
            self._by_source_id[id_key] = alias
            name_key = (alias.source_id, alias.normalized_source_name, alias.competition, alias.season)
            self._by_name[name_key].append(alias)

    def resolve(self, *, source_id: str, source_team_id: str, normalized_name: str, competition: str, season: str) -> TeamAlias:
        exact = self._by_source_id.get((source_id, source_team_id, competition, season))
        if exact is not None:
            return exact
        matches = self._by_name.get((source_id, normalized_name, competition, season), [])
        canonical = {item.canonical_team_id for item in matches}
        if len(canonical) != 1:
            raise ValueError("Team identity is unresolved or ambiguous; manual review is required.")
        return matches[0]


def audit_live78_leakage(
    dataset_build_id: str, examples: Sequence[HistoricalTrainingExample], *, audit_timestamp_utc: str,
) -> LeakageAuditReport:
    blockers: list[str] = []
    seen: dict[str, str] = {}
    for example in examples:
        if len(example.ordered_feature_vector) != LIVE_MODEL_INPUT_CONTRACT.feature_count:
            blockers.append(f"FEATURE_COUNT:{example.training_example_id}")
        if example.feature_schema_version != LIVE_MODEL_INPUT_CONTRACT.schema_version:
            blockers.append(f"FEATURE_SCHEMA:{example.training_example_id}")
        if tuple(name for name, _ in example.feature_provenance) != LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names:
            blockers.append(f"FEATURE_ORDER:{example.training_example_id}")
        if example.cutoff_timestamp != example.kickoff_utc:
            blockers.append(f"CUTOFF_MISMATCH:{example.training_example_id}")
        for source in example.sources:
            if source.source_historical_match_id == example.historical_match_id:
                blockers.append(f"TARGET_AS_SOURCE:{example.training_example_id}")
            if source.source_kickoff >= example.kickoff_utc:
                blockers.append(f"SOURCE_NOT_STRICTLY_PRIOR:{example.training_example_id}")
            prior = seen.get(source.source_historical_match_id)
            if prior is not None and prior != source.source_match_fingerprint:
                blockers.append(f"SOURCE_FINGERPRINT_CONFLICT:{source.source_historical_match_id}")
            seen[source.source_historical_match_id] = source.source_match_fingerprint
        if set(name for name, _ in example.labels) & set(name for name, _ in example.feature_provenance):
            blockers.append(f"LABEL_INPUT_COLLISION:{example.training_example_id}")
    unique = tuple(sorted(set(blockers)))
    timestamp = utc_text(audit_timestamp_utc)
    material = {
        "policy": LEAKAGE_POLICY_VERSION, "dataset_build_id": dataset_build_id,
        "checked_example_count": len(examples), "blocker_codes": unique, "audit_timestamp_utc": timestamp,
    }
    return LeakageAuditReport(
        dataset_build_id, LeakageAuditStatus.LEAKAGE_AUDIT_BLOCKED if unique else LeakageAuditStatus.LEAKAGE_AUDIT_PASSED,
        len(examples), unique, timestamp, sha256_fingerprint(material),
    )


def build_feature_coverage(examples: Sequence[HistoricalTrainingExample]) -> tuple[FeatureCoverageRow, ...]:
    rows: list[FeatureCoverageRow] = []
    required_names = set(LIVE_MODEL_INPUT_CONTRACT.required_feature_names)
    for index, name in enumerate(LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names):
        observed = [
            Decimal(int(value)) if isinstance(value, bool) else Decimal(str(value))
            for item in examples
            if (value := item.ordered_feature_vector[index]) is not None
        ]
        missing = len(examples) - len(observed)
        required = name in required_names
        by_competition = _group_coverage(examples, index, "competition")
        by_season = _group_coverage(examples, index, "season")
        faithful = not required or missing == 0
        status = (FeatureSupportStatus.FULLY_SUPPORTED if missing == 0 else
                  FeatureSupportStatus.REQUIRED_BLOCKING if required else
                  FeatureSupportStatus.OPTIONAL_MISSING_ACCEPTABLE if not observed else
                  FeatureSupportStatus.PARTIALLY_SUPPORTED)
        med = median(observed) if observed else None
        mad = median([abs(value - med) for value in observed]) if observed else None
        source_field, derivation_rule = _derivation_details(name)
        rows.append(FeatureCoverageRow(
            name, required, source_field, derivation_rule,
            _percentage(len(observed), len(examples)), len(observed), missing, 0,
            _decimal(min(observed)) if observed else None, _decimal(max(observed)) if observed else None,
            _decimal(med) if med is not None else None, _decimal(mad) if mad is not None else None,
            by_competition, by_season,
            "No lawful pre-kickoff source field" if missing else "NONE", faithful, status,
        ))
    return tuple(rows)


def _derivation_details(name: str) -> tuple[str | None, str]:
    if name == "neutral_venue_indicator":
        return "location (insufficient to prove neutrality)", "Explicitly missing because the source has no neutral-venue flag"
    if name.endswith("rest_days") or "fixture_congestion" in name:
        return "matchDateTimeUTC", "Strictly prior UTC kickoff chronology"
    if "lineup" in name or "injur" in name or "suspension" in name or "player" in name or "goalkeeper" in name:
        return None, "Explicitly missing: no lawful pre-kickoff field in source"
    if "xg" in name:
        return None, "Explicitly missing: no expected-goals field in source"
    if "head_to_head" in name:
        return "team1/team2, matchDateTimeUTC, matchResults", "Strictly prior pairwise history"
    if name in {"normalized_league_position_difference", "derby_indicator", "competition_stage_encoding"}:
        return None, "Explicitly missing: unsupported historical context"
    return "team1/team2, matchDateTimeUTC, leagueSeason, matchResults", "Canonical strictly prior form/season/venue aggregation"


def _group_coverage(examples: Sequence[HistoricalTrainingExample], index: int, attribute: str) -> tuple[tuple[str, str], ...]:
    totals: Counter[str] = Counter()
    present: Counter[str] = Counter()
    for item in examples:
        key = getattr(item, attribute)
        totals[key] += 1
        present[key] += item.ordered_feature_vector[index] is not None
    return tuple((key, _percentage(present[key], total)) for key, total in sorted(totals.items()))


def _percentage(value: int, total: int) -> str:
    return format((Decimal(value) * 100 / Decimal(total)).quantize(Decimal("0.01")), "f") if total else "0.00"


def _decimal(value: Decimal) -> str:
    return format(value, "f")


def build_data_quality_report(
    *, manifest_fingerprint: str, imported_count: int, accepted_matches: Sequence[object],
    exclusions: Iterable[str], ambiguous_team_mappings: int = 0,
) -> DataQualityReport:
    reasons = Counter(exclusions)
    competitions = Counter(getattr(item, "competition") for item in accepted_matches)
    seasons = Counter(getattr(item, "season") for item in accepted_matches)
    kickoffs = sorted(getattr(item, "kickoff_utc") for item in accepted_matches)
    labels = Counter()
    for item in accepted_matches:
        home, away = getattr(item, "full_time_home_score"), getattr(item, "full_time_away_score")
        labels["HOME_WIN" if home > away else "AWAY_WIN" if away > home else "DRAW"] += 1
    material = dict(
        source_manifest_fingerprint=manifest_fingerprint, imported_match_count=imported_count,
        accepted_match_count=len(accepted_matches), excluded_match_count=sum(reasons.values()),
        exclusion_reasons=tuple(sorted(reasons.items())), duplicate_count=reasons["DUPLICATE"],
        ambiguous_team_mappings=ambiguous_team_mappings, timestamp_issues=reasons["KICKOFF_MISSING"],
        impossible_score_statistics_issues=reasons["SCORE_INVALID"],
        competition_distribution=tuple(sorted(competitions.items())), season_distribution=tuple(sorted(seasons.items())),
        kickoff_date_start=kickoffs[0] if kickoffs else None, kickoff_date_end=kickoffs[-1] if kickoffs else None,
        home_away_balance=(("HOME_TEAMS", len(accepted_matches)), ("AWAY_TEAMS", len(accepted_matches))),
        label_distribution=tuple(sorted(labels.items())), provenance_complete=True,
    )
    return DataQualityReport(**material, report_fingerprint=sha256_fingerprint(material))
