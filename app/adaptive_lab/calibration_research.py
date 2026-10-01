"""Chronological challenger calibration, separate from TRAIN and sealed holdout."""
from __future__ import annotations
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from math import exp, isfinite, log
from app.calibration.calibrators import (CalibrationFitRequest, CalibrationFittingPolicy,
    PlattCalibrator, PlattFittingConfig, IsotonicCalibrator)
from app.calibration.models import CalibrationObservation, CalibrationScope, CalibrationTrainingWindow
from app.calibration.serialization import CalibratorSerializer
from .contracts import digest, learning_source, number, utc
from .performance import probability_metrics
from .policy import POLICY

VERSION = "PREMATCH_CALIBRATION_CHAIN_V1"
FAMILY = "CALIBRATED_PREMATCH_WRAPPER_V1"
MIN_ISOTONIC = 1000
MAX_ECE = .10
MAX_MCE = .20


def split_validation(rows: list[dict]) -> dict:
    """Reserve later validation fixtures for method selection; purge label overlap."""
    groups = defaultdict(list)
    for r in rows:
        if r["stream"] != "PREMATCH" or not learning_source(r) or r["target"] not in (0, 1):
            raise ValueError("CALIBRATION_SOURCE_INVALID")
        groups[str(r["fixture_id"])].append(r)
    ordered = sorted(groups.values(), key=lambda g: (min(utc(r["prediction_created_at"]) for r in g),
                                                     str(g[0]["fixture_id"])))
    cut = int(len(ordered)*.7)
    if not cut or cut == len(ordered):
        return {"status": "CALIBRATION_DATASET_NOT_READY", "blocked_by": ["CALIBRATION_SPLIT_UNAVAILABLE"],
                "counts": {"CALIBRATION_FIT": 0, "VALIDATION_EVALUATION": 0, "CALIBRATION_PURGED": len(rows)},
                "partitions": {"CALIBRATION_FIT": [], "VALIDATION_EVALUATION": [], "CALIBRATION_PURGED": rows}}
    boundary = min(utc(r["prediction_created_at"]) for r in ordered[cut])
    parts = {"CALIBRATION_FIT": [], "VALIDATION_EVALUATION": [], "CALIBRATION_PURGED": []}
    for i, group in enumerate(ordered):
        key = "CALIBRATION_FIT" if i < cut else "VALIDATION_EVALUATION"
        if i < cut and any(utc(r["settled_at"]) >= boundary-timedelta(hours=POLICY.embargo_hours) for r in group):
            key = "CALIBRATION_PURGED"
        parts[key].extend(group)
    fit, evaluate = parts["CALIBRATION_FIT"], parts["VALIDATION_EVALUATION"]
    reasons = []
    if len(fit) < POLICY.calibration_min:
        reasons.append("CALIBRATION_FIT_SAMPLE_INSUFFICIENT")
    if len(evaluate) < POLICY.subgroup_min:
        reasons.append("CALIBRATION_EVALUATION_SAMPLE_INSUFFICIENT")
    if min(sum(r["target"] == y for r in fit) for y in (0, 1)) < 10:
        reasons.append("CALIBRATION_CLASS_DIVERSITY_INSUFFICIENT")
    material = {"counts": {k: len(v) for k, v in parts.items()},
                "assignments": {k: [(r["observation_id"], r["observation_fingerprint"]) for r in v] for k,v in parts.items()},
                "boundary": boundary.isoformat(), "embargo_hours": POLICY.embargo_hours}
    return {**material, "fingerprint": digest(material), "partitions": parts,
            "status": "CALIBRATION_DATASET_NOT_READY" if reasons else "CALIBRATION_DATASET_READY",
            "blocked_by": reasons}


def _sigmoid(x):
    if x >= 0:
        return 1/(1+exp(-x))
    v = exp(x)
    return v/(1+v)


def _probability(p):
    p = number(p, low=0, high=1)
    if not 0 < p < 1:
        raise ValueError("CALIBRATION_RAW_PROBABILITY_INVALID")
    return p


def temperature_fit(probs, targets):
    """Bounded convex optimisation of binary logit scale; no endpoint clamping."""
    probabilities = [_probability(p) for p in probs]
    logits = [log(p/(1-p)) for p in probabilities]
    def derivative(scale):
        return sum(z*(_sigmoid(scale*z)-y) for z,y in zip(logits,targets))
    lo, hi = .05, 20.
    if derivative(lo) >= 0:
        scale = lo
    elif derivative(hi) <= 0:
        scale = hi
    else:
        for _ in range(100):
            mid = (lo+hi)/2
            if derivative(mid) < 0:
                lo = mid
            else:
                hi = mid
        scale = (lo+hi)/2
    return {"method": "temperature", "inverse_temperature": scale,
            "search_bounds": [.05,20.], "boundary_solution": scale in (.05,20.)}


def apply(calibrator: dict, probability) -> float:
    p = _probability(probability)
    if calibrator.get("method") == "temperature":
        scale = number(calibrator["inverse_temperature"], low=.05, high=20)
        result = _sigmoid(scale*log(p/(1-p)))
    else:
        fitted = CalibratorSerializer().deserialize(calibrator)
        if calibrator.get("method") == "platt":
            epsilon = float(fitted.fit_data.clipping_epsilon)
            if not epsilon <= p <= 1-epsilon:
                raise ValueError("PLATT_RAW_OUTSIDE_DECLARED_DOMAIN")
        result = float(fitted.calibrate(Decimal(str(p))))
    if not isfinite(result) or not 0 < result < 1:
        raise ValueError("CALIBRATED_PROBABILITY_ENDPOINT_OR_INVALID")
    return result


def _manifest(rows):
    return [[r["observation_id"], r["fixture_id"], r["observation_fingerprint"]] for r in rows]


def research(raw: dict, train_rows: list[dict], split: dict, *, dataset_fingerprint: str, now) -> dict:
    """Fit candidate methods only on calibration rows; select with later evidence."""
    from .models import predict, validate_artifact
    validate_artifact(raw)
    if raw.get("family") == FAMILY or raw["stream"] != "PREMATCH":
        raise ValueError("RAW_PREMATCH_ARTIFACT_REQUIRED")
    if split["blocked_by"]:
        raise ValueError("CALIBRATION_DATASET_NOT_READY")
    fit = split["partitions"]["CALIBRATION_FIT"]
    test = split["partitions"]["VALIDATION_EVALUATION"]
    for rows in (train_rows, fit, test):
        if any(not learning_source(r) or r["stream"] != "PREMATCH" for r in rows):
            raise ValueError("CALIBRATION_SOURCE_INVALID")
    for a, b in ((train_rows,fit),(train_rows,test),(fit,test)):
        if {r["fixture_id"] for r in a} & {r["fixture_id"] for r in b}:
            raise ValueError("CALIBRATION_TRAIN_VALIDATION_LEAKAGE")
        if {r["observation_id"] for r in a} & {r["observation_id"] for r in b}:
            raise ValueError("CALIBRATION_OBSERVATION_LEAKAGE")
        if max(utc(r["settled_at"]) for r in a) >= min(utc(r["prediction_created_at"]) for r in b):
            raise ValueError("CALIBRATION_CHRONOLOGY_INVALID")
    if max(utc(r["settled_at"]) for r in fit+test) > utc(now):
        raise ValueError("CALIBRATION_FUTURE_LABEL")
    training_used = [r for r in train_rows if r["target"] is not None]
    history_days = raw.get("spec", {}).get("history_days")
    if history_days:
        latest = max(utc(r["prediction_created_at"]) for r in training_used)
        training_used = [r for r in training_used if (latest-utc(r["prediction_created_at"])).days <= history_days]
    if digest([(r["observation_id"],r["observation_fingerprint"]) for r in training_used]) != raw["training_fingerprint"]:
        raise ValueError("RAW_TRAINING_PARTITION_PROVENANCE_MISMATCH")
    fit_probs = [_probability(predict(raw,r)) for r in fit]
    raw_probs = [_probability(predict(raw,r)) for r in test]
    raw_metrics = probability_metrics(list(zip(raw_probs, [r["target"] for r in test])))
    model_version = raw["artifact_fingerprint"]
    observations = [CalibrationObservation(r["observation_id"], int(r["fixture_id"]),
        str(r.get("competition_profile") or "UNKNOWN"), r["market"], r["market"],
        utc(r["prediction_created_at"]), utc(r["settled_at"]), Decimal(str(p)), r["target"],
        model_version=model_version) for r,p in zip(fit, fit_probs)]
    request = CalibrationFitRequest(utc(now), CalibrationTrainingWindow(
        min(o.prediction_timestamp for o in observations), max(o.outcome_timestamp for o in observations)),
        CalibrationScope.global_scope(), VERSION, min(utc(r["prediction_created_at"]) for r in test), model_version)
    fitting_policy = CalibrationFittingPolicy(global_minimum=POLICY.calibration_min)
    methods = [("platt", lambda: CalibratorSerializer().serialize(
        PlattCalibrator(config=PlattFittingConfig(epsilon=Decimal("1e-12")), policy=fitting_policy).fit(observations,request))),
        ("temperature", lambda: temperature_fit(fit_probs,[r["target"] for r in fit]))]
    if len(fit) >= MIN_ISOTONIC:
        methods.append(("isotonic", lambda: CalibratorSerializer().serialize(
            IsotonicCalibrator(policy=CalibrationFittingPolicy(global_minimum=MIN_ISOTONIC)).fit(observations,request))))
    evaluated, passed = {}, []
    for name, fitter in methods:
        try:
            fitted = fitter()
            for probe in (.01,.25,.5,.75,.99):
                apply(fitted,probe)
            calibrated = [apply(fitted,p) for p in raw_probs]
            m = probability_metrics(list(zip(calibrated,[r["target"] for r in test])))
            gates = {"brier_not_degraded": m["brier"] <= raw_metrics["brier"]+POLICY.brier_tolerance,
                     "log_loss_not_degraded": m["log_loss"] <= raw_metrics["log_loss"]+POLICY.logloss_tolerance,
                     "ece_not_degraded": m["ece"] <= raw_metrics["ece"]+POLICY.ece_tolerance,
                     "absolute_ece": m["ece"] <= MAX_ECE, "absolute_mce": m["mce"] <= MAX_MCE}
            evaluated[name] = {"passed": all(gates.values()), "gates": gates, "metrics": m,
                "extreme_probability_count": sum(p<.01 or p>.99 for p in calibrated),
                "raw_extreme_probability_count": sum(p<.01 or p>.99 for p in raw_probs)}
            if all(gates.values()):
                passed.append((m["log_loss"],m["brier"],name,fitted))
        except (ValueError, ArithmeticError) as exc:
            evaluated[name] = {"passed": False, "reason": type(exc).__name__}
    if len(fit) < MIN_ISOTONIC:
        evaluated["isotonic"] = {"passed": False, "reason": "ISOTONIC_SAMPLE_INSUFFICIENT", "minimum": MIN_ISOTONIC}
    provenance = {"version": VERSION, "dataset_fingerprint": dataset_fingerprint,
        "raw_model_fingerprint": model_version, "raw_training_fingerprint": raw["training_fingerprint"],
        "calibration_split_fingerprint": split["fingerprint"], "fitted_at": utc(now).isoformat(),
        "train_manifest_fingerprint": digest(_manifest(train_rows)),
        "fit_manifest": _manifest(fit), "evaluation_manifest": _manifest(test),
        "raw_metrics": raw_metrics, "methods": evaluated, "train_overlap": False,
        "holdout_used_for_fitting": False, "quality_passed": bool(passed)}
    if not passed:
        return {"status": "CALIBRATION_QUALITY_NOT_PROVEN", "evidence": provenance, "artifact": None}
    _,_,method,fitted = min(passed,key=lambda x:x[:3])
    provenance["selected_method"] = method
    wrapper = {"family": FAMILY, "stream": "PREMATCH", "raw_model": raw,
               "training_fingerprint": raw["training_fingerprint"], "calibrator": fitted,
               "calibration_evidence": provenance}
    wrapper["artifact_fingerprint"] = digest(wrapper)
    validate(wrapper)
    return {"status": "CALIBRATION_QUALITY_PASS", "evidence": provenance, "artifact": wrapper}


def validate(artifact: dict) -> None:
    from .models import validate_artifact
    required = {"family","stream","raw_model","training_fingerprint","calibrator","calibration_evidence","artifact_fingerprint"}
    if set(artifact) != required or artifact["family"] != FAMILY or artifact["stream"] != "PREMATCH":
        raise ValueError("CALIBRATION_ARTIFACT_SCHEMA_INVALID")
    if digest({k:v for k,v in artifact.items() if k!="artifact_fingerprint"}) != artifact["artifact_fingerprint"]:
        raise ValueError("ARTIFACT_INTEGRITY_FAILURE")
    if artifact["raw_model"].get("family") == FAMILY:
        raise ValueError("NESTED_CALIBRATION_FORBIDDEN")
    validate_artifact(artifact["raw_model"])
    e = artifact["calibration_evidence"]
    method = e.get("selected_method")
    if (e.get("version") != VERSION or e.get("raw_model_fingerprint") != artifact["raw_model"]["artifact_fingerprint"]
            or e.get("raw_training_fingerprint") != artifact["training_fingerprint"]
            or e.get("quality_passed") is not True or e.get("train_overlap") is not False
            or e.get("holdout_used_for_fitting") is not False
            or method != artifact["calibrator"].get("method")
            or len(e.get("fit_manifest",[])) < POLICY.calibration_min
            or len(e.get("evaluation_manifest",[])) < POLICY.subgroup_min
            or not e.get("methods",{}).get(method,{}).get("passed")):
        raise ValueError("CALIBRATION_PROVENANCE_OR_QUALITY_INVALID")
    for p in (.01,.25,.5,.75,.99):
        apply(artifact["calibrator"],p)


def predict(artifact: dict, row: dict) -> float:
    from .models import predict as raw_predict
    validate(artifact)
    return apply(artifact["calibrator"], raw_predict(artifact["raw_model"],row))
