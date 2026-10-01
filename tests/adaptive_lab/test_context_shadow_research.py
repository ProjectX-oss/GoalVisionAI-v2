from copy import deepcopy
from datetime import timedelta
import json
from math import exp
import pytest
from app.adaptive_lab.contracts import digest
from app.adaptive_lab.shadow_research import xg, goal_distribution, forward_metrics, validate_capture
from app.adaptive_lab.dynamic_strength import capture, update, INITIAL
from .conftest import START


def identity():
    return {"fixture_id":999,"league_id":1,"home_team_id":10,"away_team_id":20,
            "kickoff_utc":(START+timedelta(hours=2)).isoformat(),"captured_at":START.isoformat()}


def xg_context():
    context = {**identity(),"version":"CURRENT_XG_CONTEXT_V1"}
    for side,team,venue,rate in (("home",10,"HOME",2.),("away",20,"AWAY",1.)):
        context[side+"_samples"] = [
            {"fixture_id":i+(100 if side=="home" else 200),"league_id":1,"team_id":team,
             "played_at":(START-timedelta(days=i+1)).isoformat(),
             "available_at":(START-timedelta(hours=1)).isoformat(),"status":"RESOLVED",
             "source_metric":"expected_goals","source_endpoint":"/fixtures/statistics",
             "source_fingerprint":digest([side,i]),"venue":venue,"xg_for":rate,"xg_against":1.5}
            for i in range(3)]
    return context


def results_context():
    context = {**identity(),"version":"CURRENT_RESULTS_CONTEXT_V1","results":[]}
    for i in range(20):
        kickoff = START-timedelta(days=21-i)
        context["results"].append({"fixture_id":i,"league_id":1,"home_team_id":10,"away_team_id":20,
            "kickoff_utc":kickoff.isoformat(),"available_at":(kickoff+timedelta(hours=3)).isoformat(),
            "status":"RESOLVED","source_fingerprint":digest(i),"home_goals":2 if i%3 else 1,"away_goals":1})
    return context


def test_poisson_identities_and_extreme_valid_rates():
    for h,a in ((1.,1.),(.05,8.),(8.,8.)):
        row=goal_distribution(h,a);p=row["probabilities"]
        assert sum(p[k] for k in ("HOME_WIN","DRAW","AWAY_WIN")) == pytest.approx(1.,abs=1e-12)
        assert p["UNDER_1_5"] == pytest.approx(exp(-h-a)*(1+h+a))
        assert p["BTTS_YES"] == pytest.approx((1-exp(-h))*(1-exp(-a)))
        assert row["discarded_tail_mass"] < 1e-10
        for line in (1,2,3):
            assert p[f"OVER_{line}_5"]+p[f"UNDER_{line}_5"] == pytest.approx(1.)
    p=goal_distribution(1,1)["probabilities"]
    assert p["HOME_WIN"] == pytest.approx(p["AWAY_WIN"])


def test_xg_provenance_roundtrip_and_no_publication():
    ctx=xg_context();original=deepcopy(ctx)
    value=xg(ctx,now=START)
    validate_capture(value)
    assert value == json.loads(json.dumps(value)) and ctx==original
    assert value["publication_eligible"] is False and value["learning_observation"] is False
    assert value["output"]["home_goal_rate"] == pytest.approx(3**.5)
    assert value["output"]["probabilities"]["HOME_WIN"] > value["output"]["probabilities"]["AWAY_WIN"]


@pytest.mark.parametrize("mutation,reason",[
    (lambda c:c["home_samples"][0].update(source_metric="provider_goal_bound"),"PROVENANCE"),
    (lambda c:c["home_samples"][0].update(available_at=(START+timedelta(hours=1)).isoformat()),"FUTURE"),
    (lambda c:c["home_samples"].pop(),"INSUFFICIENT"),
    (lambda c:c["home_samples"].append(c["home_samples"][0]),"DUPLICATE"),
    (lambda c:c.update(captured_at=(START-timedelta(days=1)).isoformat()),"STALE"),
    (lambda c:c.update(kickoff_utc=START.isoformat()),"PREMATCH"),
])
def test_xg_blocks_incomplete_unavailable_or_improper_input(mutation,reason):
    context=xg_context();mutation(context)
    with pytest.raises(ValueError,match=reason):xg(context,now=START)


def test_glicko_official_worked_example():
    actual=update({"rating":1500,"rd":200,"volatility":.06},
                  [(1400,30,1),(1550,100,0),(1700,300,0)],tau=.5)
    assert actual["rating"] == pytest.approx(1464.06,abs=.01)
    assert actual["rd"] == pytest.approx(151.52,abs=.01)
    assert actual["volatility"] == pytest.approx(.059996,abs=.000001)
    assert update(INITIAL,[])["rd"] > INITIAL["rd"]


def test_strength_order_invariance_uncertainty_and_draw_probability():
    ctx=results_context()
    value=capture(ctx,now=START);validate_capture(value)
    shuffled=deepcopy(ctx);shuffled["results"].reverse()
    other=capture(shuffled,now=START)
    assert value["output"] == other["output"]
    assert value["output"]["home_state"]["rd"] < 350
    assert 0<value["output"]["probabilities"]["DRAW"]<1
    idle=deepcopy(ctx);idle.update(captured_at=(START+timedelta(days=60)).isoformat(),
                                 kickoff_utc=(START+timedelta(days=60,hours=2)).isoformat())
    later=capture(idle,now=START+timedelta(days=60))
    assert later["output"]["home_state"]["rd"] > value["output"]["home_state"]["rd"]
    assert value["output"]["independence_group"] == "RESULT_HISTORY_MODEL_CONTEXT"


@pytest.mark.parametrize("mutation,reason",[
    (lambda c:c["results"][0].update(available_at=(START+timedelta(hours=1)).isoformat()),"NOT_AVAILABLE"),
    (lambda c:c["results"].append(c["results"][0]),"DUPLICATE"),
    (lambda c:c.update(results=c["results"][:2]),"INSUFFICIENT"),
    (lambda c:c["results"][0].update(league_id=2),"PROVENANCE"),
])
def test_strength_rejects_leakage_duplicate_and_low_samples(mutation,reason):
    ctx=results_context();mutation(ctx)
    with pytest.raises(ValueError,match=reason):capture(ctx,now=START)


def test_forward_deduplicates_and_pairs_exact_frozen_markets():
    refs={"champion":{"probabilities":{"HOME_WIN":.6},"source_fingerprint":"artifact-1","captured_at":START.isoformat()},
          "current_market":{"probabilities":{"HOME_WIN":.5},"source_fingerprint":"current-quote-1","captured_at":START.isoformat()}}
    value=xg(xg_context(),now=START,references=refs)
    other=capture(results_context(),now=START,references={"xg":{"probabilities":value["output"]["probabilities"],
                  "source_fingerprint":value["capture_id"],"captured_at":START.isoformat()},**refs})
    result={"fixture_id":999,"status":"RESOLVED","home_goals":2,"away_goals":1,
            "available_at":(START+timedelta(hours=5)).isoformat(),"source_fingerprint":"resolved-999"}
    report=forward_metrics([value,value,other],[result],now=START+timedelta(days=1))
    assert report["unique_model_fixtures"]==2 and report["pending"]==0
    assert all(row["n"]==1 for row in report["paired_comparisons"])
    assert {r["reference"] for r in report["paired_comparisons"]}=={"champion","xg","current_market"}
    assert all(row["probability_observations"]==1 for row in report["metrics"])
    assert report["promotion_eligible"] is False
    corrupt=deepcopy(value);corrupt["output"]["probabilities"]["HOME_WIN"]=.9
    with pytest.raises(ValueError,match="INTEGRITY"):
        forward_metrics([corrupt],[result],now=START+timedelta(days=1))
    assert forward_metrics([value],[],now=START)["pending"]==1


def test_current_results_adapter_checks_source_fingerprint_and_freshness():
    from app.adaptive_lab.shadow_inputs import current_results_context
    from app.real_match_lab_analysis.fingerprint import fingerprint
    payload=[{"fixture":{"id":1,"date":(START-timedelta(days=1)).isoformat(),"status":{"short":"FT"}},
              "league":{"id":1},"teams":{"home":{"id":10},"away":{"id":20}},
              "score":{"fulltime":{"home":2,"away":1}}}]
    source={"endpoint":"/fixtures(results)","query":{"status":"FT","league":1},
            "retrieved_at":START.isoformat(),"payload":payload,"payload_fingerprint":fingerprint(payload)}
    value=current_results_context(identity(),[source,source],now=START)
    assert len(value["results"])==1 and value["results"][0]["available_at"]==START.isoformat()
    corrupt=deepcopy(source);corrupt["payload"][0]["score"]["fulltime"]["home"]=3
    with pytest.raises(ValueError,match="INTEGRITY"):
        current_results_context(identity(),[corrupt],now=START)
    source["retrieved_at"]=(START-timedelta(days=1)).isoformat()
    with pytest.raises(ValueError,match="UNAVAILABLE"):
        current_results_context(identity(),[source],now=START)


def test_offline_cli_capture_then_readonly_metrics(tmp_path,monkeypatch,capsys):
    import app.adaptive_lab.shadow_cli as cli
    class Clock:
        stamp=START
        @classmethod
        def now(cls,tz):return cls.stamp
    monkeypatch.setattr(cli,"datetime",Clock)
    source=tmp_path/"context.json";journal=tmp_path/"research.db";results=tmp_path/"results.json"
    source.write_text(json.dumps({"context":xg_context()}))
    assert cli.main(["capture","--method","xg","--input",str(source),"--journal",str(journal)])==0
    assert json.loads(capsys.readouterr().out)["publication_eligible"] is False
    before=journal.read_bytes()
    Clock.stamp=START+timedelta(days=1)
    results.write_text(json.dumps([{"fixture_id":999,"status":"RESOLVED","home_goals":2,"away_goals":1,
        "available_at":Clock.stamp.isoformat(),"source_fingerprint":"synthetic-999"}]))
    assert cli.main(["metrics","--journal",str(journal),"--results",str(results)])==0
    assert json.loads(capsys.readouterr().out)["unique_model_fixtures"]==1
    assert journal.read_bytes()==before
