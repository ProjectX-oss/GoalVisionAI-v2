"""Legacy immutable combo records never count toward independent model evidence."""
from datetime import timedelta
import pytest
from app.adaptive_lab.automl import AutoLearner
from app.adaptive_lab.datasets import chronological_dataset
from app.adaptive_lab.metrics import metrics
from app.adaptive_lab.models import validate_training_rows
from app.adaptive_lab.policy import eligibility
from .conftest import observation, START


def test_legacy_combo_records_are_excluded_from_dataset_metrics_and_eligibility():
    rows = [observation(i, outcome="WON" if i % 2 else "LOST") for i in range(50)]
    combo = {**observation(80), "source_product": "COMBO_LEG"}
    now = START + timedelta(days=300)
    ds = chronological_dataset(rows + [combo], "PREMATCH", now=now)
    assert all(combo["observation_id"] not in [r["observation_id"] for r in part]
               for part in ds["partitions"].values())
    assert eligibility(rows + [combo], "PREMATCH", now)["resolved"] == 50
    assert metrics(rows + [combo], "PREMATCH") == metrics(rows, "PREMATCH")
    with pytest.raises(ValueError, match="COMBO_NOT_LEARNING_OBSERVATION"):
        validate_training_rows(rows + [combo])


def test_non_due_attempt_still_reports_readiness_without_writes(repo):
    before = list(repo.connection.iterdump())
    result = AutoLearner(repo).run("PREMATCH", now=START)
    assert result["research_due"] is False
    assert result["dataset_readiness"]["status"] == "RESEARCH_DATASET_NOT_READY"
    assert result["dataset_readiness"]["split_unavailable"] is True
    assert list(repo.connection.iterdump()) == before
