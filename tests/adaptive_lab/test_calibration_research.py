"""Synthetic calibration tests never consume production data or sealed holdout."""
from copy import deepcopy
from datetime import timedelta
import json
from math import log
import pytest
from app.adaptive_lab.calibration_research import split_validation, research, apply, FAMILY
from app.adaptive_lab.contracts import digest
from app.adaptive_lab.models import candidate_specs, train, predict, validate_artifact
from .conftest import observation, START


def dataset():
    rows = [observation(i, outcome="LOST" if i % 4 == 0 else "WON") for i in range(700)]
    training = rows[:80]
    validation = rows[100:]
    spec = next(s for s in candidate_specs("PREMATCH") if s["family"] == "LOGISTIC" and s["scope"] == "GLOBAL")
    raw = train(spec, training)
    # A deliberate synthetic overconfident constant predictor, not forward evidence.
    raw["coefficients"] = [0.] * len(raw["coefficients"])
    raw["bias"] = log(.9/.1)
    raw["artifact_fingerprint"] = digest({k:v for k,v in raw.items() if k!="artifact_fingerprint"})
    return training, split_validation(validation), raw


def test_disjoint_calibration_is_reproducible_serializable_and_improves_probability():
    training, split, raw = dataset()
    assert split["status"] == "CALIBRATION_DATASET_READY"
    now = START+timedelta(days=300)
    result = research(raw, training, split, dataset_fingerprint="synthetic", now=now)
    assert result["status"] == "CALIBRATION_QUALITY_PASS", result
    artifact = result["artifact"]
    assert artifact["family"] == FAMILY
    assert result == research(raw, training, split, dataset_fingerprint="synthetic", now=now)
    assert artifact == json.loads(json.dumps(artifact))
    validate_artifact(artifact)
    p = predict(artifact, split["partitions"]["VALIDATION_EVALUATION"][0])
    assert .72 < p < .78
    e = result["evidence"]
    assert e["holdout_used_for_fitting"] is e["train_overlap"] is False
    assert e["methods"]["isotonic"]["reason"] == "ISOTONIC_SAMPLE_INSUFFICIENT"
    chosen = e["methods"][e["selected_method"]]["metrics"]
    assert chosen["brier"] < e["raw_metrics"]["brier"]
    assert chosen["ece"] < .02 and chosen["mce"] < .02
    bad = deepcopy(artifact)
    bad["calibrator"]["method"] = "identity"
    with pytest.raises(ValueError, match="INTEGRITY"):
        validate_artifact(bad)


@pytest.mark.parametrize("mutation,reason", [
    ("fixture_overlap","LEAKAGE"), ("combo","SOURCE_INVALID"),
    ("future","FUTURE_LABEL"), ("training_fingerprint","PROVENANCE_MISMATCH")])
def test_calibration_cannot_reuse_train_or_unavailable_labels(mutation, reason):
    training, split, raw = dataset()
    if mutation == "fixture_overlap":
        split["partitions"]["CALIBRATION_FIT"][0]["fixture_id"] = training[0]["fixture_id"]
    elif mutation == "combo":
        split["partitions"]["CALIBRATION_FIT"][0]["source_product"] = "COMBO_LEG"
    elif mutation == "future":
        split["partitions"]["VALIDATION_EVALUATION"][-1]["settled_at"] = (START+timedelta(days=400)).isoformat()
    else:
        raw["training_fingerprint"] = "different"
        raw["artifact_fingerprint"] = digest({k:v for k,v in raw.items() if k!="artifact_fingerprint"})
    with pytest.raises(ValueError, match=reason):
        research(raw, training, split, dataset_fingerprint="synthetic", now=START+timedelta(days=300))


@pytest.mark.parametrize("p", [0,1,float("nan"),float("inf"),-.1,1.1])
def test_invalid_probability_is_never_clamped(p):
    with pytest.raises(ValueError):
        apply({"method":"temperature","inverse_temperature":1.},p)


def test_validation_split_purges_label_overlap_and_small_sample():
    rows = [observation(i, outcome="WON" if i%2 else "LOST") for i in range(500)]
    split = split_validation(rows)
    fit = split["partitions"]["CALIBRATION_FIT"]
    evaluate = split["partitions"]["VALIDATION_EVALUATION"]
    assert max(r["settled_at"] for r in fit) < min(r["prediction_created_at"] for r in evaluate)
    assert split["counts"]["CALIBRATION_PURGED"] > 0
    assert split_validation(rows[:30])["status"] == "CALIBRATION_DATASET_NOT_READY"


def test_settlement_coordinator_only_recommends_promotion(monkeypatch):
    from app.adaptive_lab.coordinator import LearningCoordinator
    class Repo:
        def all(self, table, stream):
            return [{"shadow_id":"s"}] if table=="shadow_runs" else []
    c = LearningCoordinator(Repo())
    monkeypatch.setattr(c.governance, "promote", lambda *a,**k: pytest.fail("automatic promotion"))
    monkeypatch.setattr(c.governance, "rollback", lambda *a,**k: {"status":"NO_ROLLBACK_REQUIRED"})
    monkeypatch.setattr(c.governance, "recommend_promotion", lambda *a,**k: {"status":"PROMOTION_RECOMMENDED"})
    result = c.after_settlement("PREMATCH", now=START, train=False)
    assert result["promotions"] == [{"status":"PROMOTION_RECOMMENDED"}]
