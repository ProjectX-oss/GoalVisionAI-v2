"""Offline evidence, chronology, sampling and optional integration regressions."""
import asyncio
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

import pytest

from app.adaptive_lab.contracts import digest
from app.adaptive_lab.devig_research import capture, devig, forward_metrics, verify_capture, capture_identity, VERSION
from app.adaptive_lab import devig_integration as integration
from app.adaptive_lab.devig_metrics import operator_summary
from app.lab_v2_shadow.market_consensus import current_market_consensus
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.runner import LabV2ShadowRunner, _plain
from app.real_match_lab_analysis.fingerprint import fingerprint
from .test_devig_research import document
from .conftest import START


def frozen(source=None, **kwargs):
    return capture(source or document(), captured_at=kwargs.pop("captured_at", START),
                   kickoff=START+timedelta(hours=1), **kwargs)


def result(**kwargs):
    return {"fixture_id": 7, "status": "RESOLVED", "home_goals": 1, "away_goals": 0,
            "settled_at": (START+timedelta(hours=3)).isoformat(),
            "source_fingerprint": digest("fictional-result"), **kwargs}


def repin(q):
    q["provenance_fingerprint"] = fingerprint(dict(provider="API_FOOTBALL",
        fixture_id=q["fixture_id"], bookmaker_id=q["bookmaker_id"], bookmaker=q["bookmaker_name"],
        market=q["market"], odds=Decimal(q["decimal_odds"]),
        provider_updated=integration.utc(q["provider_origin_timestamp_utc"]),
        retrieved_at=integration.utc(q["retrieved_at_utc"])))


@pytest.mark.parametrize("price", ["0", "-1", "1", "NaN", "sNaN", "Infinity", "-Infinity", "bad", None, True])
def test_invalid_prices_rejected_without_clamp(price):
    with pytest.raises(ValueError):
        devig({"BTTS_YES":price, "BTTS_NO":"2"})


@pytest.mark.parametrize("change,reason", [
    ("future", "FUTURE_OR_REVERSED_QUOTE"),
    ("retrieval_mismatch", "INCOMPATIBLE_QUOTE_TIMESTAMPS"),
    ("origin_mismatch", "INCOMPATIBLE_QUOTE_TIMESTAMPS"),
    ("fixture", "FIXTURE_MISMATCH"),
    ("duplicate", "DUPLICATE_BOOKMAKER_OUTCOME"),
    ("tamper", "CURRENT_QUOTE_FINGERPRINT_MISMATCH"),
])
def test_quote_chronology_and_identity(change, reason):
    source = document(); q = source["quotes"][0]
    if change == "future":
        q["retrieved_at_utc"] = (START+timedelta(seconds=2)).isoformat(); repin(q)
    if change == "retrieval_mismatch":
        q["provider_origin_timestamp_utc"] = q["retrieved_at_utc"] = (START-timedelta(seconds=1)).isoformat(); repin(q)
    if change == "origin_mismatch":
        q["provider_origin_timestamp_utc"] = (START-timedelta(seconds=1)).isoformat(); repin(q)
    if change == "fixture":
        q["fixture_id"] = 8; repin(q)
    if change == "duplicate":
        source["quotes"].append(deepcopy(q))
    if change == "tamper":
        q["decimal_odds"] = "9"
    c = frozen(source)
    assert c["status"] == "BLOCKED" and c["reason"] == reason
    assert forward_metrics([c], [result()], now=START+timedelta(days=1))["fixture_count"] == 0


def test_incomplete_books_missing_line_and_partial_coverage_visible():
    source = document(); source["quotes"].pop(0)
    c = frozen(source)
    assert c["status"] == "AVAILABLE"
    assert c["bookmakers"][0]["reason"] == "INCOMPLETE_OR_MISMATCHED_MARKET"
    m = forward_metrics([c], [], now=START)
    assert m["counts"]["blocked_book_markets"] == 1 and m["counts"]["pending_book_markets"] == 1
    source["market_family"] = "TOTAL_2_5"
    assert frozen(source)["status"] == "BLOCKED"


def test_stale_postkickoff_and_unavailable_are_distinct():
    assert frozen(captured_at=START+timedelta(hours=1))["reason"] == "POST_KICKOFF_CAPTURE"
    stale = capture(document(), captured_at=START+timedelta(hours=5), kickoff=START+timedelta(hours=6))
    assert stale["reason"] == "STALE_CURRENT_ODDS"
    source=document(); source.update(status="STALE_CURRENT_ODDS",quotes=[])
    assert frozen(source)["reason"] == "STALE_CURRENT_ODDS"


def test_persist_replay_conflict_mutation_protection_and_reproduction(tmp_path):
    c = frozen(model_probabilities={"HOME_WIN":{"probability":".6", "candidate_id":"c7"}})
    repo = ShadowEvidenceRepository(tmp_path/"shadow.db")
    try:
        assert repo.append("devig_research",c["capture_id"],c,created_at=START)
        assert not repo.append("devig_research",c["capture_id"],c,created_at=START)
        with pytest.raises(ValueError, match="CONFLICT"):
            repo.append("devig_research",c["capture_id"],{**c,"selection_effect":"CHANGED"},created_at=START)
        for sql in ["DELETE FROM lab_v2_shadow_evidence", "UPDATE lab_v2_shadow_evidence SET kind='other'"]:
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                repo.connection.execute(sql)
    finally: repo.close()
    assert integration.read_captures(tmp_path/"shadow.db",now=START)==[c]
    verify_capture(c)
    altered=deepcopy(c);altered["bookmakers"][0]["methods"]["POWER"]["probabilities"]["HOME_WIN"]=".99"
    altered["capture_id"]=capture_identity({k:v for k,v in altered.items() if k!="capture_id"})
    with pytest.raises(ValueError,match="REPRODUCTION"):
        verify_capture(altered)


def test_first_capture_never_replaced_by_later_model_or_repeated_cycles():
    a=frozen(model_probabilities={"HOME_WIN":{"probability":".6"}})
    b=frozen(captured_at=START+timedelta(seconds=1),model_probabilities={"HOME_WIN":{"probability":".99"}})
    early=forward_metrics([a], [result()], now=START+timedelta(days=1))
    repeated=forward_metrics([b,a,a], [result(),result()], now=START+timedelta(days=1))
    assert repeated["methods"] == early["methods"]
    assert repeated["fixture_count"]==1 and repeated["resolved_book_market_samples"]==2
    assert repeated["counts"]["duplicate_captures"]==1 and repeated["counts"]["repeat_book_markets"]==2
    assert repeated["result_counts"]["duplicate_results"]==1


def test_paired_comparison_underround_common_cohort_and_model_subset():
    source=document()
    for q in source["quotes"]:
        if q["bookmaker_id"]==2:
            q["decimal_odds"]="3.01";repin(q)
    c=frozen(source,model_probabilities={"HOME_WIN":{"probability":".6"}})
    m=forward_metrics([c], [result()], now=START+timedelta(days=1))
    shin=m["methods"]["SHIN"];power=m["methods"]["POWER"]
    assert shin["book_market_samples"]==1 and power["book_market_samples"]==2
    assert m["common_book_market_samples"]==1
    for method in m["methods"].values():
        assert method["probability_observations"]==method["paired_multiplicative_metrics"]["probability_observations"]
        assert method["paired_model_metrics"]["probability_observations"]==method["model_paired_market_metrics"]["probability_observations"]
        assert method["common_cohort"]["book_market_samples"]==1
    assert power["missing_or_invalid_model_references"]==4
    assert m["promotion_eligible"] is False and m["quality_verdict"]=="NEEDS_MORE_EVIDENCE"


def test_result_availability_precedes_conflict_check_and_combo_is_excluded():
    c=frozen();now=START+timedelta(hours=4)
    future=result(home_goals=0,away_goals=4,settled_at=(now+timedelta(hours=1)).isoformat())
    m=forward_metrics([c],[result(),future,result(source_product="COMBO_LEG")],now=now)
    assert m["fixture_count"]==1 and m["result_counts"]["future_results"]==1
    assert m["result_counts"]["excluded_combo_results"]==1
    with pytest.raises(ValueError,match="CONFLICTING_FORWARD_RESULT"):
        forward_metrics([c],[result(),{**future,"settled_at":now.isoformat()}],now=now)
    assert forward_metrics([c],[result(settled_at=START.isoformat())],now=now)["counts"]["invalid_result_chronology_book_markets"]==2
    assert forward_metrics([c],[result(status="VOID")],now=now)["counts"]["void_book_markets"]==2
    for bad in [True,-1,31,None,"2"]:
        assert forward_metrics([c],[result(home_goals=bad)],now=now)["fixture_count"]==0


def test_policy_market_segments_and_signed_bias():
    c=frozen(policy_context={"single_policy":"V3"})
    m=forward_metrics([c],[result()],now=START+timedelta(days=1))
    assert m["segments"][0]["single_policy"]=="V3" and m["segments"][0]["market_family"]=="1X2"
    assert m["methods"]["MULTIPLICATIVE"]["bias"]["FAVOURITE"]["mean_signed_error"]<0
    assert m["model_learning_observations"]==0


def test_snapshot_read_is_bounded_readonly_and_missing_path_not_created(tmp_path,monkeypatch,repo):
    missing=tmp_path/"absent.db"
    class Ledger:
        def all(self,kind): return []
    assert integration.observed_snapshot(repo,Ledger(),missing,now=START)["status"]=="UNAVAILABLE"
    assert not missing.exists()
    path=tmp_path/"shadow.db";r=ShadowEvidenceRepository(path);c=frozen()
    r.append("devig_research",c["capture_id"],c,created_at=START);r.close()
    before=path.read_bytes()
    monkeypatch.setattr(integration,"MAX_CAPTURE_ROWS",0)
    value=integration.observed_snapshot(repo,Ledger(),path,now=START)
    assert value["reason"]=="RESEARCH_SNAPSHOT_CAPACITY_EXCEEDED" and path.read_bytes()==before


def test_scheduled_summary_is_bounded_and_does_not_mutate():
    full=forward_metrics([frozen()],[result()],now=START+timedelta(days=1))
    full["segments"]*=20000
    before=deepcopy(full);small=operator_summary(full)
    assert len(json.dumps(small).encode())<2048 and small["fixture_count"]==1
    assert full==before and "methods" not in small and "capture_ids" not in small


@pytest.mark.parametrize("mode",["enabled","calculation_failure","persistence_failure"])
def test_real_runner_candidate_api_and_publication_parity(tmp_path,monkeypatch,mode):
    from tests.test_lab_v2_shadow import FakeClient,NOW
    from app.lab_v2_shadow.operator_output import operator_cycle_summary
    snapshots=[]
    for active in (False,True):
        directory=tmp_path/str(active);directory.mkdir();monkeypatch.chdir(directory)
        monkeypatch.setenv(integration.ENVIRONMENT_FLAG,"1" if active else "0")
        monkeypatch.setenv("GOALVISION_LAB_SINGLE_MIN_ODDS_130","1")
        r=ShadowEvidenceRepository(Path("shadow.db"));client=FakeClient()
        if active and mode=="calculation_failure":
            def fail(*args,**kwargs):raise RuntimeError("secret=must-not-appear")
            monkeypatch.setattr(integration,"capture",fail)
        if active and mode=="persistence_failure":
            original=r.append
            def append(kind,*args,**kwargs):
                if kind=="devig_research":raise sqlite3.OperationalError("private-details")
                return original(kind,*args,**kwargs)
            monkeypatch.setattr(r,"append",append)
        runner=LabV2ShadowRunner(client,r,capability_cache_path=Path("var/capabilities.json"),maximum_calls=40)
        try:
            report=asyncio.run(runner.run(now=NOW,publication_requested=True,today_only=True))
            docs=r.all("devig_research")
            assert r.connection.execute("PRAGMA busy_timeout").fetchone()[0]==30000
            if active:
                extra=report.pop("devig_research")
                assert extra["status"]==("CAPTURED" if mode=="enabled" else "UNAVAILABLE")
                assert "secret" not in json.dumps(extra) and "private" not in json.dumps(extra)
                if mode=="enabled":
                    assert len(docs)==5 and any(d["status"]=="AVAILABLE" for d in docs)
                    assert all(d["policy_context"]["single_minimum"]=="1.30" for d in docs)
                    consensus_fps = {fingerprint(d) for d in r.all("market_consensus")}
                    assert all(d["source_consensus_fingerprint"] in consensus_fps for d in docs
                               if d["source_consensus"]["status"] != "CURRENT_QUOTES_UNAVAILABLE")
                    assert integration.read_captures(Path("shadow.db"),now=NOW+timedelta(hours=1))==docs
                else: assert not docs
            else: assert not docs
            snapshots.append((report,client.request_count,runner.calls,operator_cycle_summary(report)))
        finally:r.close()
    assert snapshots[0]==snapshots[1]


def test_raw_duplicate_outcomes_are_not_hidden_by_consensus_dedup(tmp_path):
    from tests.test_lab_v2_shadow import odds_payload,NOW
    payload=odds_payload(fixture_id=7)
    book=payload["response"][0]["bookmakers"][0]
    book["bets"][0]["values"].append(deepcopy(book["bets"][0]["values"][0]))
    families=current_market_consensus(payload,fixture_id=7,retrieved_at=NOW,now=NOW)
    r=ShadowEvidenceRepository(tmp_path/"shadow.db")
    try:
        integration.capture_cycle(r,{7:(payload,NOW,families)},{7:{"kickoff_utc":NOW+timedelta(hours=1)}},
                                  [],clock=NOW,runtime_clock=None,today_only=True)
        assert any(c.get("reason")=="DUPLICATE_PROVIDER_OUTCOME" for c in r.all("devig_research"))
    finally:r.close()


def test_observer_persists_metrics_without_learning_inflation_and_isolates_failure(tmp_path,monkeypatch,repo):
    from app.adaptive_lab.observer import observe
    from .test_lab_product_schedule import Ledger
    path=tmp_path/"shadow.db";r=ShadowEvidenceRepository(path);c=frozen()
    r.append("devig_research",c["capture_id"],c,created_at=START);r.close()
    ledger=Ledger()
    # A canonical result already stored by the normal settlement worker, no new fetch.
    row={"observation_id":"fixture7", "fixture_id":7, "provider_status":"FT",
         "fulltime_home":1,"fulltime_away":0, "retrieved_at_utc":result()["settled_at"],
         "source_fingerprint":digest("fictional-result"),"outcome":"WON"}
    repo.append("canonical_results","fixture7","PREMATCH",row,row["retrieved_at_utc"])
    monkeypatch.setenv(integration.ENVIRONMENT_FLAG,"1")
    full=observe(repo,ledger,now=START+timedelta(days=1),shadow_database=path)
    assert full["DEVIG_RESEARCH"]["fixture_count"]==1
    assert repo.all("observer_runs","PREMATCH")[-1]["DEVIG_RESEARCH"]==full["DEVIG_RESEARCH"]
    saved=ShadowEvidenceRepository(path)
    try:
        metrics,=saved.all("devig_metrics")
        assert metrics["snapshot_fingerprint"]==full["DEVIG_RESEARCH"]["snapshot_fingerprint"]
        assert "methods" in metrics and "methods" not in full["DEVIG_RESEARCH"]
    finally:saved.close()
    assert not repo.all("learning_observations","PREMATCH")
    assert full["LIVE"]=="DISABLED" and full["api_calls"]==full["telegram_sends"]==0
    def fail(*a,**k):raise RuntimeError("secret-token")
    monkeypatch.setattr(integration,"observed_snapshot",fail)
    full=observe(repo,ledger,now=START+timedelta(days=1,seconds=1),shadow_database=path)
    assert full["DEVIG_RESEARCH"]["status"]=="UNAVAILABLE" and "secret-token" not in json.dumps(full)


def test_same_time_conflicting_first_capture_is_not_hash_selected():
    a=frozen(model_probabilities={"HOME_WIN":{"probability":".6"}})
    b=frozen(model_probabilities={"HOME_WIN":{"probability":".8"}})
    with pytest.raises(ValueError,match="AMBIGUOUS_FIRST_FORWARD_CAPTURE"):
        forward_metrics([a,b],[result()],now=START+timedelta(days=1))


def test_source_decimal_spelling_matches_persisted_consensus():
    value={"probability":Decimal("0.5000"), "odds":Decimal("1.3000"), "retrieved":START}
    encoded=json.loads(json.dumps(value,default=integration._json_value,allow_nan=False))
    assert encoded==_plain(value)
    assert fingerprint(encoded)==digest(_plain(value))


def test_core_persistence_errors_still_fail_closed(tmp_path,monkeypatch):
    from tests.test_lab_v2_shadow import FakeClient,NOW
    monkeypatch.chdir(tmp_path);monkeypatch.setenv(integration.ENVIRONMENT_FLAG,"1")
    r=ShadowEvidenceRepository(Path("shadow.db"));original=r.append
    def fail(kind,*args,**kwargs):
        if kind=="market_consensus":raise ValueError("CORE_INTEGRITY_FAILURE")
        return original(kind,*args,**kwargs)
    monkeypatch.setattr(r,"append",fail)
    try:
        runner=LabV2ShadowRunner(FakeClient(),r,capability_cache_path=Path("var/capabilities.json"),maximum_calls=40)
        with pytest.raises(ValueError,match="CORE_INTEGRITY_FAILURE"):
            asyncio.run(runner.run(now=NOW,publication_requested=True,today_only=True))
    finally:r.close()


def test_research_has_no_single_or_combo_preparation_effect(tmp_path,monkeypatch):
    from tests.test_lab_accuracy_combo import candidates,prepare
    from tests.test_lab_v2_shadow import NOW
    from app.lab_combo.repository import ComboRepository
    monkeypatch.setenv("GOALVISION_LAB_SINGLE_MIN_ODDS_130","1")
    monkeypatch.setenv("GOALVISION_LAB_TODAY_ONLY","1")
    monkeypatch.chdir(tmp_path)
    rows=candidates()
    snapshots=[]
    for active in (False,True):
        monkeypatch.setenv(integration.ENVIRONMENT_FLAG,"1" if active else "0")
        ledger=ComboRepository(Path("var/lab_combo")/(str(active)+".db"))
        try:
            snapshots.append(prepare(ledger,deepcopy(rows)))
        finally:ledger.close()
    assert snapshots[0]==snapshots[1]
    assert len(snapshots[0]["singles"])==3 and len(snapshots[0]["combos"])==1


def test_large_metrics_separate_from_health_and_idempotent(tmp_path):
    path=tmp_path/"shadow.db";r=ShadowEvidenceRepository(path);r.close()
    cutoff=START+timedelta(days=1)
    full=forward_metrics([frozen()],[result()],now=cutoff)
    full["segments"]*=500
    full["snapshot_fingerprint"]=digest({k:v for k,v in full.items() if k!="snapshot_fingerprint"})
    assert len(json.dumps(full))>131072
    integration.persist_metrics(path,full,now=cutoff)
    integration.persist_metrics(path,full,now=cutoff)
    r=ShadowEvidenceRepository(path)
    try:
        assert r.all("devig_metrics")==[full]
        assert len(json.dumps({"DEVIG_RESEARCH":operator_summary(full)}))<2048
        with pytest.raises(sqlite3.IntegrityError):
            r.connection.execute("DELETE FROM lab_v2_shadow_evidence WHERE kind='devig_metrics'")
    finally:r.close()
    assert not integration.read_captures(path,now=cutoff)


def test_metrics_write_failure_does_not_break_core_observer(tmp_path,monkeypatch,repo):
    from app.adaptive_lab.observer import observe
    from .test_lab_product_schedule import Ledger
    path=tmp_path/"shadow.db";r=ShadowEvidenceRepository(path);c=frozen()
    r.append("devig_research",c["capture_id"],c,created_at=START);r.close()
    monkeypatch.setenv(integration.ENVIRONMENT_FLAG,"1")
    def fail(*a,**k):raise sqlite3.OperationalError("private-path")
    monkeypatch.setattr(integration,"persist_metrics",fail)
    value=observe(repo,Ledger(),now=START+timedelta(days=1),shadow_database=path)
    assert value["DEVIG_RESEARCH"]["status"]=="UNAVAILABLE"
    assert "private-path" not in json.dumps(value)
    assert value["api_calls"]==value["telegram_sends"]==0
    assert repo.all("observer_runs","PREMATCH")


def test_capture_cycle_first_valid_sampling_does_not_grow_with_timer_ticks(tmp_path):
    from tests.test_lab_v2_shadow import odds_payload, NOW
    repo = ShadowEvidenceRepository(tmp_path/"shadow.db")
    payload = odds_payload(fixture_id=7)
    families = current_market_consensus(payload,fixture_id=7,retrieved_at=NOW,now=NOW)
    fixtures = {7:{"kickoff_utc":NOW+timedelta(hours=1)}}
    def run(source, at):
        return integration.capture_cycle(repo,{7:(payload,NOW,source)},fixtures,[],
            clock=at,runtime_clock=None,today_only=True)
    try:
        initial = run({}, NOW)
        assert initial["counts"]["persisted"] == 5
        first_valid = run(families,NOW+timedelta(seconds=1))
        assert first_valid["counts"]["persisted"] >= 1
        saved = repo.all("devig_research")
        for second in range(2,20):
            repeated=run(families,NOW+timedelta(seconds=second))
            assert repeated["counts"]["already_captured"] == 5
        assert repo.all("devig_research") == saved
        assert len(saved) <= 10
        plan=repo.connection.execute("EXPLAIN QUERY PLAN SELECT identity FROM lab_v2_shadow_evidence "
            "WHERE kind='devig_research' AND identity>=? AND identity<?",
            ("devig-v2:7:1X2:","devig-v2:7:1X2:~")).fetchall()
        assert any("INDEX" in str(tuple(row)) for row in plan)
    finally:repo.close()


def test_first_valid_sampling_admits_new_book_and_isolates_fixture(tmp_path):
    repo=ShadowEvidenceRepository(tmp_path/"shadow.db")
    first=frozen()
    try:
        assert integration._needs_capture(repo.connection,first)
        repo.append("devig_research",first["capture_id"],first,created_at=START)
        later=frozen(captured_at=START+timedelta(seconds=1))
        assert not integration._needs_capture(repo.connection,later)
        source=document()
        for q in source["quotes"]:
            if q["bookmaker_id"] == 2:
                q["bookmaker_id"]=3;q["bookmaker_name"]="Third";repin(q)
        added=frozen(source,captured_at=START+timedelta(seconds=1))
        assert integration._needs_capture(repo.connection,added)
        repo.append("devig_research",added["capture_id"],added,created_at=START+timedelta(seconds=1))
        assert not integration._needs_capture(repo.connection,added)
        source=document();source["fixture_id"]=70
        for q in source["quotes"]:q["fixture_id"]=70;repin(q)
        assert integration._needs_capture(repo.connection,frozen(source))
        conflict=frozen(model_probabilities={"HOME_WIN":{"probability":".9"}})
        with pytest.raises(ValueError,match="RESEARCH_BACKDATED"):
            integration._needs_capture(repo.connection,conflict)
        conflict=capture(added["source_consensus"], captured_at=START+timedelta(seconds=1),
            kickoff=START+timedelta(hours=1),model_probabilities={"HOME_WIN":{"probability":".9"}})
        with pytest.raises(ValueError,match="AMBIGUOUS_FIRST"):
            integration._needs_capture(repo.connection,conflict)
        metrics=forward_metrics([first,added],[result()],now=START+timedelta(days=1))
        assert metrics["resolved_book_market_samples"]==3 and metrics["fixture_count"]==1
    finally:repo.close()
