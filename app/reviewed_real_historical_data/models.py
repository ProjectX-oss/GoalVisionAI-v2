"""Typed immutable records for reviewed real historical football data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SourceApprovalStatus(str, Enum):
    APPROVED_FOR_CONTROLLED_RESEARCH = "APPROVED_FOR_CONTROLLED_RESEARCH"
    APPROVED_FOR_INTERNAL_DERIVED_DATA = "APPROVED_FOR_INTERNAL_DERIVED_DATA"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"
    ACCESS_UNAVAILABLE = "ACCESS_UNAVAILABLE"
    TERMS_UNCLEAR = "TERMS_UNCLEAR"

    @property
    def permits_import(self) -> bool:
        return self in {
            self.APPROVED_FOR_CONTROLLED_RESEARCH,
            self.APPROVED_FOR_INTERNAL_DERIVED_DATA,
        }


class EvidenceTier(str, Enum):
    CONTROLLED_SYNTHETIC = "CONTROLLED_SYNTHETIC"
    REVIEWED_REAL_HISTORICAL = "REVIEWED_REAL_HISTORICAL"
    PRODUCTION_AUTHORIZED = "PRODUCTION_AUTHORIZED"

    @property
    def publication_eligible(self) -> bool:
        return self is self.PRODUCTION_AUTHORIZED


class FeatureSupportStatus(str, Enum):
    FULLY_SUPPORTED = "FULLY_SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    OPTIONAL_MISSING_ACCEPTABLE = "OPTIONAL_MISSING_ACCEPTABLE"
    DERIVATION_REVIEW_REQUIRED = "DERIVATION_REVIEW_REQUIRED"
    REQUIRED_BLOCKING = "REQUIRED_BLOCKING"
    UNSUPPORTED = "UNSUPPORTED"


class LeakageAuditStatus(str, Enum):
    LEAKAGE_AUDIT_PASSED = "LEAKAGE_AUDIT_PASSED"
    LEAKAGE_AUDIT_BLOCKED = "LEAKAGE_AUDIT_BLOCKED"


class MatchExclusionReason(str, Enum):
    NOT_FINISHED = "NOT_FINISHED"
    SCORE_MISSING = "SCORE_MISSING"
    SCORE_INVALID = "SCORE_INVALID"
    KICKOFF_MISSING = "KICKOFF_MISSING"
    TEAM_IDENTITY_INVALID = "TEAM_IDENTITY_INVALID"
    DUPLICATE = "DUPLICATE"
    MALFORMED = "MALFORMED"


@dataclass(frozen=True, slots=True)
class SourceReview:
    source_id: str
    source_name: str
    source_category: str
    public_url_or_api_identifier: str
    data_owner_provider: str
    access_method: str
    authentication_requirement: str
    terms_of_use_status: str
    robots_public_access_considerations: str
    redistribution_restrictions: str
    commercial_use_restrictions: str
    rate_limits: str
    data_fields_available: tuple[str, ...]
    historical_coverage: str
    competition_coverage: str
    update_cadence: str
    reliability_assessment: str
    raw_data_may_be_stored: bool
    normalized_derived_data_may_be_stored: bool
    provenance_may_be_committed: bool
    evidence_may_be_published: bool
    review_timestamp_utc: str
    reviewer_operator_note: str
    approval_status: SourceApprovalStatus
    review_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class SourceFile:
    file_name: str
    sha256: str
    byte_count: int
    row_count: int


@dataclass(frozen=True, slots=True)
class SourceManifest:
    source_id: str
    source_version: str
    acquisition_timestamp_utc: str
    effective_date_start: str
    effective_date_end: str
    competition_scope: tuple[str, ...]
    season_scope: tuple[str, ...]
    source_files: tuple[SourceFile, ...]
    match_count: int
    field_coverage: tuple[tuple[str, int], ...]
    usage_approval_status: SourceApprovalStatus
    provenance_references: tuple[str, ...]
    parser_version: str
    normalization_version: str
    manifest_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class TeamAlias:
    source_id: str
    source_team_id: str
    normalized_source_name: str
    canonical_team_id: str
    canonical_name: str
    competition: str
    season: str
    provenance: str
    alias_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class FeatureCoverageRow:
    feature_name: str
    required: bool
    direct_source_field: str | None
    derivation_rule: str
    coverage_percentage: str
    non_missing_count: int
    missing_count: int
    imputed_count: int
    observed_minimum: str | None
    observed_maximum: str | None
    median: str | None
    robust_dispersion: str | None
    competition_coverage: tuple[tuple[str, str], ...]
    season_coverage: tuple[tuple[str, str], ...]
    missingness_reason: str
    live_semantics_faithfully_reproduced: bool
    review_status: FeatureSupportStatus


@dataclass(frozen=True, slots=True)
class LeakageAuditReport:
    dataset_build_id: str
    status: LeakageAuditStatus
    checked_example_count: int
    blocker_codes: tuple[str, ...]
    audit_timestamp_utc: str
    report_fingerprint: str


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    source_manifest_fingerprint: str
    imported_match_count: int
    accepted_match_count: int
    excluded_match_count: int
    exclusion_reasons: tuple[tuple[str, int], ...]
    duplicate_count: int
    ambiguous_team_mappings: int
    timestamp_issues: int
    impossible_score_statistics_issues: int
    competition_distribution: tuple[tuple[str, int], ...]
    season_distribution: tuple[tuple[str, int], ...]
    kickoff_date_start: str | None
    kickoff_date_end: str | None
    home_away_balance: tuple[tuple[str, int], ...]
    label_distribution: tuple[tuple[str, int], ...]
    provenance_complete: bool
    report_fingerprint: str
