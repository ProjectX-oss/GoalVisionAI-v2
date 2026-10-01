"""Forward incident: API percent zero survives normalization and is rejected."""
from decimal import Decimal
import json
from app.lab_v2_shadow.api_prediction import normalize_api_prediction
from app.lab_v2_shadow.global_evaluation import evaluate_profile
from app.lab_v2_shadow.profiles import policy_for
from .test_prematch_probability_guard import signals


def test_provider_zero_is_not_a_decimal_or_complement_bug():
    source = {"response": [{"predictions": {
        "percent": {"home": "0%", "draw": "50%", "away": "50%"}}}]}
    normalized = normalize_api_prediction(source, fixture_id=1639967)
    p = normalized.probabilities["HOME_WIN"]
    assert normalized.raw_provider_probabilities["HOME_WIN"] == "0%"
    assert p == Decimal(0)
    assert sum(normalized.probabilities.values()) == 1
    wire = json.loads(json.dumps({"p": str(p)}))
    assert Decimal(wire["p"]) == 0
    decision, evidence = evaluate_profile(
        "HOME_WIN", Decimal("15"), signals("HOME_WIN", p),
        policy_for("INTERNATIONAL_SENIOR"), (), fixture_id=1639967)
    assert decision.ensemble_probability == 0
    assert "INVALID_MODEL_PROBABILITY" in decision.rejection_reasons
    assert evidence["invalid_model_probability_evidence"]["fixture_id"] == 1639967
