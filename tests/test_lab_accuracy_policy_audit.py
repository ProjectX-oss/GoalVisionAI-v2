"""User policy: no odds floor; quality and exposure constraints remain independent."""
from copy import deepcopy
from decimal import Decimal
import pytest
from app.lab_combo.service import _accuracy_delivery_review
from app.lab_v2_shadow.publication import prepare_v2_publications, v2_single_message
from app.lab_v2_shadow.publication_policy import review_accuracy_publication
from app.lab_v2_shadow.accuracy_combo import review_accuracy_combo
from tests.test_lab_accuracy_combo import candidates, prepare
from tests.test_lab_accuracy_delivery import accuracy_candidate
from tests.test_lab_v2_shadow import NOW, bind_candidate_evidence
from tests.test_prematch_v2_enablement import ledger


def test_sub_130_singles_and_sub_200_combo_pass_same_quality_checks(ledger):
    rows = candidates()
    for r in rows:
        r["captured_odds"] = r["offered_odds"] = "1.10"
        bind_candidate_evidence(r)
    result = prepare(ledger, rows)
    assert len(result["singles"]) == 3 and len(result["combos"]) == 1
    assert result["minimum_published_decimal_odds"] is None
    for single in result["singles"]:
        assert _accuracy_delivery_review(single, NOW)["eligible"]
        assert "bez koeficienta minimuma" in v2_single_message(single)
    combo = result["combos"][0]
    assert Decimal(combo["combined_odds"]) == Decimal("1.331")
    assert review_accuracy_combo(combo, now=NOW)["eligible"]


def test_claimed_fixture_cannot_publish_a_different_single_market(ledger):
    row = accuracy_candidate()
    original = prepare_v2_publications({"candidate_markets": [row]}, ledger, now=NOW, label_origin=True)["singles"][0]
    ledger.claim_publication("single_prediction", original, {"prediction_id": original["prediction_id"]})
    other = accuracy_candidate("OVER_1_5")
    other["candidate_id"] += "-other"
    result = prepare_v2_publications({"candidate_markets": [other]}, ledger, now=NOW, label_origin=True)
    assert result["singles"] == []


@pytest.mark.parametrize("mutation", ["duplicate", "zero", "one", "unavailable", "zero_weight"])
def test_probability_alone_does_not_override_unusable_signal(mutation):
    row = accuracy_candidate()
    if mutation == "duplicate":
        row["signals"].append(deepcopy(row["signals"][0]))
    if mutation == "zero":
        row["signals"][0]["probability"] = "0E+1"
    if mutation == "one":
        row["signals"][0]["probability"] = "1"
    if mutation == "unavailable":
        row["signals"][0]["availability"] = "STALE"
    if mutation == "zero_weight":
        row["signals"][0]["reliability"] = "0"
    assert not review_accuracy_publication(row, now=NOW)["eligible"]


def test_frozen_legacy_floor_and_preview_are_preserved(ledger):
    value = prepare(ledger)["singles"][0]
    value["single_selection_policy"] = "LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V1"
    value["minimum_published_decimal_odds"] = "1.30"
    assert _accuracy_delivery_review(value, NOW)["eligible"]
    assert "koef. ≥1.30" in v2_single_message(value)
    value["captured_odds"] = "1.10"
    bind_candidate_evidence(value)
    assert not _accuracy_delivery_review(value, NOW)["eligible"]
