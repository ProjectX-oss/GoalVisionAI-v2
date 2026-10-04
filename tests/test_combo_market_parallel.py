"""Parallel current-market COMBO: real arithmetic, offline transport and settlement."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json

import pytest

from app.lab_v2_shadow import combo_market as market, combo_agreement as agreement
from app.lab_v2_shadow.combo_market_sources import Inputs
from app.lab_v2_shadow.combo_agreement_sources import Inputs as DCInputs
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.publication import prepare_v2_publications
from app.lab_v2_shadow.accuracy_combo import review_accuracy_combo, prepare_accuracy_combos
from app.lab_combo.bot_routing import cohort_statistics
from app.lab_combo.service import LabComboService
from app.dixon_coles_research.repository import ResearchStore
from app.dixon_coles_research.contracts import seal
from app.real_match_lab_analysis.fingerprint import fingerprint
from tests.test_dixon_coles_forward import artifact, item, START
from tests.test_lab_v2_shadow import bind_candidate_evidence
from tests.test_prematch_v2_enablement import ledger
from tests.test_combo_bot_routing import routed, send, RoutedTransport, TOKEN
from tests.test_lab_combo_early_loss import Provider, payload


@pytest.fixture(autouse=True)
def active(monkeypatch):
    for flag in (market.FLAG, agreement.FLAG, "GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130",
                 "GOALVISION_LAB_SINGLE_MIN_ODDS_130", "GOALVISION_LAB_SINGLE_MIN_ODDS_150",
                 "GOALVISION_LAB_TODAY_ONLY", "GOALVISION_LAB_EARLY_COMBO_LOSS"):
        monkeypatch.setenv(flag, "1")


def source(index=0, *, odds="1.30", prices=("1.32", "1.34")):
    value = item(index, odds=odds)
    doc = deepcopy(value["capture"]["source_consensus"])
    original = deepcopy(doc["quotes"])
    for bid, price in enumerate(prices, 20):
        for quote in original:
            q = deepcopy(quote)
            q.update(bookmaker_id=bid, bookmaker_name=f"Book {bid}")
            if q["market"] == "UNDER_3_5":
                q["decimal_odds"] = price
            q["raw_implied_probability"] = str(1 / Decimal(q["decimal_odds"]))
            q["provenance_fingerprint"] = quote_hash(q)
            doc["quotes"].append(q)
    doc["retrieved_at_utc"] = START.isoformat()
    return value, doc


def quote_hash(q):
    from datetime import datetime
    return fingerprint(dict(provider="API_FOOTBALL", fixture_id=q["fixture_id"],
        bookmaker_id=q["bookmaker_id"], bookmaker=q["bookmaker_name"], market=q["market"],
        odds=Decimal(q["decimal_odds"]),
        provider_updated=datetime.fromisoformat(q["provider_origin_timestamp_utc"]),
        retrieved_at=datetime.fromisoformat(q["retrieved_at_utc"])))


@pytest.fixture
def sources(tmp_path):
    repo = ShadowEvidenceRepository(tmp_path / "market-shadow.db")
    def make(values=None):
        rows = []
        for value, doc in values if values is not None else [source(i) for i in range(3)]:
            repo.append("market_consensus", f'{doc["fixture_id"]}:{doc["market_family"]}:{fingerprint(doc)}',
                        doc, created_at=START)
            rows.extend(value["candidates"].values())
        return rows, Inputs(repo)
    yield make, repo
    repo.close()


def prepare(ledger, sources, values=None, *, now=START, dc=None):
    rows, inputs = sources[0](values)
    return prepare_v2_publications({"candidate_markets": rows}, ledger, now=now,
        label_origin=True, accuracy_combos=True, combo_inputs=dc, market_combo_inputs=inputs)


def test_real_medians_without_dc_and_exact_floor(ledger, sources):
    result = prepare(ledger, sources)
    combo, = result["combos"]
    assert combo["policy"] == market.POLICY and combo["statistics_cohort"] == market.COHORT
    assert combo["combined_odds"] == str(Decimal("1.30") ** 3)
    assert result["combo_diagnostics"]["prepared_count"] == 0
    assert result["combo_diagnostics"]["parallel_market"]["prepared_count"] == 1
    frozen = combo["legs"][0]["combo_market"]
    assert frozen["bookmaker_count"] == 3
    assert Decimal(frozen["ranking_score"]) == min(map(Decimal, frozen["method_medians"].values()))
    assert frozen["score_is_calibrated_probability"] is False
    assert review_accuracy_combo(combo, now=START)["eligible"]
    assert "COMBO Tirgus tests" in ledger.get("preview", combo["prediction_id"])["message"]


def test_market_rank_can_choose_different_market_without_changing_single(ledger, sources):
    values = [source(i) for i in range(3)]
    c = values[0][0]["candidates"]["OVER_3_5"]
    c["ensemble_probability"] = c["signals"][0]["probability"] = ".80"
    c["edge"] = str(Decimal(".80") - 1 / Decimal(c["captured_odds"]))
    bind_candidate_evidence(c)
    result = prepare(ledger, sources, values)
    assert next(s for s in result["singles"] if s["fixture_id"] == 9000)["market"] == "OVER_3_5"
    assert all(leg["market"] == "UNDER_3_5" for leg in result["combos"][0]["legs"])


def test_two_live_lanes_preserve_dc_and_are_disjoint(ledger, sources, artifact, tmp_path, monkeypatch):
    values = [source(i) for i in range(6)]
    path = tmp_path / "models.db"
    db = ResearchStore(path)
    db.append("model", artifact["fingerprint"], artifact)
    db.close()
    # Only three fixtures belong to the model's league; B needs no DC coverage.
    for value, _ in values[3:]:
        for c in value["candidates"].values():
            c["league_id"] = 999
    rows, inputs = sources[0](values)
    monkeypatch.setenv(market.FLAG, "0")
    baseline = prepare_v2_publications({"candidate_markets": rows}, ledger, now=START,
        label_origin=True, accuracy_combos=True, combo_inputs=DCInputs(sources[1], model_path=path))
    monkeypatch.setenv(market.FLAG, "1")
    both = prepare_v2_publications({"candidate_markets": rows}, ledger, now=START,
        label_origin=True, accuracy_combos=True, combo_inputs=DCInputs(sources[1], model_path=path),
        market_combo_inputs=inputs)
    a, b = both["combos"]
    assert a == baseline["combos"][0] and both["singles"] == baseline["singles"]
    assert a["policy"] == agreement.POLICY and b["policy"] == market.POLICY
    assert len({leg["fixture_id"] for c in (a, b) for leg in c["legs"]}) == 6
    assert len({leg[k] for c in (a, b) for leg in c["legs"] for k in ("home_team_id", "away_team_id")}) == 12


@pytest.mark.parametrize("case", ["floor", "one_book", "duplicate_book_id", "incomplete_selected",
    "stale", "future", "quote_mismatch", "family_mismatch", "tomorrow", "quality", "shared_team", "mode"])
def test_fail_closed(ledger, sources, monkeypatch, case):
    values = [source(i) for i in range(3)]
    value, doc = values[0]
    if case == "floor": values[0] = source(0, odds="1.29999999999999999")
    if case == "one_book": doc["quotes"] = doc["quotes"][:2]
    if case == "duplicate_book_id":
        for q in doc["quotes"][2:4]:
            q["bookmaker_id"] = 8
            q["provenance_fingerprint"] = quote_hash(q)
    if case == "incomplete_selected": doc["quotes"] = [q for q in doc["quotes"] if not (q["bookmaker_id"] == 8 and q["market"] == "OVER_3_5")]
    if case in {"stale", "future"}:
        for q in doc["quotes"][2:]:
            q["retrieved_at_utc"] = (START + timedelta(seconds=1 if case == "future" else -901)).isoformat()
            q["provenance_fingerprint"] = quote_hash(q)
    if case == "quote_mismatch": doc["quotes"][0]["decimal_odds"] = "1.8"
    if case == "family_mismatch": doc["market_family"] = "TOTAL_2_5"
    if case == "tomorrow":
        for c in value["candidates"].values(): c["kickoff_utc"] = (START+timedelta(days=1)).isoformat()
    if case == "quality":
        for c in value["candidates"].values(): c["hard_failures"].append("UNSUPPORTED_MARKET")
    if case == "shared_team":
        for c in value["candidates"].values(): c["home_team_id"] = 3
    if case == "mode": monkeypatch.setenv(market.FLAG, "yes")
    assert not prepare(ledger, sources, values)["combos"]
    assert not ledger.all("claim")


@pytest.mark.parametrize("case", ["score", "median", "book", "quote", "candidate", "aggregate", "cohort", "future"])
def test_rehashed_tampering_blocked_before_send(ledger, sources, routed, monkeypatch, case):
    combo = prepare(ledger, sources)["combos"][0]
    bad = deepcopy(combo)
    e = bad["legs"][0]["combo_market"]
    if case == "score": e["ranking_score"] = ".99"
    if case == "median": e["method_medians"]["POWER"] = ".99"
    if case == "book": e["bookmakers"][0]["probabilities"]["POWER"] = ".99"
    if case == "quote": e["consensus"]["quotes"][0]["decimal_odds"] = "1.8"
    if case == "candidate": bad["legs"][0]["league_id"] = 222
    if case == "aggregate": bad["ranking_score_if_independent"] = ".99"
    if case == "cohort": bad["statistics_cohort"] = "OTHER"
    if case == "future": e["selected_at"] = (START+timedelta(minutes=1)).isoformat()
    e.pop("fingerprint")
    bad["legs"][0]["combo_market"] = seal(e)
    assert not review_accuracy_combo(bad, now=START)["eligible"]
    old_get = ledger.get
    monkeypatch.setattr(ledger, "get", lambda kind, key: bad if kind == "prediction" and key == combo["prediction_id"] else old_get(kind, key))
    transport = RoutedTransport(TOKEN)
    assert not send(ledger, "combo_prediction", combo["prediction_id"], routed[2], transport, now=START)["sent"]
    assert not transport.calls and not ledger.all("claim")


def test_frozen_replay_permutation_one_extra_limit_and_reader_only(ledger, sources):
    values = [source(i) for i in range(9)]
    result = prepare(ledger, sources, values)
    assert len(result["combos"]) == 1
    rows, inputs = sources[0](values)
    replay = prepare_v2_publications({"candidate_markets": list(reversed(rows))}, ledger,
        now=START+timedelta(minutes=1), label_origin=True, accuracy_combos=True, market_combo_inputs=inputs)
    assert replay["combos"] == result["combos"]
    before = sources[1].connection.total_changes
    Inputs(sources[1]).score(rows[0], now=START)
    assert sources[1].connection.total_changes == before


def test_no_duplicate_unknown_claim_and_separate_cohorts(ledger, sources, routed, monkeypatch):
    combo = prepare(ledger, sources)["combos"][0]
    transport = RoutedTransport(TOKEN)
    assert send(ledger, "combo_prediction", combo["prediction_id"], routed[2], transport, now=START)["sent"]
    assert not prepare(ledger, sources)["combos"]
    assert send(ledger, "combo_prediction", combo["prediction_id"], routed[2], transport, now=START)["status"] == "DELIVERY_ALREADY_CLAIMED"
    assert len(transport.calls) == 1
    assert cohort_statistics(ledger, routed[2].route, selection_policy=market.POLICY)["total_published"] == 1
    assert cohort_statistics(ledger, routed[2].route, agreement=False)["total_published"] == 0
    assert cohort_statistics(ledger, routed[2].route, agreement=True)["total_published"] == 0
    assert cohort_statistics(ledger, routed[2].route)["total_published"] == 1


def test_unknown_delivery_is_terminal_and_not_counted_as_confirmed(ledger, sources, routed):
    combo = prepare(ledger, sources)["combos"][0]
    client = RoutedTransport(TOKEN)
    client.fail = True
    assert not send(ledger, "combo_prediction", combo["prediction_id"], routed[2], client, now=START)["sent"]
    assert ledger.get("claim", "combo_prediction:"+combo["prediction_id"])
    assert not prepare(ledger, sources)["combos"]
    client.fail = False
    assert send(ledger, "combo_prediction", combo["prediction_id"], routed[2], client, now=START)["status"] == "DELIVERY_ALREADY_CLAIMED"
    assert len(client.calls) == 1
    assert cohort_statistics(ledger, routed[2].route, selection_policy=market.POLICY)["total_published"] == 0


@pytest.mark.parametrize("case", ["hash", "future_record", "missing"])
def test_source_record_failure_preserves_singles(ledger, sources, case):
    import sqlite3
    from types import SimpleNamespace
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE lab_v2_shadow_evidence(kind,identity,content_fingerprint,document_json,created_at_utc)")
    rows = []
    for value, doc in [source(i, odds="1.60") for i in range(3)]:
        rows.extend(value["candidates"].values())
        if case != "missing":
            connection.execute("INSERT INTO lab_v2_shadow_evidence VALUES(?,?,?,?,?)", (
                "market_consensus", str(doc["fixture_id"])+":test", "invalid" if case == "hash" else fingerprint(doc),
                json.dumps(doc), (START+timedelta(seconds=1) if case == "future_record" else START).isoformat()))
    try:
        result = prepare_v2_publications({"candidate_markets": rows}, ledger, now=START,
            label_origin=True, accuracy_combos=True, market_combo_inputs=Inputs(SimpleNamespace(connection=connection)))
        assert len(result["singles"]) == 3 and not result["combos"]
    finally:
        connection.close()


def test_candidate_capacity_does_not_partially_rank(ledger, sources):
    rows, inputs = sources[0]()
    combos, diagnostic = prepare_accuracy_combos([rows[0]]*601, ledger, now=START,
        label_origin=True, combo_inputs=inputs, market_variant=True)
    assert not combos and diagnostic["reason"] == "COMBO_MARKET_CAPACITY"
    assert not ledger.all("prediction")


def test_top_sixty_is_deterministic_and_reports_omitted_tail(ledger, sources):
    rows, inputs = sources[0]([source(i) for i in range(61)])
    result = prepare_v2_publications({"candidate_markets": rows}, ledger, now=START,
        label_origin=True, accuracy_combos=True, market_combo_inputs=inputs)
    first, diagnostic = result["combos"], result["combo_diagnostics"]["parallel_market"]
    assert len(first) == 1 and diagnostic["eligible_fixture_count"] == 61
    assert diagnostic["rank_tail_omitted"] == 1
    second = prepare_v2_publications({"candidate_markets": list(reversed(rows))}, ledger, now=START,
        label_origin=True, accuracy_combos=True, market_combo_inputs=Inputs(sources[1]))
    assert second["combos"] == first


@pytest.mark.parametrize("photo", [False, True])
def test_early_loss_reply_after_rollback_and_remaining_legs(ledger, sources, routed, monkeypatch, tmp_path, photo):
    from tests.test_settlement_replies import transport
    from app.lab_combo.presentation import ResultImagePaths
    monkeypatch.setenv("GOALVISION_LAB_SETTLEMENT_REPLIES", "1")
    combo = prepare(ledger, sources)["combos"][0]
    client = transport(private=True)
    assert send(ledger, "combo_prediction", combo["prediction_id"], routed[2], client, now=START)["sent"]
    receipt = ledger.get("receipt", "combo_prediction:"+combo["prediction_id"])
    monkeypatch.setenv(market.FLAG, "0")
    later = START+timedelta(hours=2, minutes=35)
    service = LabComboService(ledger, None, clock=lambda: later, early_combo_loss=True)
    asyncio.run(service.check_results(Provider({9000: payload(9000, score=(2, 2)), 9001: payload(9001, "NS"), 9002: payload(9002, "NS")})))
    result = ledger.get("settlement", combo["prediction_id"])
    assert result["status"] == "LOST" and len(result["pending_legs"]) == 2
    preview = ledger.get("settlement_preview", combo["prediction_id"])
    assert preview["statistics"]["selection_cohort"] == market.COHORT and preview["statistics"]["LOST"] == 1
    assert "COMBO Tirgus testa statistika" in preview["message"]
    if photo:
        path = tmp_path/"loss.png"
        path.write_bytes(b"fixture-image")
        service.result_images = ResultImagePaths(path, path, path)
    outcome = asyncio.run(service.publish_experimental("combo_settlement", combo["prediction_id"], routed[2], client))
    assert outcome["sent"] and client.bot.calls[-1][1]["reply_parameters"].message_id == receipt["message_id"]
    final = Provider({9001: payload(9001), 9002: payload(9002)})
    asyncio.run(service.check_results(final))
    assert ledger.get("combo_result_detail", combo["prediction_id"])
    assert ledger.get("settlement", combo["prediction_id"]) == result
    assert len(ledger.all("settlement")) == 1


def test_rollback_blocks_new_market_claim_without_disabling_dc(ledger, sources, routed, monkeypatch):
    combo = prepare(ledger, sources)["combos"][0]
    monkeypatch.setenv(market.FLAG, "0")
    client = RoutedTransport(TOKEN)
    assert send(ledger, "combo_prediction", combo["prediction_id"], routed[2], client, now=START)["status"] == "COMBO_MARKET_SELECTION_DISABLED"
    assert not ledger.all("claim") and not client.calls
    assert market.published_selection_blocker(agreement.POLICY) is None


@pytest.mark.parametrize("reverse", [False, True])
def test_atomic_cross_policy_overlap_blocks_changed_triplet(ledger, sources, reverse):
    b = prepare(ledger, sources)["combos"][0]
    a = deepcopy(b)
    a.update(prediction_id="synthetic-dc", combo_selection_policy=agreement.POLICY)
    a["legs"][1]["fixture_id"] = 12345
    first, second = (a, b) if reverse else (b, a)
    if reverse: ledger.append("prediction", a["prediction_id"], a)
    assert ledger.claim_publication("combo_prediction", first, {"prediction_id": first["prediction_id"]})
    assert not ledger.claim_publication("combo_prediction", second, {"prediction_id": second["prediction_id"]})


def test_budget_failure_discards_partial_market_pool(ledger, sources, monkeypatch):
    rows, inputs = sources[0]()
    original = inputs.score
    def score(c, *, now):
        if c["fixture_id"] == 9002: raise ValueError("COMBO_MARKET_BUDGET_EXHAUSTED")
        return original(c, now=now)
    monkeypatch.setattr(inputs, "score", score)
    result = prepare_v2_publications({"candidate_markets": rows}, ledger, now=START,
        label_origin=True, accuracy_combos=True, market_combo_inputs=inputs)
    assert not result["combos"]
    assert result["combo_diagnostics"]["parallel_market"]["reason"] == "COMBO_MARKET_BUDGET_EXHAUSTED"


def test_compact_operator_output_keeps_second_lane():
    from app.lab_v2_shadow.operator_output import operator_cycle_summary
    out = operator_cycle_summary({"controlled_publication": {"combo_diagnostics": {
        "prepared_count": 1, "total_prepared_count": 2, "parallel_market": {
            "policy": market.POLICY, "reason": "COMBO_READY", "prepared_count": 1,
            "eligible_fixture_count": 80, "rank_tail_omitted": 20, "secret": "not-public"}}}})
    value = out["controlled_publication"]["combo_diagnostics"]
    assert value["total_prepared_count"] == 2 and value["parallel_market"]["prepared_count"] == 1
    assert "not-public" not in json.dumps(out) and len(json.dumps(out)) < 4096


def test_full_cycle_constructs_market_reader_and_uses_combo_bot(tmp_path, monkeypatch, capsys, routed):
    from datetime import datetime
    from pathlib import Path
    from app.lab_v2_shadow import cli, combo_agreement_sources
    from app.lab_combo.repository import ComboRepository
    from tests.test_lab_v2_shadow import _install_controlled_cycle_fakes, _controlled_cycle_arguments
    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    ticks = iter(START+timedelta(seconds=i) for i in range(100))
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(ticks).astimezone(tz)
    class Runner:
        def __init__(self, client, repository, **kwargs):
            self.repository = repository
        async def run(self, **kwargs):
            rows = []
            for value, doc in [source(i) for i in range(3)]:
                self.repository.append("market_consensus", str(doc["fixture_id"])+":test", doc, created_at=START)
                rows.extend(value["candidates"].values())
            return {"candidate_markets": rows, "mode": "LAB_V2_NO_SEND"}
    monkeypatch.setattr(cli, "datetime", Clock)
    monkeypatch.setattr(cli, "LabV2ShadowRunner", Runner)
    monkeypatch.setattr(cli, "LabTelegramTransport", RoutedTransport)
    monkeypatch.setattr(combo_agreement_sources, "MODEL_DB", tmp_path/"no-model.db")
    RoutedTransport.instances = []
    assert cli.main([*_controlled_cycle_arguments(send=True), "--accuracy-combos"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["controlled_publication"]["singles_sent"] == 0
    assert output["controlled_publication"]["combos_sent"] == 1, output["controlled_publication"]
    assert output["controlled_publication"]["combo_diagnostics"]["parallel_market"]["prepared_count"] == 1
    clients = [c for c in RoutedTransport.instances if c.calls]
    assert len(clients) == 1
    assert clients[0].calls[0]["chat_id"] == routed[2].chat_id
    assert "COMBO Tirgus tests" in clients[0].calls[0]["text"]
    store = ComboRepository(Path("var/lab_combo/ledger.db"))
    try:
        assert len(store.all("claim")) == len(store.all("receipt")) == 1
        assert cohort_statistics(store, routed[2].route, selection_policy=market.POLICY)["total_published"] == 1
    finally:
        store.close()
