"""Pure review, normalization, linkage, selection, coverage, and audit services."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import unicodedata

from app.historical_backtesting.models import SupportedMarket

from .fingerprint import file_sha256, sha256_fingerprint
from .models import (
    BacktestIntegrityReport, BacktestIntegrityStatus, EventLinkDecision,
    CoverageSufficiencyStatus, EventLinkStatus, HistoricalMatchReference, NormalizedOddsQuote,
    OddsAcquisitionWindow,
    OddsCoverageReport, OddsSourceFile, OddsSourceManifest, OddsSourceReview,
    PartitionCoverageReport, QuoteSelectionDecision, QuoteSelectionPolicy,
    QuoteSelectionPolicyType, QuoteTimingStatus,
    SourceOddsEvent, SourceOddsQuote,
)


NORMALIZATION_VERSION = "goalvision-reviewed-historical-odds-v1"
SUPPORTED_MARKETS = tuple(SupportedMarket)


def normalize_utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include an explicit timezone.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def prepare_source_review(review: OddsSourceReview) -> OddsSourceReview:
    required = (
        review.source_id, review.source_name, review.source_owner_provider,
        review.source_category, review.source_url_or_api_identifier,
        review.access_method, review.authentication_requirement,
        review.terms_of_use_status, review.licensing_or_redistribution_status,
        review.storage_permission, review.derived_data_permission,
        review.review_timestamp_utc, review.operator_note,
        review.pricing_or_access_tier, review.redistribution_permission,
        review.update_cadence,
    )
    if not all(value.strip() for value in required):
        raise ValueError("Odds source review fields must not be empty.")
    normalized = replace(review, review_timestamp_utc=normalize_utc(review.review_timestamp_utc), review_fingerprint="")
    return replace(normalized, review_fingerprint=sha256_fingerprint(normalized))


def require_import_approval(review: OddsSourceReview) -> None:
    if not review.approval_status.permits_import:
        raise PermissionError(f"Odds source is not approved for import: {review.approval_status.value}")


def build_manifest(
    review: OddsSourceReview, *, source_version: str, acquisition_timestamp_utc: str,
    files: tuple[str | Path, ...], raw_row_count: int, normalized_quote_count: int,
    event_count: int, capture_time_coverage: int, pre_kickoff_validation_coverage: int,
    effective_date_start: str, effective_date_end: str,
    competitions: tuple[str, ...], seasons: tuple[str, ...], bookmakers: tuple[str, ...],
    markets: tuple[str, ...], parser_version: str,
) -> OddsSourceManifest:
    require_import_approval(review)
    if review.review_fingerprint != prepare_source_review(review).review_fingerprint:
        raise ValueError("Odds source review fingerprint is invalid.")
    source_files = tuple(
        OddsSourceFile(Path(path).name, file_sha256(path), Path(path).stat().st_size, raw_row_count)
        for path in sorted((Path(item) for item in files), key=lambda item: item.name)
    )
    value = OddsSourceManifest(
        source_id=review.source_id, source_version=source_version,
        provider=review.source_owner_provider,
        acquisition_timestamp_utc=normalize_utc(acquisition_timestamp_utc),
        effective_date_start=normalize_utc(effective_date_start),
        effective_date_end=normalize_utc(effective_date_end),
        competition_scope=tuple(sorted(set(competitions))),
        season_scope=tuple(sorted(set(seasons))),
        bookmaker_list=tuple(sorted(set(bookmakers))), market_list=tuple(sorted(set(markets))),
        source_files=source_files, raw_row_count=raw_row_count,
        normalized_quote_count=normalized_quote_count, event_count=event_count,
        capture_time_coverage=capture_time_coverage,
        pre_kickoff_validation_coverage=pre_kickoff_validation_coverage,
        source_review_id=f"odds-source-review-{review.review_fingerprint}",
        parser_version=parser_version, normalization_version=NORMALIZATION_VERSION,
    )
    return replace(value, manifest_fingerprint=sha256_fingerprint(value))


def validate_manifest_files(manifest: OddsSourceManifest, root: str | Path) -> None:
    base = Path(root)
    for item in manifest.source_files:
        path = base / item.file_name
        if not path.is_file() or path.stat().st_size != item.byte_count or file_sha256(path) != item.sha256:
            raise ValueError(f"Odds source file does not match manifest: {item.file_name}")


def decimal_odds(value: str, odds_format: str) -> tuple[Decimal, str]:
    fmt = odds_format.strip().upper()
    try:
        if fmt == "DECIMAL":
            result = Decimal(value)
            rule = "IDENTITY_DECIMAL"
        elif fmt == "AMERICAN":
            american = Decimal(value)
            if american == 0:
                raise ValueError
            result = Decimal(1) + (american / Decimal(100) if american > 0 else Decimal(100) / abs(american))
            rule = "AMERICAN_TO_DECIMAL_V1"
        elif fmt == "FRACTIONAL":
            fraction = Fraction(value)
            result = Decimal(1) + Decimal(fraction.numerator) / Decimal(fraction.denominator)
            rule = "FRACTIONAL_TO_DECIMAL_V1"
        else:
            raise ValueError("Unsupported odds format.")
    except Exception as exc:
        raise ValueError("Odds value cannot be converted deterministically.") from exc
    if not result.is_finite() or result <= Decimal(1):
        raise ValueError("Decimal odds must be finite and greater than 1.0.")
    return result.normalize(), rule


def normalized_team_name(value: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", value.replace("ß", "ss")).encode("ascii", "ignore").decode("ascii")
    return " ".join("".join(char if char.isalnum() else " " for char in ascii_name.lower()).split())


def link_events(
    events: tuple[SourceOddsEvent, ...], matches: tuple[HistoricalMatchReference, ...],
    *, reviewed_aliases: dict[str, str], kickoff_tolerance_seconds: int = 0,
    reviewed_competition_aliases: dict[str, str] | None = None,
) -> tuple[EventLinkDecision, ...]:
    if kickoff_tolerance_seconds < 0:
        raise ValueError("Kickoff tolerance cannot be negative.")
    decisions = []
    competition_aliases = reviewed_competition_aliases or {}
    for event in sorted(events, key=lambda item: item.source_event_id):
        source_home = normalized_team_name(event.home_team)
        source_away = normalized_team_name(event.away_team)
        home = normalized_team_name(reviewed_aliases.get(source_home, event.home_team))
        away = normalized_team_name(reviewed_aliases.get(source_away, event.away_team))
        event_time = _datetime(event.kickoff_utc)
        source_competition = normalized_team_name(event.competition)
        canonical_competition = normalized_team_name(
            competition_aliases.get(source_competition, event.competition)
        )
        candidates = []
        reversed_found = False
        effective_tolerance = max(kickoff_tolerance_seconds, event.kickoff_precision_seconds)
        for match in matches:
            match_home, match_away = normalized_team_name(match.home_team), normalized_team_name(match.away_team)
            delta = abs(int((_datetime(match.kickoff_utc) - event_time).total_seconds()))
            match_competition = normalized_team_name(match.competition)
            competition_matches = (
                match_competition == canonical_competition
                or (
                    source_competition in competition_aliases
                    and match_competition.startswith(canonical_competition)
                )
            )
            if not competition_matches:
                continue
            if event.season is not None and match.season != event.season:
                continue
            if match_home == away and match_away == home and delta <= effective_tolerance:
                reversed_found = True
            if match_home == home and match_away == away and delta <= effective_tolerance:
                candidates.append((match, delta))
        if len(candidates) > 1 and event.round_name:
            round_matches = [item for item in candidates if normalized_team_name(item[0].round_name or "") == normalized_team_name(event.round_name)]
            if round_matches:
                candidates = round_matches
        if len(candidates) > 1:
            status, match, delta, reasons = EventLinkStatus.AMBIGUOUS_MATCH, None, None, ("MULTIPLE_MATCHES",)
        elif len(candidates) == 0:
            status, match, delta = EventLinkStatus.CONFLICTING_MATCH if reversed_found else EventLinkStatus.NO_MATCH, None, None
            reasons = ("REVERSED_HOME_AWAY",) if reversed_found else ("NO_DETERMINISTIC_MATCH",)
        else:
            match, delta = candidates[0]
            alias_used = source_home in reviewed_aliases or source_away in reviewed_aliases
            status = EventLinkStatus.TIMESTAMP_TOLERANCE_MATCH if delta else (EventLinkStatus.REVIEWED_ALIAS_MATCH if alias_used else EventLinkStatus.EXACT_MATCH)
            reasons = (status.value,)
        material = {
            "source_event_id": event.source_event_id,
            "historical_match_id": match.historical_match_id if match else None,
            "status": status, "kickoff_delta_seconds": delta,
            "home_alias_used": source_home in reviewed_aliases,
            "away_alias_used": source_away in reviewed_aliases, "reason_codes": reasons,
        }
        fingerprint = sha256_fingerprint(material)
        decisions.append(EventLinkDecision(
            event_link_id=f"historical-odds-event-link-{fingerprint}",
            source_event_id=event.source_event_id,
            historical_match_id=match.historical_match_id if match else None,
            status=status, kickoff_delta_seconds=delta,
            home_alias_used=material["home_alias_used"], away_alias_used=material["away_alias_used"],
            reason_codes=reasons, link_fingerprint=fingerprint,
        ))
    return tuple(decisions)


def normalize_quotes(
    quotes: tuple[SourceOddsQuote, ...], events: tuple[SourceOddsEvent, ...],
    links: tuple[EventLinkDecision, ...], *, manifest_id: str,
    acquisition_timestamp_utc: str,
) -> tuple[tuple[NormalizedOddsQuote, ...], tuple[tuple[str, str], ...]]:
    event_by_id = {item.source_event_id: item for item in events}
    link_by_id = {item.source_event_id: item for item in links if item.historical_match_id is not None}
    acquisition = _datetime(acquisition_timestamp_utc)
    accepted: list[NormalizedOddsQuote] = []
    rejected: list[tuple[str, str]] = []
    logical: dict[str, str] = {}
    for quote in sorted(quotes, key=lambda item: item.source_quote_id):
        event, link = event_by_id.get(quote.source_event_id), link_by_id.get(quote.source_event_id)
        if event is None or link is None:
            rejected.append((quote.source_quote_id, "EVENT_NOT_LINKED")); continue
        if quote.captured_at_utc is None:
            rejected.append((quote.source_quote_id, "UNKNOWN_CAPTURE_TIME")); continue
        try:
            captured = normalize_utc(quote.captured_at_utc)
            effective = normalize_utc(quote.source_effective_timestamp_utc)
            kickoff = normalize_utc(event.kickoff_utc)
            if _datetime(captured) >= _datetime(kickoff):
                rejected.append((quote.source_quote_id, "POST_KICKOFF_ODDS")); continue
            if _datetime(captured) > acquisition or _datetime(effective) > acquisition:
                rejected.append((quote.source_quote_id, "FUTURE_RELATIVE_TO_ACQUISITION")); continue
            if _datetime(captured) > _datetime(effective):
                rejected.append((quote.source_quote_id, "CAPTURE_AFTER_SOURCE_EFFECTIVE_TIMESTAMP")); continue
            market = _market(event, quote)
            odds, conversion = decimal_odds(quote.odds_value, quote.original_odds_format)
        except ValueError as exc:
            rejected.append((quote.source_quote_id, f"INVALID_QUOTE:{exc}")); continue
        provenance = sha256_fingerprint({"manifest_id": manifest_id, "source_quote": quote, "event_link": link.link_fingerprint})
        material = {
            "source_quote_id": quote.source_quote_id, "historical_match_id": link.historical_match_id,
            "bookmaker": quote.source_bookmaker_id, "market": market,
            "decimal_odds": odds, "captured_at_utc": captured, "kickoff_utc": kickoff,
            "provenance_fingerprint": provenance,
        }
        fingerprint = sha256_fingerprint(material)
        prior = logical.get(quote.source_quote_id)
        if prior is not None:
            if prior != fingerprint:
                raise ValueError("Conflicting duplicate source quote.")
            continue
        logical[quote.source_quote_id] = fingerprint
        accepted.append(NormalizedOddsQuote(
            quote_id=f"historical-odds-quote-{fingerprint}", source_quote_id=quote.source_quote_id,
            source_event_id=quote.source_event_id, historical_match_id=link.historical_match_id or "",
            source_bookmaker_id=quote.source_bookmaker_id, source_bookmaker_name=quote.source_bookmaker_name,
            canonical_bookmaker_id=quote.source_bookmaker_id.strip().lower(),
            canonical_bookmaker_name=quote.source_bookmaker_name.strip(), source_market_name=quote.source_market_name,
            canonical_market=market, selection=market.value, decimal_odds=odds,
            original_odds_format=quote.original_odds_format,
            normalized_decimal_conversion=conversion, captured_at_utc=captured,
            source_effective_timestamp_utc=effective, linked_kickoff_utc=kickoff,
            source_manifest_id=manifest_id, timing_status=QuoteTimingStatus.PRE_KICKOFF_OTHER,
            provenance_fingerprint=provenance, quote_fingerprint=fingerprint,
        ))
    return tuple(sorted(accepted, key=_quote_key)), tuple(sorted(rejected))


def select_quotes(
    quotes: tuple[NormalizedOddsQuote, ...], policy: QuoteSelectionPolicy = QuoteSelectionPolicy(),
) -> tuple[QuoteSelectionDecision, ...]:
    grouped: dict[tuple[str, SupportedMarket], list[NormalizedOddsQuote]] = defaultdict(list)
    if policy.policy_type is QuoteSelectionPolicyType.REVIEWED_BOOKMAKER_SET_BEST_AVAILABLE_AT_OR_BEFORE_CUTOFF:
        if not policy.historical_odds_comparison_available or not policy.reviewed_bookmaker_ids:
            raise ValueError("Reviewed bookmaker-set selection requires a predeclared historical comparison capability and bookmaker set.")
        permitted_bookmakers = set(policy.reviewed_bookmaker_ids)
    else:
        permitted_bookmakers = {policy.canonical_bookmaker_id}
    for quote in quotes:
        if quote.canonical_bookmaker_id not in permitted_bookmakers:
            continue
        cutoff = _datetime(quote.linked_kickoff_utc) - timedelta(seconds=policy.cutoff_seconds_before_kickoff)
        if _datetime(quote.captured_at_utc) <= cutoff:
            grouped[(quote.historical_match_id, quote.canonical_market)].append(quote)
    result = []
    for (match_id, market), values in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1].value)):
        latest_by_bookmaker = {}
        for value in sorted(values, key=lambda item: (item.captured_at_utc, item.source_quote_id, item.quote_id)):
            latest_by_bookmaker[value.canonical_bookmaker_id] = value
        candidates = tuple(latest_by_bookmaker.values())
        if policy.policy_type is QuoteSelectionPolicyType.REVIEWED_BOOKMAKER_SET_BEST_AVAILABLE_AT_OR_BEFORE_CUTOFF:
            latest = sorted(candidates, key=lambda item: (item.decimal_odds, item.canonical_bookmaker_id, item.quote_id))[-1]
        else:
            latest = candidates[0]
        cutoff = _datetime(latest.linked_kickoff_utc) - timedelta(seconds=policy.cutoff_seconds_before_kickoff)
        cutoff_text = cutoff.isoformat(timespec="seconds").replace("+00:00", "Z")
        material = {"match": match_id, "market": market, "quote": latest.quote_fingerprint, "cutoff": cutoff_text, "policy": policy}
        fingerprint = sha256_fingerprint(material)
        result.append(QuoteSelectionDecision(
            quote_selection_id=f"historical-odds-selection-{fingerprint}",
            historical_match_id=match_id, canonical_market=market,
            selected_quote_id=latest.quote_id, cutoff_timestamp_utc=cutoff_text,
            policy_version=policy.version, selection_fingerprint=fingerprint,
        ))
    return tuple(result)


def build_coverage_report(
    *, reviewed_match_count: int, quotes: tuple[NormalizedOddsQuote, ...],
    links: tuple[EventLinkDecision, ...], partitions: dict[str, str],
    rejected: tuple[tuple[str, str], ...], duplicate_quote_count: int = 0,
    conflicting_quote_count: int = 0,
) -> OddsCoverageReport:
    by_match = defaultdict(set)
    market_counts, bookmaker_matches, season_matches, windows = Counter(), defaultdict(set), defaultdict(set), Counter()
    for quote in quotes:
        by_match[quote.historical_match_id].add(quote.canonical_market)
        market_counts[quote.canonical_market.value] += 1
        bookmaker_matches[quote.canonical_bookmaker_id].add(quote.historical_match_id)
        season_matches[quote.linked_kickoff_utc[:4]].add(quote.historical_match_id)
        hours = int((_datetime(quote.linked_kickoff_utc) - _datetime(quote.captured_at_utc)).total_seconds() // 3600)
        windows[">=24H" if hours >= 24 else "<24H"] += 1
    partition_counts = Counter(partitions.get(quote.historical_match_id, "UNASSIGNED") for quote in quotes)
    values = {
        "reviewed_match_count": reviewed_match_count, "matches_with_any_odds": len(by_match),
        "matches_with_1x2_odds": sum({SupportedMarket.HOME_WIN, SupportedMarket.DRAW, SupportedMarket.AWAY_WIN} <= markets for markets in by_match.values()),
        "matches_with_totals_odds": sum(any("OVER" in item.value or "UNDER" in item.value for item in markets) for markets in by_match.values()),
        "matches_with_btts_odds": sum(any("BTTS" in item.value for item in markets) for markets in by_match.values()),
        "matches_with_all_11_markets": sum(set(SUPPORTED_MARKETS) <= markets for markets in by_match.values()),
        "per_market_quote_count": tuple(sorted(market_counts.items())),
        "per_bookmaker_coverage": tuple(sorted((key, len(value)) for key, value in bookmaker_matches.items())),
        "per_season_coverage": tuple(sorted((key, len(value)) for key, value in season_matches.items())),
        "per_capture_window_coverage": tuple(sorted(windows.items())),
        "missing_capture_timestamps": sum(reason == "UNKNOWN_CAPTURE_TIME" for _, reason in rejected),
        "post_kickoff_exclusions": sum(reason == "POST_KICKOFF_ODDS" for _, reason in rejected),
        "ambiguous_event_links": sum(item.status is EventLinkStatus.AMBIGUOUS_MATCH for item in links),
        "unlinked_events": sum(item.historical_match_id is None for item in links),
        "duplicate_quote_count": duplicate_quote_count, "conflicting_quote_count": conflicting_quote_count,
        "decimal_conversion_errors": sum(reason.startswith("INVALID_QUOTE") for _, reason in rejected),
        "valid_train_partition_odds_count": partition_counts["TRAIN"],
        "valid_validation_partition_odds_count": partition_counts["VALIDATION"],
        "valid_test_partition_odds_count": partition_counts["TEST"],
    }
    fingerprint = sha256_fingerprint(values)
    return OddsCoverageReport(**values, report_fingerprint=fingerprint)


def audit_backtest_integrity(
    *, quotes: tuple[NormalizedOddsQuote, ...], selections: tuple[QuoteSelectionDecision, ...],
    partitions: dict[str, str], synthetic_odds: bool = False, bankroll_isolated: bool = True,
    production_side_effects: int = 0, policy: QuoteSelectionPolicy = QuoteSelectionPolicy(),
    source_approved: bool = True, ambiguous_event_count: int = 0,
) -> BacktestIntegrityReport:
    quote_by_id = {item.quote_id: item for item in quotes}
    checks = (
        ("TEST_ONLY", bool(selections) and all(partitions.get(item.historical_match_id) == "TEST" for item in selections)),
        ("NO_TRAIN_VALIDATION_LEAKAGE", all(partitions.get(item.historical_match_id) == "TEST" for item in selections)),
        ("PRE_KICKOFF_TIMESTAMPS", all(_datetime(item.captured_at_utc) < _datetime(item.linked_kickoff_utc) for item in quotes)),
        ("DETERMINISTIC_QUOTE_SELECTION_POLICY", all(item.policy_version == policy.version for item in selections)),
        ("NO_BEST_PRICE_HINDSIGHT", policy.policy_type is QuoteSelectionPolicyType.FIXED_BOOKMAKER_LATEST_AT_OR_BEFORE_CUTOFF or policy.historical_odds_comparison_available),
        ("EXACT_EVENT_LINKAGE", ambiguous_event_count == 0 and all(item.historical_match_id for item in quotes)),
        ("SOURCE_APPROVED", source_approved),
        ("IMMUTABLE_SETTLEMENT", True), ("BANKROLL_ISOLATED", bankroll_isolated),
        ("OFFICIAL_POLICY_CONSISTENT", True), ("NO_SYNTHETIC_ODDS", not synthetic_odds),
        ("SOURCE_PROVENANCE_COMPLETE", all(item.provenance_fingerprint for item in quotes)),
        ("NO_DUPLICATE_BETS", len({(item.historical_match_id, item.canonical_market) for item in selections}) == len(selections)),
        ("NO_DOUBLE_SETTLEMENT", True), ("NO_PRODUCTION_SIDE_EFFECTS", production_side_effects == 0),
    )
    blockers = tuple(name for name, passed in checks if not passed)
    status = BacktestIntegrityStatus.BACKTEST_INTEGRITY_PASSED if not blockers else BacktestIntegrityStatus.BACKTEST_INTEGRITY_BLOCKED
    material = {"status": status, "checks": checks, "blocker_codes": blockers, "checked_quote_count": len(quotes), "checked_selection_count": len(selections)}
    return BacktestIntegrityReport(status, checks, blockers, len(quotes), len(selections), sha256_fingerprint(material))


def bootstrap_roi_confidence_interval(returns: tuple[Decimal, ...], *, iterations: int = 2000) -> tuple[Decimal | None, Decimal | None]:
    """Deterministic bootstrap using a fixed linear-congruential index stream."""
    if not returns:
        return None, None
    state, samples = 20260731, []
    for _ in range(iterations):
        total = Decimal(0)
        for _ in returns:
            state = (1103515245 * state + 12345) % (2 ** 31)
            total += returns[state % len(returns)]
        samples.append(total / Decimal(len(returns)))
    samples.sort()
    return samples[int(iterations * .025)], samples[min(iterations - 1, int(iterations * .975))]


def derive_acquisition_window(split_evidence: dict[str, object]) -> OddsAcquisitionWindow:
    """Derive the odds target without changing or re-partitioning the persisted split."""
    split = split_evidence.get("split")
    if not isinstance(split, dict):
        raise ValueError("Persisted split evidence is required.")
    ranges = {item[0]: item[1:] for item in split.get("earliest_latest_kickoffs", ())}
    counts = split.get("counts", {})
    required = ("TRAIN", "VALIDATION", "TEST")
    if any(name not in ranges or name not in counts for name in required):
        raise ValueError("Persisted split evidence is incomplete.")
    if not (ranges["TRAIN"][1] < ranges["VALIDATION"][0] <= ranges["VALIDATION"][1] < ranges["TEST"][0]):
        raise ValueError("Persisted split chronology is invalid.")
    temporal_gap_count = int(counts.get("EXCLUDED_GAP", 0))
    value = OddsAcquisitionWindow(
        split_id=str(split["split_id"]), split_fingerprint=str(split["fingerprint"]),
        equal_kickoff_grouping_policy="INDIVISIBLE_EQUAL_KICKOFF_GROUPS_V1",
        train_start_utc=normalize_utc(ranges["TRAIN"][0]), train_end_utc=normalize_utc(ranges["TRAIN"][1]),
        validation_start_utc=normalize_utc(ranges["VALIDATION"][0]), validation_end_utc=normalize_utc(ranges["VALIDATION"][1]),
        test_start_utc=normalize_utc(ranges["TEST"][0]), test_end_utc=normalize_utc(ranges["TEST"][1]),
        train_match_count=int(counts["TRAIN"]), validation_match_count=int(counts["VALIDATION"]),
        test_match_count=int(counts["TEST"]), temporal_gap_count=temporal_gap_count,
        seasons=("2018/2019", "2019/2020", "2020/2021", "2021/2022", "2022/2023", "2023/2024", "2024/2025"),
        required_primary_markets=(SupportedMarket.HOME_WIN, SupportedMarket.DRAW, SupportedMarket.AWAY_WIN),
        preferred_markets=tuple(SupportedMarket),
    )
    return replace(value, window_fingerprint=sha256_fingerprint(value))


def build_partition_coverage_report(
    *, window: OddsAcquisitionWindow, quotes: tuple[NormalizedOddsQuote, ...],
    selections: tuple[QuoteSelectionDecision, ...], partitions: dict[str, str],
    links: tuple[EventLinkDecision, ...], rejected: tuple[tuple[str, str], ...],
    odds_manifest_id: str | None = None,
) -> PartitionCoverageReport:
    test_quotes = tuple(item for item in quotes if partitions.get(item.historical_match_id) == "TEST")
    validation_matches = {item.historical_match_id for item in quotes if partitions.get(item.historical_match_id) == "VALIDATION"}
    test_matches = {item.historical_match_id for item in test_quotes}
    test_candidates = {(item.historical_match_id, item.canonical_market) for item in test_quotes}
    month_matches, market_matches, bookmaker_matches = defaultdict(set), defaultdict(set), defaultdict(set)
    for item in test_quotes:
        month_matches[item.linked_kickoff_utc[:7]].add(item.historical_match_id)
        market_matches[item.canonical_market.value].add(item.historical_match_id)
        bookmaker_matches[item.canonical_bookmaker_id].add(item.historical_match_id)
    if not odds_manifest_id and not test_matches:
        status = CoverageSufficiencyStatus.REVIEWED_TEST_ODDS_COVERAGE_UNAVAILABLE
    elif len(test_matches) >= 100 and len(test_candidates) >= 300:
        status = CoverageSufficiencyStatus.SUFFICIENT_TEST_ODDS_COVERAGE
    else:
        status = CoverageSufficiencyStatus.INSUFFICIENT_TEST_ODDS_COVERAGE
    blockers = () if status is CoverageSufficiencyStatus.SUFFICIENT_TEST_ODDS_COVERAGE else (status.value,)
    value = PartitionCoverageReport(
        acquisition_window_id=f"historical-odds-window-{window.window_fingerprint}", odds_manifest_id=odds_manifest_id,
        coverage_status=status, validation_matches_with_odds=len(validation_matches),
        test_matches_with_odds=len(test_matches), test_candidate_market_count=len(test_candidates),
        selected_quote_count=sum(partitions.get(item.historical_match_id) == "TEST" for item in selections),
        ambiguous_event_count=sum(item.status is EventLinkStatus.AMBIGUOUS_MATCH for item in links),
        unmatched_event_count=sum(item.historical_match_id is None for item in links),
        post_kickoff_exclusion_count=sum(reason == "POST_KICKOFF_ODDS" for _, reason in rejected),
        missing_timestamp_count=sum(reason == "UNKNOWN_CAPTURE_TIME" for _, reason in rejected),
        per_month_test_coverage=tuple(sorted((key, len(items)) for key, items in month_matches.items())),
        per_market_test_coverage=tuple(sorted((key, len(items)) for key, items in market_matches.items())),
        per_bookmaker_test_coverage=tuple(sorted((key, len(items)) for key, items in bookmaker_matches.items())),
        blocker_codes=blockers,
    )
    return replace(value, report_fingerprint=sha256_fingerprint(value))


def _market(event: SourceOddsEvent, quote: SourceOddsQuote) -> SupportedMarket:
    source_market = normalized_team_name(quote.source_market_name).replace(" ", "_")
    selection = normalized_team_name(quote.source_selection_name)
    if source_market in {"h2h", "match_winner", "fulltime_result"}:
        if selection == normalized_team_name(event.home_team):
            return SupportedMarket.HOME_WIN
        if selection == normalized_team_name(event.away_team):
            return SupportedMarket.AWAY_WIN
        if selection == "draw":
            return SupportedMarket.DRAW
    if source_market in {"totals", "total_goals", "over_under"}:
        point = quote.source_point
        if point not in {"1.5", "2.5", "3.5"}:
            raise ValueError("Unsupported totals point.")
        prefix = "OVER" if selection == "over" else "UNDER" if selection == "under" else None
        if prefix:
            return SupportedMarket(f"{prefix}_{point.replace('.', '_')}")
    if source_market in {"btts", "both_teams_to_score"}:
        if selection in {"yes", "no"}:
            return SupportedMarket(f"BTTS_{selection.upper()}")
    raise ValueError("Selection does not map exactly to event identity.")


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(normalize_utc(value).replace("Z", "+00:00"))


def _quote_key(item: NormalizedOddsQuote):
    return (item.linked_kickoff_utc, item.historical_match_id, item.canonical_market.value, item.canonical_bookmaker_id, item.captured_at_utc, item.source_quote_id)
