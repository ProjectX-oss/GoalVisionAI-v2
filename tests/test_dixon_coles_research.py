"""Controlled fixtures only; no predictive-quality claims or external calls."""
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from math import exp,fsum
import random
import sqlite3
import pytest
from app.dixon_coles_research import model
from app.dixon_coles_research.contracts import load_plan,utc,normalize_results,seal,verify
from app.dixon_coles_research.repository import ResearchStore
from app.dixon_coles_research.service import forecast,intake
from app.dixon_coles_research.metrics import evaluate,COMPARATORS
from app.adaptive_lab.devig_research import capture
from app.lab_v2_shadow.market_consensus import current_market_consensus
from app.lab_v2_shadow.runner import _plain
from app.real_match_lab_analysis.fingerprint import fingerprint

PLAN=load_plan()
START=utc(PLAN["declared_at"])+timedelta(minutes=1)

def history():
    rng=random.Random(74023); rows=[]
    def poisson(rate):
        x=0;p=1.0
        while p>exp(-rate): x+=1;p*=rng.random()
        return x-1
    for i in range(120):
        home=i%6+1; away=(home+(i//6)%5)%6+1
        if away==home: away=home%6+1
        kickoff=utc(PLAN["train_end"])-timedelta(days=121-i)
        rows.append({"fixture_id":10000+i,"league_id":71,"home_team_id":home,"away_team_id":away,
                     "home_goals":poisson(1.55),"away_goals":poisson(1.05),
                     "kickoff_utc":kickoff.isoformat(),"observed_at_utc":(kickoff+timedelta(hours=3)).isoformat(),
                     "neutral":False,"status":"FT","source_fingerprint":f"fictional-{i}"})
    return rows

@pytest.fixture(scope="module")
def artifact():
    return model.fit(history(),league_id=71,as_of=START,plan=PLAN)

def item():
    kickoff=START+timedelta(hours=1)
    payload={"response":[{"fixture":{"id":9000},"update":START.isoformat(),
             "bookmakers":[{"id":i,"name":str(i),"bets":[{"name":"Match Winner","values":[
                 {"value":"Home","odd":"2"},{"value":"Draw","odd":"3.5"},{"value":"Away","odd":"4"}]}]}
                          for i in (2,1)]}]}
    consensus=current_market_consensus(payload,fixture_id=9000,retrieved_at=START,now=START)["1X2"]
    source={**_plain(asdict(consensus)),"source":"API_FOOTBALL_CURRENT_ODDS","historical_bookmaker_odds_used":False}
    candidates={}
    for market,p in zip(("HOME_WIN","DRAW","AWAY_WIN"),(".55",".25",".20")):
        candidates[market]={"fixture_id":9000,"candidate_id":"fictional-"+market,
            "league_id":71,"season":2026,"home_team_id":1,"away_team_id":2,"market":market,
            "competition_profile":"SENIOR_MEN","kickoff_utc":kickoff.isoformat(),
            "ensemble_probability":p,"flags":[],
            "quote_provenance_fingerprint":next(q["provenance_fingerprint"] for q in source["quotes"] if q["market"]==market)}
    refs={m:{"probability":c["ensemble_probability"],"candidate_id":c["candidate_id"],
             "candidate_fingerprint":fingerprint(c)} for m,c in candidates.items()}
    cap=capture(source,captured_at=START,kickoff=kickoff,model_probabilities=refs,policy_context={"single_minimum":"1.50"})
    return {"capture":cap,"candidates":candidates,"training_results":history()}

def result(**changes):
    return {"fixture_id":9000,"status":"RESOLVED","home_goals":1,"away_goals":0,
            "settled_at":(START+timedelta(hours=3)).isoformat(),"source_fingerprint":"fictional-terminal",
            "source_product":"SINGLE",**changes}

@pytest.mark.parametrize("h,a,expected",[(0,0,1.18),(0,1,.85),(1,0,.88),(1,1,1.1),(2,1,1)])
def test_four_cell_formula(h,a,expected):
    assert model.correction(h,a,1.5,1.2,-.1)==pytest.approx(expected)

@pytest.mark.parametrize("lam,mu,rho",[(.2,.3,0),(1.5,1.2,-.1),(1.5,1.2,.1),(8,8,.01),(8,.2,-.05)])
def test_grid_mass_marginal_markets_and_monotonicity(lam,mu,rho):
    output=model.markets(lam,mu,rho); p=output["probabilities"]
    assert sum(p[k] for k in ("HOME_WIN","DRAW","AWAY_WIN"))==pytest.approx(1,abs=2e-12)
    assert p["BTTS_YES"]+p["BTTS_NO"]==1
    assert p["OVER_1_5"]>=p["OVER_2_5"]>=p["OVER_3_5"]
    for i in (1,2,3): assert p[f"UNDER_{i}_5"]+p[f"OVER_{i}_5"]==1
    assert output["omitted_mass"]<=2e-12

def test_correction_moves_only_low_scores_preserves_total_25_and_marginals():
    independent=model.markets(1.5,1.2,0)["probabilities"]
    negative=model.markets(1.5,1.2,-.1)["probabilities"]
    assert negative["DRAW"]>independent["DRAW"]
    assert negative["BTTS_YES"]>independent["BTTS_YES"]
    assert negative["OVER_2_5"]==pytest.approx(independent["OVER_2_5"],abs=1e-12)
    assert independent["BTTS_YES"]==pytest.approx((1-exp(-1.5))*(1-exp(-1.2)))
    for h in range(4):
        total=fsum(exp(-1.2)*1.2**a/__import__("math").factorial(a)*model.correction(h,a,1.5,1.2,-.1) for a in range(25))
        assert total==pytest.approx(1,abs=1e-12)

@pytest.mark.parametrize("rates",[(0,1,0),(float("nan"),1,0),(1,float("inf"),0),(8,8,.1),(8,8,-.2),(1,1,True)])
def test_invalid_rates_or_negative_low_cell_rejected(rates):
    with pytest.raises(ValueError): model.markets(*rates)

@pytest.mark.parametrize("neutral",[False,True])
def test_analytic_gradient_against_central_difference(neutral):
    n=3; theta=[.1,.15,.02,-.03,.01,.04,-.03,-.01,-.2]
    rows=[(h,a,x,y,neutral,1.0) for h,a in ((0,1),(1,2),(2,0))
          for x,y in ((0,0),(0,1),(1,0),(1,1),(3,2))]
    value,g=model._objective(theta,rows,n)
    for i in range(len(theta)):
        plus=theta[:];minus=theta[:];plus[i]+=1e-6;minus[i]-=1e-6
        numerical=(model._objective(plus,rows,n)[0]-model._objective(minus,rows,n)[0])/2e-6
        assert g[i]==pytest.approx(numerical,abs=2e-8)

def test_fit_converges_and_is_order_invariant(artifact):
    other=model.fit(list(reversed(history())),league_id=71,as_of=START,plan=PLAN)
    assert other==artifact
    assert artifact["fit"]["gradient_inf"]<=model.POLICY["gradient_tolerance"]
    assert artifact["fit"]["objective"]<artifact["fit"]["initial_objective"]
    assert abs(sum(artifact["parameters"]["attack"].values()))<1e-12
    assert abs(sum(artifact["parameters"]["defense"].values()))<1e-12

def test_neutral_venue_and_unseen_team(artifact):
    args=dict(home_team_id=1,away_team_id=2,league_id=71,as_of=START,kickoff=START+timedelta(hours=1),plan=PLAN)
    home=model.predict(artifact,neutral=False,**args)
    neutral=model.predict(artifact,neutral=True,**args)
    assert home["dixon_coles"]["home_goal_rate"]/neutral["dixon_coles"]["home_goal_rate"]==pytest.approx(exp(artifact["parameters"]["home_advantage"]))
    assert home["dixon_coles"]["away_goal_rate"]==neutral["dixon_coles"]["away_goal_rate"]
    args["home_team_id"]=999
    with pytest.raises(ValueError,match="INSUFFICIENT_TARGET"): model.predict(artifact,neutral=False,**args)

def test_sparse_data_and_nonconvergence_do_not_emit_models(monkeypatch):
    with pytest.raises(ValueError,match="INSUFFICIENT_LEAGUE"):
        model.fit(history()[:5],league_id=71,as_of=START,plan=PLAN)
    def failed(*a,**k): raise ValueError("FIT_DID_NOT_CONVERGE")
    monkeypatch.setattr(model,"_optimize",failed)
    with pytest.raises(ValueError,match="FIT_DID_NOT"):
        model.fit(history(),league_id=71,as_of=START,plan=PLAN)

def test_normalization_time_reserved_duplicate_conflict_and_input_immutability():
    rows=history(); before=deepcopy(rows)
    reserved=rows[0]["fixture_id"]
    future=deepcopy(rows[1]);future["observed_at_utc"]=(START+timedelta(seconds=1)).isoformat()
    rows[1]=future
    rows.append(deepcopy(rows[2]))
    recent=deepcopy(rows[3]);recent["fixture_id"]=99999;recent["kickoff_utc"]=PLAN["train_end"];rows.append(recent)
    normalized,counts=normalize_results(rows,league_id=71,as_of=START,plan=PLAN,additional_reserved=frozenset({reserved}))
    assert counts=={"reserved_holdout":1,"result_not_known_as_of_input":1,"duplicate_result":1,"outside_frozen_training_window":1}
    assert len(normalized)==118
    assert before==history()
    rows[-1]=deepcopy(rows[2]);rows[-1]["home_goals"]+=1
    with pytest.raises(ValueError,match="CONFLICTING_TRAINING"):
        normalize_results(rows,league_id=71,as_of=START,plan=PLAN)

@pytest.mark.parametrize("field,value",[("home_goals",True),("home_goals",-1),("away_goals",None),
                                         ("neutral",None),("fixture_id",True),("home_team_id",None)])
def test_malformed_training_values_fail(field,value):
    rows=history();rows[0][field]=value
    with pytest.raises((ValueError,TypeError)):
        normalize_results(rows,league_id=71,as_of=START,plan=PLAN)

def test_artifact_tamper_wrong_league_postkickoff_rejected(artifact):
    bad=deepcopy(artifact);bad["parameters"]["rho"]=.1
    args=dict(home_team_id=1,away_team_id=2,league_id=71,neutral=False,as_of=START,
              kickoff=START+timedelta(hours=1),plan=PLAN)
    with pytest.raises(ValueError,match="INTEGRITY"): model.predict(bad,**args)
    args["league_id"]=1
    with pytest.raises(ValueError): model.predict(artifact,**args)
    args["league_id"]=71;args["kickoff"]=START
    with pytest.raises(ValueError): model.predict(artifact,**args)

def test_forecast_exact_source_pair_and_book_choice(artifact):
    value=forecast(item(),artifact=artifact,plan=PLAN,now=START+timedelta(seconds=1))
    assert value["bookmaker_id"]==1
    assert set(value["comparisons"]["HOME_WIN"])==set(COMPARATORS)
    assert value["comparisons"]["HOME_WIN"]["EXISTING_ENSEMBLE"]==.55
    assert value["telegram_publication"] is False and value["selection_effect"]=="NONE"
    assert value["comparison_odds"]["HOME_WIN"]=="2"
    verify(value)

@pytest.mark.parametrize("delay",[901,3600])
def test_stale_or_postkickoff_research_cannot_backfill(artifact,delay):
    with pytest.raises(ValueError):
        forecast(item(),artifact=artifact,plan=PLAN,now=START+timedelta(seconds=delay))

def test_resealed_candidate_tamper_and_training_clock_rejected(artifact):
    source=item();source["candidates"]["HOME_WIN"]["ensemble_probability"]=".99"
    with pytest.raises(ValueError,match="MODEL_REFERENCE"):
        forecast(source,artifact=artifact,plan=PLAN,now=START)
    bad=deepcopy(artifact);bad.pop("fingerprint");bad["input_as_of"]=(START-timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError,match="CLOCK"):
        forecast(item(),artifact=seal(bad),plan=PLAN,now=START)

def test_metrics_pending_void_duplicate_labels_and_exact_pair_counts(artifact):
    f=forecast(item(),artifact=artifact,plan=PLAN,now=START)
    args=dict(forecasts=[f],models={artifact["fingerprint"]:artifact},plan=PLAN)
    pending=evaluate(results=[],now=START,**args)
    assert pending["lifecycle"]=={"PENDING":1,"VOID":0,"RESOLVED":0}
    output=evaluate(results=[result(),result()],now=START+timedelta(days=1),**args)
    assert output["overall"]["fixtures"]==1 and output["overall"]["market_rows"]==3
    assert output["overall"]["common_market_rows"]==3 and output["counts"]["duplicate_result"]==1
    assert output["overall"]["paired"]["DIXON_COLES"]["method"]==output["overall"]["paired"]["DIXON_COLES"]["paired_dixon_coles"]
    void=evaluate(results=[result(status="VOID",home_goals=None,away_goals=None)],now=START+timedelta(days=1),**args)
    assert void["lifecycle"]["VOID"]==1 and void["overall"]["market_rows"]==0
    assert evaluate(results=[result()],now=START,**args)["lifecycle"]["PENDING"]==1

def test_metrics_refuses_conflicts_duplicate_forecasts_and_forged_probabilities(artifact):
    f=forecast(item(),artifact=artifact,plan=PLAN,now=START)
    args=dict(models={artifact["fingerprint"]:artifact},plan=PLAN,now=START+timedelta(days=1))
    with pytest.raises(ValueError,match="CONFLICTING_FORWARD"):
        evaluate([f],results=[result(),result(home_goals=0)],**args)
    with pytest.raises(ValueError,match="DUPLICATE_RESEARCH"):
        evaluate([f,f],results=[result()],**args)
    forged=deepcopy(f);forged.pop("fingerprint");forged["comparisons"]["HOME_WIN"]["DIXON_COLES"]=.99
    with pytest.raises(ValueError,match="REPRODUCTION"):
        evaluate([seal(forged)],results=[result()],**args)
    excluded=evaluate([f],results=[result(source_product="COMBO_LEG")],**args)
    assert excluded["lifecycle"]["PENDING"]==1

def test_append_only_replay_collision_and_production_schema_refusal(tmp_path):
    path=tmp_path/"research.db"; store=ResearchStore(path)
    value=seal({"x":1})
    assert store.append("test","x",value) and not store.append("test","x",value)
    with pytest.raises(ValueError,match="CONFLICT"): store.append("test","x",seal({"x":2}))
    for command in ("UPDATE dc_research_records SET identity='y'","DELETE FROM dc_research_records"):
        with pytest.raises(sqlite3.IntegrityError): store.connection.execute(command)
    store.close()
    with pytest.raises(ValueError,match="PRODUCTION"):
        ResearchStore(path,protected_paths=(path,))
    foreign=tmp_path/"production.db"
    with sqlite3.connect(foreign) as c: c.execute("CREATE TABLE evidence(x)")
    before=foreign.read_bytes()
    with pytest.raises(ValueError,match="DEDICATED"): ResearchStore(foreign)
    assert before==foreign.read_bytes()

def test_complete_intake_replay_no_model_refit_and_research_only(tmp_path,artifact,monkeypatch):
    from app.dixon_coles_research import service
    calls=[]
    monkeypatch.setattr(service,"fit",lambda *a,**k:(calls.append(1) or artifact))
    store=ResearchStore(tmp_path/"research.db")
    data={"items":[item()],"additional_reserved":[],"diagnostics":{}}
    first=intake(data,store,plan=PLAN,clock=lambda:START)
    second=intake(data,store,plan=PLAN,clock=lambda:START+timedelta(seconds=1))
    assert first["counts"]["forecast"]==1 and second["counts"]["already_forecast"]==1
    assert calls==[1] and len(store.all("forecast"))==1 and len(store.all("model"))==1
    assert first["provider_calls"]==first["telegram_sends"]==0
    store.close()

def test_resealed_model_reference_probability_must_match_candidate(artifact):
    from app.adaptive_lab.devig_research import capture
    source=item();old=source["capture"];refs=deepcopy(old["model_probabilities"])
    refs["HOME_WIN"]["probability"]=".99"
    source["capture"]=capture(old["source_consensus"],captured_at=START,kickoff=utc(old["kickoff_utc"]),
                              model_probabilities=refs,policy_context=old["policy_context"])
    with pytest.raises(ValueError,match="MODEL_REFERENCE"):
        forecast(source,artifact=artifact,plan=PLAN,now=START)

def test_retrieval_age_independent_of_provider_snapshot_age(artifact):
    from app.adaptive_lab.devig_research import capture
    source=item();old=source["capture"]
    later=START+timedelta(seconds=901)
    source["capture"]=capture(old["source_consensus"],captured_at=later,kickoff=utc(old["kickoff_utc"]),
                              model_probabilities=old["model_probabilities"],policy_context=old["policy_context"])
    assert source["capture"]["status"]=="AVAILABLE"
    with pytest.raises(ValueError,match="STALE_COMPARISON_RETRIEVAL"):
        forecast(source,artifact=artifact,plan=PLAN,now=later)

def test_missing_comparator_never_changes_paired_denominators(artifact):
    from app.adaptive_lab.devig_research import capture
    source=item();old=source["capture"];refs=deepcopy(old["model_probabilities"]);refs.pop("DRAW")
    source["candidates"].pop("DRAW")
    source["capture"]=capture(old["source_consensus"],captured_at=START,kickoff=utc(old["kickoff_utc"]),
                              model_probabilities=refs,policy_context=old["policy_context"])
    f=forecast(source,artifact=artifact,plan=PLAN,now=START)
    output=evaluate([f],{artifact["fingerprint"]:artifact},[result()],plan=PLAN,now=START+timedelta(days=1))
    assert f["missing_comparators"]=={"existing_model_missing":1}
    assert output["overall"]["common_market_rows"]==2
    assert output["overall"]["paired"]["EXISTING_ENSEMBLE"]["method"]["probability_observations"]==2

def test_frozen_policy_cannot_be_mutated():
    with pytest.raises(TypeError): model.POLICY["ridge"]=99

def test_first_forward_result_asof_excludes_future_correction(artifact):
    f=forecast(item(),artifact=artifact,plan=PLAN,now=START)
    early=result();late=result(home_goals=0,settled_at=(START+timedelta(days=2)).isoformat())
    output=evaluate([f],{artifact["fingerprint"]:artifact},[late,early],plan=PLAN,now=START+timedelta(days=1))
    assert output["counts"]["future_result"]==1 and output["lifecycle"]["RESOLVED"]==1

def test_all_neutral_training_cannot_invent_home_advantage():
    rows=history()
    for row in rows: row["neutral"]=True
    a=model.fit(rows,league_id=71,as_of=START,plan=PLAN)
    assert a["parameters"]["home_advantage"]==0.0

def test_wrong_quote_reference_is_not_same_snapshot(artifact):
    from app.adaptive_lab.devig_research import capture
    source=item();old=source["capture"]
    source["candidates"]["HOME_WIN"]["quote_provenance_fingerprint"]="unrelated"
    refs=deepcopy(old["model_probabilities"])
    refs["HOME_WIN"]["candidate_fingerprint"]=fingerprint(source["candidates"]["HOME_WIN"])
    source["capture"]=capture(old["source_consensus"],captured_at=START,kickoff=utc(old["kickoff_utc"]),
                              model_probabilities=refs,policy_context=old["policy_context"])
    with pytest.raises(ValueError,match="MODEL_REFERENCE"):
        forecast(source,artifact=artifact,plan=PLAN,now=START)
