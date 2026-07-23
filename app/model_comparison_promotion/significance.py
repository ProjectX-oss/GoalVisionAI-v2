"""Reproducible paired bootstrap intervals and uncertainty classifications."""

from __future__ import annotations

import random
from decimal import Decimal

from .fingerprint import canonical_json, sha256_fingerprint, statistical_evidence_fingerprint
from .models import StatisticalEvidence, UncertaintyClassification


def calculate_statistical_evidence(
    champion_run,
    challenger_run,
    *,
    comparison_fingerprint,
    policy,
):
    seed = int(
        sha256_fingerprint(
            (comparison_fingerprint, policy.significance_policy_version)
        )[:16],
        16,
    ) % (2**63 - 1)
    evidence = []
    champion_predictions = {
        item.training_example_id: item for item in champion_run.predictions
    }
    challenger_predictions = {
        item.training_example_id: item for item in challenger_run.predictions
    }
    shared = tuple(sorted(set(champion_predictions) & set(challenger_predictions)))
    for name, extractor in (
        ("BRIER_DELTA", _prediction_brier_delta),
        ("LOG_LOSS_DELTA", _prediction_log_loss_delta),
    ):
        deltas = tuple(
            extractor(champion_predictions[item], challenger_predictions[item])
            for item in shared
        )
        evidence.append(
            _bootstrap_record(name, deltas, seed + len(evidence), policy, len(evidence))
        )
    champion_returns = _returns_by_match(champion_run)
    challenger_returns = _returns_by_match(challenger_run)
    shared_bets = tuple(sorted(set(champion_returns) & set(challenger_returns)))
    return_deltas = tuple(
        challenger_returns[item] - champion_returns[item] for item in shared_bets
    )
    evidence.append(
        _bootstrap_record(
            "MEAN_RETURN_DELTA",
            return_deltas,
            seed + len(evidence),
            policy,
            len(evidence),
        )
    )
    evidence.append(
        _bootstrap_record(
            "ROI_DELTA",
            return_deltas,
            seed + len(evidence),
            policy,
            len(evidence),
        )
    )
    return tuple(evidence)


def _bootstrap_record(name, values, seed, policy, order):
    mean = _mean(values) if values else None
    if not values:
        lower = upper = None
        classification = UncertaintyClassification.INCONCLUSIVE
    else:
        rng = random.Random(seed)
        count = len(values)
        samples = []
        for _ in range(policy.bootstrap_iterations):
            sample = tuple(values[rng.randrange(count)] for _ in range(count))
            samples.append(_mean(sample))
        samples.sort()
        alpha = (Decimal(1) - policy.confidence_level) / Decimal(2)
        lower = samples[min(len(samples) - 1, int(alpha * len(samples)))]
        upper = samples[min(len(samples) - 1, int((Decimal(1) - alpha) * len(samples)))]
        if lower > 0 or upper < 0:
            classification = (
                UncertaintyClassification.STRONG_EVIDENCE
                if count >= 100
                else UncertaintyClassification.MODERATE_EVIDENCE
            )
        elif count >= 100:
            classification = UncertaintyClassification.WEAK_EVIDENCE
        else:
            classification = UncertaintyClassification.INCONCLUSIVE
    material = {
        "name": name,
        "count": len(values),
        "seed": seed,
        "iterations": policy.bootstrap_iterations,
        "effect_size": mean,
        "lower": lower,
        "upper": upper,
        "classification": classification,
        "policy_version": policy.significance_policy_version,
    }
    fingerprint = statistical_evidence_fingerprint(material)
    return StatisticalEvidence(
        statistical_row_id=f"model-comparison-statistical-{sha256_fingerprint((fingerprint, order))}",
        evidence_name=name,
        paired_sample_count=len(values),
        deterministic_seed=seed,
        bootstrap_iterations=policy.bootstrap_iterations,
        effect_size=mean,
        lower_confidence_bound=lower,
        upper_confidence_bound=upper,
        uncertainty_classification=classification,
        detail_snapshot=canonical_json(material),
        evidence_fingerprint=fingerprint,
        deterministic_order=order,
    )


def _prediction_brier_delta(champion, challenger):
    labels = dict(champion.labels)
    c = dict((item.target.value, item.probability) for item in champion.calibrated_probabilities.ordered_probabilities)
    h = dict((item.target.value, item.probability) for item in challenger.calibrated_probabilities.ordered_probabilities)
    c_score = _mean(tuple((c[name] - Decimal(value)) ** 2 for name, value in labels.items()))
    h_score = _mean(tuple((h[name] - Decimal(value)) ** 2 for name, value in labels.items()))
    return c_score - h_score


def _prediction_log_loss_delta(champion, challenger):
    labels = dict(champion.labels)
    c = dict((item.target.value, item.probability) for item in champion.calibrated_probabilities.ordered_probabilities)
    h = dict((item.target.value, item.probability) for item in challenger.calibrated_probabilities.ordered_probabilities)
    c_score = _mean(tuple(_binary_log_loss(c[name], value) for name, value in labels.items()))
    h_score = _mean(tuple(_binary_log_loss(h[name], value) for name, value in labels.items()))
    return c_score - h_score


def _binary_log_loss(probability, outcome):
    return -(Decimal(outcome) * probability.ln() + Decimal(1 - outcome) * (Decimal(1) - probability).ln())


def _returns_by_match(run):
    selections = {item.selection_id: item for item in run.selections}
    return {
        (
            selections[item.selection_id].historical_match_id,
            selections[item.selection_id].market_identity.value,
        ): (
            item.net_profit_loss / selections[item.selection_id].applied_stake_amount
            if selections[item.selection_id].applied_stake_amount
            else Decimal(0)
        )
        for item in run.settlements
        if item.selection_id in selections
    }


def _mean(values):
    return sum(values, Decimal(0)) / Decimal(len(values))
