"""Regression for differently ordered Decimal products at COMBO publication."""
from copy import deepcopy
from decimal import Decimal
from itertools import permutations

import pytest
from app.lab_v2_shadow import combo_market as market, combo_agreement as agreement
from app.lab_v2_shadow.accuracy_combo import review_accuracy_combo
from app.lab_v2_shadow.publication import prepare_v2_publications
from tests.test_combo_market_parallel import active, sources, source, prepare, ledger, START

SCORES = (
    "0.6402877697841726618705035970",
    "0.6343283582089552238805970150",
    "0.6666666666666666666666666669",
)

@pytest.mark.parametrize("market_variant", [False, True])
@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_persisted_aggregate_reproduces_in_frozen_leg_order(ledger, sources, market_variant, order):
    rows, _ = sources[0]()
    by_fixture = {9000+i: SCORES[i] for i in range(3)}
    class Scores:
        def score(self, candidate, *, now):
            value = {"ranking_score": by_fixture[candidate["fixture_id"]], "consensus": {}}
            if not market_variant:
                value["artifact"] = {"fingerprint": "synthetic-model-for-order-regression"}
            return value
    candidates = [c for i in order for c in rows if c["fixture_id"] == 9000+i]
    def prepare_rows(rows):
        result = prepare_v2_publications({"candidate_markets": rows}, ledger,
            now=START, label_origin=True, accuracy_combos=True,
            combo_inputs=None if market_variant else Scores(),
            market_combo_inputs=Scores() if market_variant else None)
        return result["combos"]
    combos = prepare_rows(candidates)
    combo, = combos
    key = "combo_market" if market_variant else "combo_agreement"
    expected = Decimal(1)
    for leg in combo["legs"]:
        expected *= Decimal(leg[key]["ranking_score"])
    assert {leg["fixture_id"] for leg in combo["legs"]} == {9000, 9001, 9002}
    assert combo["ranking_score_if_independent"] == str(expected)
    persisted = ledger.get("prediction", combo["prediction_id"])
    assert persisted == combo
    again = prepare_rows(list(reversed(candidates)))
    assert again == combos

def test_distinct_current_market_scores_reproduce_and_tampering_still_blocks(ledger, sources):
    values = [source(0, prices=("1.37", "1.42")),
              source(1, prices=("1.40", "1.44")),
              source(2, prices=("1.34", "1.36"))]
    combo, = prepare(ledger, sources, values)["combos"]
    assert len({leg["combo_market"]["ranking_score"] for leg in combo["legs"]}) == 3
    assert review_accuracy_combo(combo, now=START)["eligible"]
    bad = deepcopy(combo)
    bad["ranking_score_if_independent"] = str(Decimal(combo["ranking_score_if_independent"])+Decimal("1e-28"))
    assert not review_accuracy_combo(bad, now=START)["eligible"]
