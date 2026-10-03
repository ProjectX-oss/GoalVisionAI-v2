"""Original standard-library implementation of a regularized Dixon–Coles model.

The four-cell correction follows Dixon & Coles (1997). Attack/defence, home
advantage and dependence are fitted jointly with a deterministic BFGS solver.
No external model code, pickle, network, provider or publication dependency.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime
from math import exp, log, lgamma, tanh, isfinite, fsum
from .contracts import (POLICY, MODEL_VERSION, seal, verify, finite, integer,
                        normalize_results, utc, MARKETS)

def correction(h: int, a: int, lam: float, mu: float, rho: float) -> float:
    if (h,a) == (0,0): return 1-lam*mu*rho
    if (h,a) == (0,1): return 1+lam*rho
    if (h,a) == (1,0): return 1+mu*rho
    if (h,a) == (1,1): return 1-rho
    return 1.0

def _objective(theta: list[float], rows: list[tuple], n: int) -> tuple[float,list[float]]:
    """Weighted negative log-likelihood and analytic gradient (mean-zero strengths)."""
    g = [0.0]*len(theta)
    value, mass = 0.0, fsum(r[5] for r in rows)
    attacks, defenses = theta[2:2+n], theta[2+n:2+2*n]
    am, dm = fsum(attacks)/n, fsum(defenses)/n
    rho = POLICY["rho_scale"]*tanh(theta[-1])
    drho = POLICY["rho_scale"]*(1-tanh(theta[-1])**2)
    for hi,ai,h,a,neutral,w in rows:
        lh = theta[0]+attacks[hi]-am+defenses[ai]-dm+(0 if neutral else theta[1])
        la = theta[0]+attacks[ai]-am+defenses[hi]-dm
        if min(lh,la) < -12 or max(lh,la) > log(POLICY["maximum_goal_rate"]):
            return float("inf"),g
        lam,mu = exp(lh),exp(la)
        if min(correction(x,y,lam,mu,rho) for x,y in ((0,0),(0,1),(1,0),(1,1))) <= 1e-10:
            return float("inf"),g
        tau = correction(h,a,lam,mu,rho)
        tl=tm=tr=0.0
        if (h,a)==(0,0): tl=tm=-lam*mu*rho; tr=-lam*mu
        elif (h,a)==(0,1): tl=lam*rho; tr=lam
        elif (h,a)==(1,0): tm=mu*rho; tr=mu
        elif (h,a)==(1,1): tr=-1
        weight=w/mass
        value += weight*(lam-h*lh+lgamma(h+1)+mu-a*la+lgamma(a+1)-log(tau))
        gh,ga=weight*(lam-h-tl/tau),weight*(mu-a-tm/tau)
        g[0] += gh+ga
        if not neutral: g[1] += gh
        g[2+hi] += gh; g[2+ai] += ga
        g[2+n+ai] += gh; g[2+n+hi] += ga
        g[-1] -= weight*tr*drho/tau
    for start,block in ((2,attacks),(2+n,defenses)):
        gm=fsum(g[start:start+n])/n; bm=fsum(block)/n
        for i,x in enumerate(block):
            g[start+i] = g[start+i]-gm+POLICY["ridge"]*(x-bm)/n
            value += POLICY["ridge"]*(x-bm)**2/(2*n)
    # A weak, declared regularizer keeps home/dependence estimates finite.
    for j in (1,len(theta)-1):
        value += POLICY["ridge"]*theta[j]**2/2
        g[j] += POLICY["ridge"]*theta[j]
    return value,g

def _optimize(initial: list[float], rows: list[tuple], n: int) -> tuple[list[float],dict]:
    x=initial[:]; size=len(x)
    identity=lambda:[[float(i==j) for j in range(size)] for i in range(size)]
    inverse=identity(); value,g=_objective(x,rows,n); initial_value=value
    for iteration in range(POLICY["maximum_iterations"]+1):
        norm=max(abs(v) for v in g)
        if isfinite(value) and norm <= POLICY["gradient_tolerance"]:
            return x,{"converged":True,"iterations":iteration,"gradient_inf":norm,
                      "objective":value,"initial_objective":initial_value}
        if iteration == POLICY["maximum_iterations"]: break
        direction=[-fsum(inverse[i][j]*g[j] for j in range(size)) for i in range(size)]
        slope=fsum(a*b for a,b in zip(g,direction))
        if not isfinite(slope) or slope>=0:
            inverse=identity(); direction=[-v for v in g]; slope=-fsum(v*v for v in g)
        step=1.0
        for _ in range(45):
            trial=[a+step*b for a,b in zip(x,direction)]
            fv,gg=_objective(trial,rows,n)
            if isfinite(fv) and fv<=value+1e-4*step*slope: break
            step*=0.5
        else: break
        s=[b-a for a,b in zip(x,trial)]; y=[b-a for a,b in zip(g,gg)]
        ys=fsum(a*b for a,b in zip(y,s))
        if ys>1e-12:
            hy=[fsum(inverse[i][j]*y[j] for j in range(size)) for i in range(size)]
            factor=(ys+fsum(a*b for a,b in zip(y,hy)))/(ys*ys)
            inverse=[[inverse[i][j]+factor*s[i]*s[j]-(hy[i]*s[j]+s[i]*hy[j])/ys
                      for j in range(size)] for i in range(size)]
        else: inverse=identity()
        x,value,g=trial,fv,gg
    raise ValueError("FIT_DID_NOT_CONVERGE")

def fit(rows: list[dict], *, league_id: int, as_of: datetime, plan: dict,
        additional_reserved: frozenset[int] = frozenset()) -> dict:
    normalized,excluded=normalize_results(rows,league_id=league_id,as_of=as_of,
                                          plan=plan,additional_reserved=additional_reserved)
    if len(normalized)<POLICY["minimum_matches"]:
        raise ValueError("INSUFFICIENT_LEAGUE_RESULTS")
    teams=sorted({r[k] for r in normalized for k in ("home_team_id","away_team_id")})
    n=len(teams)
    if not 2<=n<=POLICY["maximum_teams"]: raise ValueError("TEAM_CAPACITY")
    index={t:i for i,t in enumerate(teams)}
    counts=Counter(t for r in normalized for t in (r["home_team_id"],r["away_team_id"]))
    cutoff=utc(as_of)
    training=[(index[r["home_team_id"]],index[r["away_team_id"]],r["home_goals"],
               r["away_goals"],r["neutral"],2**(-(cutoff-utc(r["kickoff_utc"])).total_seconds()/86400/POLICY["half_life_days"]))
              for r in normalized]
    total=fsum(r[5] for r in training)
    mh=fsum(r[2]*r[5] for r in training)/total
    ma=fsum(r[3]*r[5] for r in training)/total
    initial=[log(max(.2,ma)),0.0 if all(r[4] for r in training) else log(max(.2,mh)/max(.2,ma))]+[0.0]*(2*n)+[0.0]
    theta,diagnostics=_optimize(initial,training,n)
    attack=theta[2:2+n]; defense=theta[2+n:2+2*n]
    am,dm=fsum(attack)/n,fsum(defense)/n
    params={"base":theta[0],"home_advantage":theta[1],
            "attack":{str(t):attack[i]-am for i,t in enumerate(teams)},
            "defense":{str(t):defense[i]-dm for i,t in enumerate(teams)},
            "rho":POLICY["rho_scale"]*tanh(theta[-1])}
    return seal({"version":MODEL_VERSION,"plan_fingerprint":plan["fingerprint"],
                 "league_id":league_id,"input_as_of":cutoff.isoformat(),
                 "policy":dict(POLICY),"training_matches":normalized,
                 "training_counts":{str(t):counts[t] for t in teams},
                 "excluded":excluded,"parameters":params,"fit":diagnostics,
                 "research_only":True,"selection_effect":"NONE"})

def markets(lam: float, mu: float, rho: float) -> dict:
    """Expand the score grid until omitted Poisson mass is explicitly negligible."""
    lam=finite(lam,low=1e-6,high=POLICY["maximum_goal_rate"])
    mu=finite(mu,low=1e-6,high=POLICY["maximum_goal_rate"])
    rho=finite(rho,low=-POLICY["rho_scale"],high=POLICY["rho_scale"])
    if min(correction(h,a,lam,mu,rho) for h,a in ((0,0),(0,1),(1,0),(1,1))) <= 0:
        raise ValueError("INVALID_LOW_SCORE_PROBABILITY")
    hp,ap=[exp(-lam)],[exp(-mu)]
    for k in range(1,POLICY["maximum_goals"]+1):
        hp.append(hp[-1]*lam/k); ap.append(ap[-1]*mu/k)
        if k>=3 and 1-fsum(hp)*fsum(ap)<=POLICY["tail_tolerance"]: break
    else: raise ValueError("SCORE_GRID_TAIL_TOO_LARGE")
    cells=[(h,a,p*q*correction(h,a,lam,mu,rho))
           for h,p in enumerate(hp) for a,q in enumerate(ap)]
    mass=fsum(p for h,a,p in cells); tail=max(0.0,1-mass)
    if abs(1-mass)>POLICY["tail_tolerance"]*2: raise ValueError("SCORE_GRID_MASS")
    out={"HOME_WIN":fsum(p for h,a,p in cells if h>a)/mass,
         "DRAW":fsum(p for h,a,p in cells if h==a)/mass,
         "AWAY_WIN":fsum(p for h,a,p in cells if h<a)/mass,
         "BTTS_YES":fsum(p for h,a,p in cells if h>0 and a>0)/mass}
    out["BTTS_NO"]=1-out["BTTS_YES"]
    for line in (1,2,3):
        over=fsum(p for h,a,p in cells if h+a>line)/mass
        out[f"OVER_{line}_5"]=over; out[f"UNDER_{line}_5"]=1-over
    if set(out)!=MARKETS or any(not isfinite(p) or not 0<p<1 for p in out.values()):
        raise ValueError("MARKET_PROBABILITY_CONTRACT")
    return {"probabilities":out,"omitted_mass":tail,"maximum_goals":k,
            "home_goal_rate":lam,"away_goal_rate":mu,"rho":rho}

def predict(artifact: dict, *, home_team_id: int, away_team_id: int,
            league_id: int, neutral: bool, as_of: datetime, kickoff: datetime,
            plan: dict) -> dict:
    from .contracts import verify_plan
    verify_plan(plan); verify(artifact)
    if (artifact["version"]!=MODEL_VERSION or artifact["policy"]!=POLICY
            or artifact["plan_fingerprint"]!=plan["fingerprint"]
            or artifact["league_id"]!=league_id or artifact["fit"]["converged"] is not True
            or not utc(artifact["input_as_of"])<=utc(as_of)<utc(kickoff)):
        raise ValueError("ARTIFACT_OR_PREDICTION_BOUNDARY")
    integer(home_team_id); integer(away_team_id)
    if home_team_id==away_team_id or type(neutral) is not bool: raise ValueError("FIXTURE_CONTRACT")
    h,a=str(home_team_id),str(away_team_id); p=artifact["parameters"]
    if any(artifact["training_counts"].get(t,0)<POLICY["minimum_target_team_matches"] for t in (h,a)):
        raise ValueError("INSUFFICIENT_TARGET_TEAM_RESULTS")
    lam=exp(p["base"]+p["attack"][h]+p["defense"][a]+(0 if neutral else p["home_advantage"]))
    mu=exp(p["base"]+p["attack"][a]+p["defense"][h])
    return {"dixon_coles":markets(lam,mu,p["rho"]),
            "independent_poisson_ablation":markets(lam,mu,0)}
