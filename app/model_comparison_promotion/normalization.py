"""Fair-scope derivation without inventing predictions, odds, or outcomes."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.historical_backtesting import build_ledger, calculate_betting_metrics

from .fingerprint import canonical_json, sha256_fingerprint
from .models import (
    ComparisonExclusion,
    ComparisonMode,
    CompatibilityStatus,
    SourceEvidence,
)


def derive_comparison_scope(champion_run, challenger_run, scope):
    champion_predictions = _filtered_predictions(champion_run.predictions, scope)
    challenger_predictions = _filtered_predictions(challenger_run.predictions, scope)
    champion_by_example = {
        item.training_example_id: item for item in champion_predictions
    }
    challenger_by_example = {
        item.training_example_id: item for item in challenger_predictions
    }
    shared_ids = tuple(sorted(set(champion_by_example) & set(challenger_by_example)))
    exact = (
        tuple(sorted(champion_by_example)) == tuple(sorted(challenger_by_example))
        and champion_run.command.odds_dataset_fingerprint
        == challenger_run.command.odds_dataset_fingerprint
        and champion_run.command.initial_bankroll
        == challenger_run.command.initial_bankroll
        and _strict_policy_tuple(champion_run.command)
        == _strict_policy_tuple(challenger_run.command)
    )
    if scope.mode is ComparisonMode.EXACT_SHARED_BACKTEST_SCOPE and not exact:
        return None, None, (), (), ("EXACT_SHARED_SCOPE_MISMATCH",)
    exclusions = []
    if scope.mode is not ComparisonMode.EXACT_SHARED_BACKTEST_SCOPE:
        for source, values in (
            ("CHAMPION", set(champion_by_example) - set(shared_ids)),
            ("CHALLENGER", set(challenger_by_example) - set(shared_ids)),
        ):
            for identity in sorted(values):
                material = (source, identity, "NON_OVERLAPPING_TEST_EXAMPLE")
                exclusions.append(
                    ComparisonExclusion(
                        exclusion_id=f"model-comparison-exclusion-{sha256_fingerprint(material)}",
                        challenger_candidate_id=None,
                        exclusion_stage="SCOPE_NORMALIZATION",
                        exclusion_reason=f"{source}_NON_OVERLAPPING_TEST_EXAMPLE",
                        detail_snapshot=canonical_json({"training_example_id": identity}),
                        deterministic_order=len(exclusions),
                    )
                )
    champion = _subset_run(champion_run, shared_ids, scope.required_markets)
    challenger = _subset_run(challenger_run, shared_ids, scope.required_markets)
    status = (
        CompatibilityStatus.COMPATIBLE
        if exact
        else CompatibilityStatus.NORMALIZED
        if scope.mode is ComparisonMode.INTERSECTION_SCOPE
        else CompatibilityStatus.REVIEW_REQUIRED
    )
    evidence_material = {
        "mode": scope.mode,
        "exact": exact,
        "shared_ids": shared_ids,
        "champion_population": tuple(sorted(champion_by_example)),
        "challenger_population": tuple(sorted(challenger_by_example)),
        "strict_policies_equal": _strict_policy_tuple(champion_run.command)
        == _strict_policy_tuple(challenger_run.command),
    }
    evidence = SourceEvidence(
        evidence_row_id=f"model-comparison-source-{sha256_fingerprint(evidence_material)}",
        category="SCOPE",
        name="FAIR_TEST_POPULATION",
        champion_value_snapshot=canonical_json(tuple(sorted(champion_by_example))),
        challenger_value_snapshot=canonical_json(tuple(sorted(challenger_by_example))),
        compatibility_status=status,
        detail_snapshot=canonical_json(evidence_material),
        evidence_fingerprint=sha256_fingerprint(evidence_material),
        deterministic_order=0,
    )
    reasons = ("POLICY_NORMALIZED_SCOPE_REQUIRES_REVIEW",) if (
        scope.mode is ComparisonMode.POLICY_NORMALIZED_SCOPE and not exact
    ) else ()
    return champion, challenger, (evidence,), tuple(exclusions), tuple(reasons)


def verify_scope_compatibility(champion_run, challenger_run, scope):
    result = derive_comparison_scope(champion_run, challenger_run, scope)
    return () if result[0] is not None else result[4]


def _filtered_predictions(predictions, scope):
    result = []
    for item in predictions:
        if scope.required_competitions and item.competition not in scope.required_competitions:
            continue
        if scope.required_seasons and item.season not in scope.required_seasons:
            continue
        if scope.kickoff_lower_bound and item.kickoff_utc < scope.kickoff_lower_bound:
            continue
        if scope.kickoff_upper_bound and item.kickoff_utc > scope.kickoff_upper_bound:
            continue
        result.append(item)
    return tuple(result)


def _subset_run(run, shared_ids, required_markets):
    shared = set(shared_ids)
    predictions = tuple(
        item for item in run.predictions if item.training_example_id in shared
    )
    matches = {item.historical_match_id for item in predictions}
    selections = tuple(
        item
        for item in run.selections
        if item.historical_match_id in matches
        and (
            not required_markets
            or item.market_identity.value in required_markets
        )
    )
    selection_ids = {item.selection_id for item in selections}
    settlements = tuple(item for item in run.settlements if item.selection_id in selection_ids)
    ledger = build_ledger(
        run.command.initial_bankroll,
        selections,
        settlements,
        run_namespace=f"comparison-normalized:{run.backtest_run_id}",
    )
    assessments = tuple(
        item
        for item in run.assessments
        if item.historical_match_id in matches
        and (
            not required_markets
            or item.market_identity.value in required_markets
        )
    )
    _, aggregate = calculate_betting_metrics(
        predictions,
        assessments,
        selections,
        settlements,
        ledger,
        run.command.initial_bankroll,
    )
    final_bankroll = (
        ledger[-1].bankroll_after if ledger else run.command.initial_bankroll
    )
    return replace(
        run,
        predictions=predictions,
        selections=selections,
        settlements=settlements,
        ledger=ledger,
        assessments=assessments,
        aggregate_betting_metrics=aggregate,
        final_bankroll=final_bankroll,
        maximum_drawdown=max(
            (item.percentage_drawdown for item in ledger),
            default=Decimal(0),
        ),
    )


def _strict_policy_tuple(command):
    return (
        command.odds_selection_policy_version,
        command.selection_policy_version,
        command.staking_policy_version,
        command.settlement_policy_version,
        command.bankroll_policy_version,
        command.metric_policy_version,
        command.currency,
        command.competitions,
        command.seasons,
        command.markets,
        command.kickoff_lower_bound,
        command.kickoff_upper_bound,
        command.bookmaker_filters,
    )
