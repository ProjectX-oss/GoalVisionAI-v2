"""Opt-in offline PREMATCH calendar research; no runtime wiring or model fitting.

One immutable schedule: 14 TRAIN days, then 7 days each for calibration fitting,
later evaluation and sealed holdout, separated by 24-hour embargo gaps. Windows
never move to satisfy sample counts. This candidate is not a promotion contract.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from .contracts import digest, utc
from .policy import POLICY

VERSION = "PREMATCH_CALENDAR_RESEARCH_V1"
WINDOW_DAYS = (("TRAIN", 14), ("CALIBRATION_FIT", 7),
               ("VALIDATION_EVALUATION", 7), ("SEALED_HOLDOUT", 7))
COHORT_KEYS = ("model_generation", "model_artifact_identity", "policy_version", "classifier_version")
PARTITIONS = tuple(name for name, _ in WINDOW_DAYS)


def _fixture(value: Any) -> str:
    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
        raise ValueError("CALENDAR_FIXTURE_ID_INVALID")
    return str(int(value))


@dataclass(frozen=True)
class CalendarPlan:
    """Persist once before calibration starts; sealed fixtures cannot become TRAIN.

    Anchor is an explicit UTC midnight, never inferred from outcomes or density.
    Declaration after calibration starts is supported only as a blocked audit.
    """
    anchor: str
    declared_at: str
    model_generation: str
    model_artifact_identity: str
    policy_version: str
    classifier_version: str
    reserved_holdout_fixtures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        anchor, declared = utc(self.anchor), utc(self.declared_at)
        if any((anchor.hour, anchor.minute, anchor.second, anchor.microsecond)):
            raise ValueError("CALENDAR_UTC_MIDNIGHT_REQUIRED")
        if any(not isinstance(getattr(self, k), str) or not getattr(self, k).strip()
               for k in COHORT_KEYS):
            raise ValueError("CALENDAR_COHORT_REQUIRED")
        if len(self.reserved_holdout_fixtures) > POLICY.training_rows_limit:
            raise ValueError("CALENDAR_RESERVATION_BOUND")
        reserved = tuple(sorted({_fixture(f) for f in self.reserved_holdout_fixtures}))
        object.__setattr__(self, "anchor", anchor.isoformat())
        object.__setattr__(self, "declared_at", declared.isoformat())
        object.__setattr__(self, "reserved_holdout_fixtures", reserved)

    def windows(self) -> dict[str, tuple[datetime, datetime]]:
        start = utc(self.anchor)
        result = {}
        for name, days in WINDOW_DAYS:
            end = start + timedelta(days=days)
            result[name] = (start, end)
            start = end + timedelta(hours=POLICY.embargo_hours)
        return result

    def document(self) -> dict:
        """JSON-safe, integrity-bound schedule, cohort, reservations and policy."""
        material = {**asdict(self), "reserved_holdout_fixtures": list(self.reserved_holdout_fixtures),
                    "version": VERSION, "policy_fingerprint": POLICY.fingerprint,
                    "windows": {k: [a.isoformat(), b.isoformat()]
                                for k, (a, b) in self.windows().items()}}
        return {**material, "plan_fingerprint": digest(material)}

    @classmethod
    def from_document(cls, document: dict) -> CalendarPlan:
        """Reject edited schedules or policy changes; never silently rebase a plan."""
        try:
            plan = cls(**{key: document[key] for key in cls.__dataclass_fields__})
            if plan.document() != document:
                raise ValueError("CALENDAR_PLAN_INTEGRITY")
            return plan
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("CALENDAR_PLAN_INVALID") from exc


def _validate_rows(rows: list[dict]) -> list[dict]:
    if len(rows) > POLICY.training_rows_limit:
        raise ValueError("CALENDAR_DATASET_BOUND")
    seen = set()
    for row in rows:
        oid = row.get("observation_id")
        if not isinstance(oid, str) or not oid or oid in seen:
            raise ValueError("CALENDAR_DUPLICATE_OR_INVALID_OBSERVATION")
        seen.add(oid)
        if digest({k: v for k, v in row.items() if k != "observation_fingerprint"}) != row.get("observation_fingerprint"):
            raise ValueError("CALENDAR_OBSERVATION_INTEGRITY")
        _fixture(row["fixture_id"])
        created = utc(row["prediction_created_at"])
        settled = utc(row["settled_at"]) if row.get("settled_at") else None
        if settled is not None and settled < created:
            raise ValueError("CALENDAR_SETTLEMENT_BEFORE_PREDICTION")
        target, outcome = row.get("target"), row.get("outcome")
        expected = {"WON": 1, "LOST": 0, "VOID": None, "PENDING": None}
        if outcome not in expected or isinstance(target, bool) or target != expected[outcome]:
            raise ValueError("CALENDAR_OUTCOME_INVALID")
        if outcome != "PENDING" and settled is None:
            raise ValueError("CALENDAR_SETTLEMENT_REQUIRED")
    return sorted(rows, key=lambda r: (utc(r["prediction_created_at"]), r["observation_id"]))


def calendar_dataset(rows: list[dict], plan: CalendarPlan, *, now: datetime,
                     consumed_holdout_fixtures: set[str] | None = None) -> dict:
    """Pure candidate allocation with whole-fixture purging and explicit readiness.

    Consumed holdout fixture identities must come from the caller's immutable audit.
    The result is detached from input rows. No fitting, persistence or promotion is
    performed, even when counts satisfy this experimental readiness contract.
    """
    rows = _validate_rows(rows)
    now = utc(now)
    if utc(plan.declared_at) > now:
        raise ValueError("CALENDAR_PLAN_NOT_YET_DECLARED")
    consumed = {_fixture(f) for f in (consumed_holdout_fixtures or set())}
    reserved = set(plan.reserved_holdout_fixtures)
    windows = plan.windows()
    parts: dict[str, list[dict]] = {k: [] for k in (*PARTITIONS, "PURGED", "EXCLUDED")}
    groups: dict[str, list[dict]] = defaultdict(list)
    reasons: dict[str, str] = {}

    def assign(group: list[dict], partition: str, reason: str | None = None) -> None:
        parts[partition].extend(group)
        if reason:
            reasons.update({r["observation_id"]: reason for r in group})

    for row in rows:
        if row.get("stream") != "PREMATCH" or row.get("source_product") not in {"SINGLE", "SHADOW"}:
            assign([row], "EXCLUDED", "SOURCE_NOT_INDEPENDENT_PREMATCH")
        else:
            groups[_fixture(row["fixture_id"])].append(row)

    for fixture, group in sorted(groups.items()):
        if any(any(r.get(k) != getattr(plan, k) for k in COHORT_KEYS) for r in group):
            assign(group, "EXCLUDED", "COHORT_MISMATCH_OR_MIXED_FIXTURE")
            continue
        if fixture in consumed:
            assign(group, "PURGED", "HOLDOUT_ALREADY_CONSUMED")
            continue
        allocations = {next((name for name, (start, end) in windows.items()
                             if start <= utc(r["prediction_created_at"]) < end), None) for r in group}
        if len(allocations) != 1:
            assign(group, "PURGED", "FIXTURE_CROSSES_WINDOW")
            continue
        name = next(iter(allocations))
        if name is None:
            assign(group, "PURGED", "OUTSIDE_WINDOWS_OR_EMBARGO_GAP")
            continue
        if fixture in reserved and name != "SEALED_HOLDOUT":
            assign(group, "PURGED", "SEALED_HOLDOUT_RESERVATION")
            continue
        if any(utc(r["prediction_created_at"]) > now for r in group):
            assign(group, "PURGED", "PREDICTION_NOT_AVAILABLE")
            continue
        if any(r["target"] is None or utc(r["settled_at"]) > now for r in group):
            assign(group, "PURGED", "NON_BINARY_OR_UNAVAILABLE_LABEL")
            continue
        index = PARTITIONS.index(name)
        if index < len(PARTITIONS) - 1:
            next_start = windows[PARTITIONS[index + 1]][0]
            cutoff = next_start - timedelta(hours=POLICY.embargo_hours)
            if any(utc(r["settled_at"]) >= cutoff for r in group):
                assign(group, "PURGED", "LABEL_NOT_AVAILABLE_BEFORE_EMBARGO")
                continue
        assign(group, name)

    for group in parts.values():
        group.sort(key=lambda r: (utc(r["prediction_created_at"]), r["observation_id"]))
    counts = {k: len(v) for k, v in parts.items()}
    fixtures = {k: len({_fixture(r["fixture_id"]) for r in v}) for k, v in parts.items()}
    blocked = []
    minimums = {"TRAIN": 1, "CALIBRATION_FIT": POLICY.calibration_min,
                "VALIDATION_EVALUATION": POLICY.subgroup_min, "SEALED_HOLDOUT": POLICY.holdout_min}
    for name, minimum in minimums.items():
        if counts[name] < minimum:
            blocked.append(name + "_SAMPLE_INSUFFICIENT")
        # Market rows from one fixture cannot manufacture an independent sample.
        if fixtures[name] < minimum:
            blocked.append(name + "_INDEPENDENT_FIXTURES_INSUFFICIENT")
        if now < windows[name][1]:
            blocked.append(name + "_WINDOW_NOT_CLOSED")
    if {r["target"] for r in parts["TRAIN"]} != {0, 1}:
        blocked.append("TRAIN_CLASS_DIVERSITY_REQUIRED")
    # Count class diversity by distinct fixture, not correlated market rows.
    if any(len({_fixture(r["fixture_id"]) for r in parts["CALIBRATION_FIT"] if r["target"] == y}) < 10
           for y in (0, 1)):
        blocked.append("CALIBRATION_CLASS_DIVERSITY_INSUFFICIENT")
    if utc(plan.declared_at) >= windows["CALIBRATION_FIT"][0]:
        blocked.append("PLAN_NOT_DECLARED_BEFORE_CALIBRATION")
    blocked.sort()
    assignments = {k: [[r["observation_id"], r["observation_fingerprint"]] for r in v] for k, v in parts.items()}
    material = {"version": VERSION, "plan": plan.document(), "as_of": now.isoformat(),
                "consumed_holdout_fixtures": sorted(consumed), "assignments": assignments,
                "purge_reasons": reasons}
    split_material = {"plan_fingerprint": plan.document()["plan_fingerprint"],
                      "assignments": {k: assignments[k] for k in ("CALIBRATION_FIT", "VALIDATION_EVALUATION")}}
    calibration = {"status": "CALIBRATION_DATASET_NOT_READY" if blocked else "CALIBRATION_DATASET_READY",
                   "blocked_by": blocked, "fingerprint": digest(split_material),
                   "partitions": {"CALIBRATION_FIT": parts["CALIBRATION_FIT"],
                                  "VALIDATION_EVALUATION": parts["VALIDATION_EVALUATION"],
                                  "CALIBRATION_PURGED": []}}
    return deepcopy({**material, "dataset_fingerprint": digest(material), "partitions": parts,
                     "counts": counts, "independent_fixture_counts": fixtures,
                     "minimum_observations_and_fixtures": minimums,
                     "reason_counts": dict(sorted(Counter(reasons.values()).items())),
                     "blocked_by": blocked,
                     "status": "CALENDAR_DATASET_NOT_READY" if blocked else "CALENDAR_READY_FOR_OFFLINE_REVIEW",
                     "calibration_split": calibration, "runtime_enabled": False,
                     "training_invoked": False, "promotion_allowed": False})
