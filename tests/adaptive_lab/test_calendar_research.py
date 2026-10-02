"""Calendar candidate tests: synthetic fixtures only, no scheduled runtime calls."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from math import log

import pytest

from app.adaptive_lab.calendar_research import CalendarPlan, calendar_dataset, PARTITIONS
from app.adaptive_lab.calibration_research import research
from app.adaptive_lab.contracts import digest
from app.adaptive_lab.datasets import chronological_dataset
from app.adaptive_lab.models import candidate_specs, train, validate_artifact
from .conftest import START, observation

COHORT = {k: observation()[k] for k in (
    "model_generation", "model_artifact_identity", "policy_version", "classifier_version")}


def plan(**kw):
    return CalendarPlan(anchor=START.isoformat(), declared_at=START.isoformat(), **COHORT, **kw)


def resign(row):
    row["observation_fingerprint"] = digest({k: v for k, v in row.items() if k != "observation_fingerprint"})
    return row


def row(i, created, **changes):
    result = observation(i, outcome="LOST" if i % 4 == 0 else "WON")
    result.update(prediction_created_at=created.isoformat(),
                  kickoff_utc=(created+timedelta(hours=1)).isoformat(),
                  settled_at=(created+timedelta(hours=3)).isoformat(), **changes)
    return resign(result)


def populated(p=None):
    p = p or plan()
    result = []
    for name, count in zip(PARTITIONS, (40, 320, 80, 120)):
        start = p.windows()[name][0]
        for j in range(count):
            result.append(row(len(result), start+timedelta(minutes=20*j)))
    return result


NOW = START+timedelta(days=45)


def test_ready_deterministic_grouped_and_detached():
    p, rows = plan(), populated()
    original = deepcopy(rows)
    result = calendar_dataset(rows, p, now=NOW)
    assert result["status"] == "CALENDAR_READY_FOR_OFFLINE_REVIEW", result["blocked_by"]
    assert result == calendar_dataset(list(reversed(rows)), p, now=NOW)
    assert result["counts"] == dict(zip((*PARTITIONS,"PURGED","EXCLUDED"), (40,320,80,120,0,0)))
    assert result["independent_fixture_counts"] == result["counts"]
    assert not result["runtime_enabled"] and not result["promotion_allowed"]
    assert not result["training_invoked"]
    for i, a in enumerate(PARTITIONS):
        for b in PARTITIONS[i+1:]:
            assert not ({r["fixture_id"] for r in result["partitions"][a]} &
                        {r["fixture_id"] for r in result["partitions"][b]})
    result["partitions"]["TRAIN"][0]["frozen_features"]["changed"] = True
    assert rows == original


def test_plan_json_roundtrip_pins_schedule_policy_and_reservations():
    p = plan(reserved_holdout_fixtures=("4","1","4"))
    document = json.loads(json.dumps(p.document()))
    assert CalendarPlan.from_document(document) == p
    assert p.reserved_holdout_fixtures == ("1","4")
    for field in ("windows", "policy_fingerprint", "reserved_holdout_fixtures", "declared_at", "version"):
        changed = deepcopy(document)
        changed[field] = "tampered"
        with pytest.raises((ValueError, TypeError)):
            CalendarPlan.from_document(changed)
    with pytest.raises(ValueError, match="MIDNIGHT"):
        replace(p, anchor=(START+timedelta(hours=1)).isoformat())
    with pytest.raises(ValueError, match="COHORT"):
        replace(p, policy_version="")


@pytest.mark.parametrize("part", PARTITIONS[:-1])
@pytest.mark.parametrize("offset_seconds,kept", [(-1,True),(0,False),(1,False)])
def test_label_cutoff_is_strict_and_retains_full_24_hour_embargo(part, offset_seconds, kept):
    p = plan()
    start, end = p.windows()[part]
    r = row(0, start)
    r["settled_at"] = (end+timedelta(seconds=offset_seconds)).isoformat()
    result = calendar_dataset([resign(r)], p, now=NOW)
    assert bool(result["counts"][part]) is kept
    if not kept:
        assert result["reason_counts"] == {"LABEL_NOT_AVAILABLE_BEFORE_EMBARGO":1}


def test_half_open_windows_gap_and_cross_window_fixture_are_purged():
    p = plan()
    train_end, fit_start = p.windows()["TRAIN"][1], p.windows()["CALIBRATION_FIT"][0]
    rows = [row(0, train_end), row(1, fit_start), row(2, START),
            row(3, fit_start, fixture_id=3)]
    result = calendar_dataset(rows, p, now=NOW)
    assert result["counts"]["CALIBRATION_FIT"] == 1
    assert result["reason_counts"] == {"FIXTURE_CROSSES_WINDOW":2,"OUTSIDE_WINDOWS_OR_EMBARGO_GAP":1}


def test_late_member_purges_whole_fixture_not_only_one_market():
    p = plan()
    rows = [row(0, START),row(1, START+timedelta(minutes=1), fixture_id=1)]
    rows[1]["settled_at"] = p.windows()["TRAIN"][1].isoformat()
    resign(rows[1])
    result = calendar_dataset(rows,p,now=NOW)
    assert result["counts"]["TRAIN"] == 0
    assert result["reason_counts"] == {"LABEL_NOT_AVAILABLE_BEFORE_EMBARGO":2}


def test_reserved_and_consumed_holdout_never_become_training_evidence():
    p = plan(reserved_holdout_fixtures=("1","2"))
    rows = [row(0,START),row(1,p.windows()["SEALED_HOLDOUT"][0]),row(2,START)]
    result = calendar_dataset(rows,p,now=NOW,consumed_holdout_fixtures={"2","3"})
    assert result["counts"]["TRAIN"] == result["counts"]["SEALED_HOLDOUT"] == 0
    assert result["reason_counts"] == {"HOLDOUT_ALREADY_CONSUMED":2,"SEALED_HOLDOUT_RESERVATION":1}
    unconsumed = calendar_dataset(rows,p,now=NOW)
    assert unconsumed["counts"]["SEALED_HOLDOUT"] == 1


@pytest.mark.parametrize("change", [{"source_product":"COMBO_LEG"},{"source_product":"COMBO"},
    {"source_product":None},{"stream":"LIVE"},{"model_generation":"other"},
    {"model_artifact_identity":"other"},{"classifier_version":"other"},{"policy_version":"other"}])
def test_scope_exclusions_do_not_train(change):
    result = calendar_dataset([row(0,START,**change)],plan(),now=NOW)
    assert result["counts"]["EXCLUDED"] == 1 and result["counts"]["TRAIN"] == 0


def test_mixed_generation_fixture_is_excluded_as_a_group():
    rows = [row(0,START),row(1,START,fixture_id=1,model_generation="other")]
    assert calendar_dataset(rows,plan(),now=NOW)["reason_counts"] == {"COHORT_MISMATCH_OR_MIXED_FIXTURE":2}


def test_many_markets_cannot_manufacture_independent_fitting_sample():
    rows = populated()
    for r in rows[40:360]:
        r["fixture_id"] = 10000
        resign(r)
    result = calendar_dataset(rows,plan(),now=NOW)
    assert result["counts"]["CALIBRATION_FIT"] == 320
    assert result["independent_fixture_counts"]["CALIBRATION_FIT"] == 1
    assert "CALIBRATION_FIT_INDEPENDENT_FIXTURES_INSUFFICIENT" in result["blocked_by"]
    assert "CALIBRATION_CLASS_DIVERSITY_INSUFFICIENT" in result["blocked_by"]


def test_immature_and_retrospectively_declared_plans_remain_blocked():
    p = plan()
    early = calendar_dataset(populated(),p,now=START+timedelta(days=13))
    assert "TRAIN_WINDOW_NOT_CLOSED" in early["blocked_by"]
    assert "SEALED_HOLDOUT_WINDOW_NOT_CLOSED" in early["blocked_by"]
    late_plan = replace(p,declared_at=(START+timedelta(days=16)).isoformat())
    late = calendar_dataset(populated(),late_plan,now=NOW)
    assert late["blocked_by"] == ["PLAN_NOT_DECLARED_BEFORE_CALIBRATION"]
    with pytest.raises(ValueError,match="NOT_YET_DECLARED"):
        calendar_dataset([],late_plan,now=START)


@pytest.mark.parametrize("outcome,target,settled",[("VOID",None,START+timedelta(hours=3)),
    ("PENDING",None,None),("WON",1,NOW+timedelta(days=1))])
def test_void_unresolved_or_future_labels_are_unavailable(outcome,target,settled):
    r=row(0,START)
    r.update(outcome=outcome,target=target,settled_at=settled.isoformat() if settled else None)
    result=calendar_dataset([resign(r)],plan(),now=NOW)
    assert result["reason_counts"] == {"NON_BINARY_OR_UNAVAILABLE_LABEL":1}


def test_duplicates_integrity_and_invalid_outcome_fail_closed():
    r=row(0,START)
    with pytest.raises(ValueError,match="DUPLICATE"):
        calendar_dataset([r,r],plan(),now=NOW)
    r["target"]=1
    with pytest.raises(ValueError,match="INTEGRITY"):
        calendar_dataset([r],plan(),now=NOW)
    with pytest.raises(ValueError,match="OUTCOME"):
        calendar_dataset([resign(r)],plan(),now=NOW)
    r=row(0,START)
    r["settled_at"]=(START-timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError,match="BEFORE_PREDICTION"):
        calendar_dataset([resign(r)],plan(),now=NOW)


def test_adding_future_fixtures_and_changing_targets_cannot_move_boundaries():
    p=plan()
    rows=populated()
    before=calendar_dataset(rows,p,now=NOW)
    changed=deepcopy(rows)
    for r in changed:
        r["target"]=1-r["target"]
        r["outcome"]="WON" if r["target"] else "LOST"
        resign(r)
    changed.append(row(9000,NOW+timedelta(days=10)))
    after=calendar_dataset(changed,p,now=NOW+timedelta(days=20))
    assert before["plan"]==after["plan"]
    for name in PARTITIONS:
        assert [r["observation_id"] for r in before["partitions"][name]] == [r["observation_id"] for r in after["partitions"][name]]


def test_clustered_dates_empty_legacy_validation_without_erasing_embargo():
    p=plan()
    # 100 early TRAIN fixtures, 55 on a clustered fitting day, 40 next day.
    rows=[row(i,START+timedelta(hours=i)) for i in range(100)]
    rows += [row(100+i,START+timedelta(days=15,minutes=i)) for i in range(55)]
    rows += [row(155+i,START+timedelta(days=16,minutes=i)) for i in range(40)]
    old=chronological_dataset(rows,"PREMATCH",now=NOW)
    new=calendar_dataset(rows,p,now=NOW)
    assert len(old["partitions"]["VALIDATION"])==0
    assert new["counts"]["CALIBRATION_FIT"]==95
    assert new["status"]=="CALENDAR_DATASET_NOT_READY"
    assert "CALIBRATION_FIT_SAMPLE_INSUFFICIENT" in new["blocked_by"]
    assert new["counts"]["VALIDATION_EVALUATION"]==0


def test_existing_calibration_accepts_ready_calendar_partition_synthetic_only():
    result=calendar_dataset(populated(),plan(),now=NOW)
    training=result["partitions"]["TRAIN"]
    spec=next(s for s in candidate_specs("PREMATCH") if s["family"]=="LOGISTIC" and s["scope"]=="GLOBAL")
    raw=train(spec,training)
    raw["coefficients"]=[0.]*len(raw["coefficients"])
    raw["bias"]=log(.9/.1)
    raw["artifact_fingerprint"]=digest({k:v for k,v in raw.items() if k!="artifact_fingerprint"})
    calibrated=research(raw,training,result["calibration_split"],
        dataset_fingerprint=result["dataset_fingerprint"],now=NOW)
    assert calibrated["status"]=="CALIBRATION_QUALITY_PASS"
    validate_artifact(calibrated["artifact"])
    evidence=calibrated["evidence"]
    assert evidence["holdout_used_for_fitting"] is False
    sealed={r["observation_id"] for r in result["partitions"]["SEALED_HOLDOUT"]}
    assert not sealed & {m[0] for m in evidence["fit_manifest"]+evidence["evaluation_manifest"]}
    assert calibrated==research(raw,training,result["calibration_split"],
        dataset_fingerprint=result["dataset_fingerprint"],now=NOW)
