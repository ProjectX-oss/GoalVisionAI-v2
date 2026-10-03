"""Independent math checks and development isolation; all data are controlled."""
from copy import deepcopy
from datetime import timedelta
from math import exp, log, sqrt
import pytest
from app.dixon_coles_constrained import geometry, model, solver
from app.dixon_coles_research import model as baseline
from app.dixon_coles_research.contracts import seal, POLICY
from tests.test_dixon_coles_research import history, PLAN, START

ROWS=[(0,1,0,0,False,1.0),(1,2,0,1,False,.8),(2,0,1,0,True,.7),
      (0,2,1,1,False,.9),(1,0,3,2,False,.5)]
POINT=[.1,.2,-.1,.1,.1,-.15,.2]

@pytest.mark.parametrize("weight",[0.0,.0002,.02])
def test_analytic_gradient_and_hessian_against_central_difference(weight):
    value,g,h,cert=geometry.evaluate(POINT,ROWS,3,weight)
    step=1e-5
    for j in range(len(POINT)):
        left=POINT[:];right=POINT[:];left[j]-=step;right[j]+=step
        lf,lg,_,_=geometry.evaluate(left,ROWS,3,weight)
        rf,rg,_,_=geometry.evaluate(right,ROWS,3,weight)
        assert g[j]==pytest.approx((rf-lf)/(2*step),abs=3e-8)
        for i in range(len(POINT)):
            assert h[i][j]==pytest.approx((rg[i]-lg[i])/(2*step),abs=2e-7)
            assert h[i][j]==pytest.approx(h[j][i],abs=1e-12)
    assert cert["minimum_slack"]>0

def test_exact_same_likelihood_regularization_and_transformed_gradient():
    full=geometry.full_theta(POINT,3)
    old_value,old_g=baseline._objective(full,ROWS,3)
    new_value,new_g,_,_=geometry.evaluate(POINT,ROWS,3,0)
    transformed=old_g[:2]+[old_g[2+i]-old_g[4] for i in range(2)]
    transformed += [old_g[5+i]-old_g[7] for i in range(2)]+[old_g[-1]]
    assert old_value==pytest.approx(new_value,abs=1e-12)
    assert new_g==pytest.approx(transformed,abs=1e-12)

@pytest.mark.parametrize("base,raw",[(log(8),0),(-12,0),(log(3),3)])
def test_original_domain_rejected_without_clipping(base,raw):
    point=[base,0,0,0,0,0,raw]
    with pytest.raises(geometry.Infeasible):
        geometry.evaluate(point,ROWS,3,.001)

def scalar_problem(target,quartic=False):
    def evaluate(x,weight,*,hessian=True):
        p=x[0];lo,hi=(-2,2) if quartic else (-1,1)
        if not lo<p<hi: raise geometry.Infeasible("DOMAIN")
        sl,sr=p-lo,hi-p
        value=p**4-p*p if quartic else (p-target)**2/2
        g=4*p**3-2*p if quartic else p-target
        h=12*p*p-2 if quartic else 1
        bv=value-weight*(log(sl)+log(sr))
        bg=g-weight/sl+weight/sr
        bh=h+weight/sl**2+weight/sr**2
        cert={"objective":value,"minimum_slack":min(sl,sr),"dual_feasible":True,
              "complementarity_inf":weight,"stationarity_inf":abs(bg)}
        return bv,[bg],[[bh]] if hessian else None,cert
    return evaluate

@pytest.mark.parametrize("target,expected",[(2,1),(.3,.3),(-2,-1)])
def test_known_constrained_quadratic_solution(target,expected):
    x,report=solver.solve([0],scalar_problem(target),model.load_protocol()["solver"])
    assert x[0]==pytest.approx(expected,abs=1e-6)
    assert -1<x[0]<1
    assert report["certificate"]["stationarity_inf"]<=1e-6
    assert report["certificate"]["complementarity_inf"]<=1e-6

def test_indefinite_hessian_is_damped_and_local_claim_only():
    x,report=solver.solve([.1],scalar_problem(0,True),model.load_protocol()["solver"])
    assert x[0]==pytest.approx(sqrt(.5),abs=1e-6)
    assert report["maximum_hessian_damping"]>0
    assert report["criterion"]=="LOCAL_APPROXIMATE_KKT"

@pytest.mark.parametrize("key,value,reason",[
    ("max_evaluations",1,"EVALUATION_BUDGET"),
    ("max_iterations_per_stage",0,"ITERATION_BUDGET"),
    ("max_line_search_steps",0,"LINE_SEARCH_UNAVAILABLE"),
    ("max_damping_attempts",0,"HESSIAN_UNAVAILABLE")])
def test_explicit_budgets_never_return_uncertified_fit(key,value,reason):
    settings=model.load_protocol()["solver"];settings[key]=value
    with pytest.raises(ValueError,match=reason):
        solver.solve([0],scalar_problem(2),settings)

def test_cpu_budget_is_not_a_convergence_result():
    times=iter([0,100])
    with pytest.raises(ValueError,match="CPU_BUDGET"):
        solver.solve([0],scalar_problem(2),model.load_protocol()["solver"],cpu_clock=lambda:next(times))

@pytest.fixture(scope="module")
def candidate():
    return model.fit(history(),league_id=71,as_of=START,plan=PLAN)

def test_controlled_fit_has_valid_certificate_and_no_forward_eligibility(candidate):
    cert=model.verify_artifact(candidate,plan=PLAN)
    assert cert["stationarity_inf"]<=1e-6
    assert cert["maximum_fitted_rate"]<8
    assert cert["minimum_low_cell_factor"]>1e-10
    assert candidate["purpose"]=="DEVELOPMENT_ONLY" and candidate["forward_eligible"] is False
    assert candidate["selection_effect"]=="NONE"
    assert model.fit(list(reversed(history())),league_id=71,as_of=START,plan=PLAN)==candidate

def test_interior_prediction_and_loss_agree_with_baseline(candidate):
    old=baseline.fit(history(),league_id=71,as_of=START,plan=PLAN)
    args=dict(home_team_id=1,away_team_id=2,league_id=71,neutral=False,
              as_of=START,kickoff=START+timedelta(hours=1),plan=PLAN)
    new=model.predict(candidate,**args)["dixon_coles"]
    prior=baseline.predict(old,**args)["dixon_coles"]
    limits=model.load_protocol()["acceptance"]
    assert abs(candidate["fit"]["certificate"]["objective"]-old["fit"]["objective"])<limits["interior_objective_absolute_tolerance"]
    assert max(abs(v-prior["probabilities"][k]) for k,v in new["probabilities"].items())<limits["interior_probability_absolute_tolerance"]
    assert sum(new["probabilities"][k] for k in ("HOME_WIN","DRAW","AWAY_WIN"))==pytest.approx(1,abs=1e-12)
    assert new["omitted_mass"]<=2e-12

@pytest.mark.parametrize("change",["version","purpose","forward","parameters","counts","theta","certificate","protocol"])
def test_resealed_invalid_artifact_is_rejected(candidate,change):
    value=deepcopy(candidate);value.pop("fingerprint")
    if change=="version": value["version"]="OLD"
    elif change=="purpose": value["purpose"]="FORWARD"
    elif change=="forward": value["forward_eligible"]=True
    elif change=="parameters": value["parameters"]["rho"]+=.01
    elif change=="counts": value["training_counts"]["1"]+=1
    elif change=="theta": value["optimizer_theta"][0]+=.01
    elif change=="certificate": value["fit"]["certificate"]["stationarity_inf"]=0
    else: value["protocol_fingerprint"]="wrong"
    with pytest.raises(ValueError): model.verify_artifact(seal(value),plan=PLAN)

def test_legacy_reader_rejects_new_variant(candidate):
    args=dict(home_team_id=1,away_team_id=2,league_id=71,neutral=False,as_of=START,
              kickoff=START+timedelta(hours=1),plan=PLAN)
    with pytest.raises(ValueError,match="ARTIFACT"): baseline.predict(candidate,**args)
    old=baseline.fit(history(),league_id=71,as_of=START,plan=PLAN)
    with pytest.raises(ValueError,match="ARTIFACT"): model.predict(old,**args)

def test_target_constraints_chronology_and_consumed_holdouts(candidate):
    args=dict(home_team_id=1,away_team_id=2,league_id=71,neutral=False,as_of=START,
              kickoff=START+timedelta(hours=1),plan=PLAN)
    with pytest.raises(ValueError,match="TARGET_TEAM"):
        model.predict(candidate,**{**args,"home_team_id":99999})
    with pytest.raises(ValueError,match="BOUNDARY"):
        model.predict(candidate,**{**args,"as_of":START+timedelta(hours=1)})
    with pytest.raises(ValueError,match="TRAINING_REFERENCE"):
        model.predict(candidate,**args,additional_reserved=frozenset({candidate["training_matches"][0]["fixture_id"]}))

def test_sparse_training_and_neutral_only():
    with pytest.raises(ValueError,match="INSUFFICIENT_LEAGUE"):
        model.fit(history()[:39],league_id=71,as_of=START,plan=PLAN)
    rows=[{**r,"neutral":True} for r in history()]
    artifact=model.fit(rows,league_id=71,as_of=START,plan=PLAN)
    assert abs(artifact["parameters"]["home_advantage"])<1e-12

def test_boundary_fit_uses_feasible_initialization_without_relaxing_rate_limit():
    rows=[]
    for i,row in enumerate(history()[:48]):
        rows.append({**row,"home_team_id":1+i%2,"away_team_id":2-i%2,
                     "home_goals":10,"away_goals":1})
    value=model.fit(rows,league_id=71,as_of=START,plan=PLAN)
    cert=model.verify_artifact(value,plan=PLAN)
    assert value["initialization"]=="STRICTLY_FEASIBLE_UNIT_RATES"
    assert 7.99<cert["maximum_fitted_rate"]<8
    assert cert["minimum_slack"]>0
    assert cert["stationarity_inf"]<=1e-6
    assert cert["complementarity_inf"]<=1e-6

def test_near_low_cell_boundary_derivatives():
    point=[log(7),0,0,0,0,0,.095]
    _,gradient,hessian,cert=geometry.evaluate(point,ROWS,3,.0002)
    assert 0<cert["minimum_low_cell_factor"]<.1
    step=1e-6
    for j in range(len(point)):
        left=point[:];right=point[:];left[j]-=step;right[j]+=step
        lv,lg,_,_=geometry.evaluate(left,ROWS,3,.0002)
        rv,rg,_,_=geometry.evaluate(right,ROWS,3,.0002)
        assert gradient[j]==pytest.approx((rv-lv)/(2*step),rel=1e-5,abs=1e-7)
        for i in range(len(point)):
            assert hessian[i][j]==pytest.approx((rg[i]-lg[i])/(2*step),rel=1e-5,abs=1e-5)
