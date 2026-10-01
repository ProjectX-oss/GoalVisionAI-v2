"""Glicko-2 research baseline and an explicitly experimental football draw link."""
from __future__ import annotations
from collections import defaultdict
from math import exp, log, pi, sqrt
from .contracts import digest, number, utc
from .shadow_research import fixture_identity, record

SCALE = 173.7178
INITIAL = {"rating":1500., "rd":350., "volatility":.06}
CONFIG = {"version":"GLICKO_FOOTBALL_SHADOW_V1","tau":.5,"home_advantage":35.,
          "rating_period_days":1,"draw_prior":.25,"draw_prior_sample":20,
          "minimum_team_matches":8,"margin_of_victory_used":False}


def _state(value):
    return (number(value["rating"],low=-10000,high=10000),
            number(value["rd"],low=.000001,high=1000),
            number(value["volatility"],low=.000001,high=1))


def _g(phi):
    return 1/sqrt(1+3*phi*phi/(pi*pi))


def update(state, opponents, *, tau=.5):
    """Official Glicko-2 equations; opponents: (rating, RD, score)."""
    rating,rd,sigma = _state(state)
    tau = number(tau,low=.1,high=1.2)
    mu,phi = (rating-1500)/SCALE, rd/SCALE
    if not opponents:
        return {"rating":rating,"rd":SCALE*sqrt(phi*phi+sigma*sigma),"volatility":sigma}
    values = []
    for r,d,s in opponents:
        r,d = number(r,low=-10000,high=10000),number(d,low=.000001,high=1000)
        if s not in (0,.5,1):
            raise ValueError("GLICKO_SCORE_INVALID")
        g = _g(d/SCALE)
        expected = 1/(1+exp(-g*(mu-(r-1500)/SCALE)))
        values.append((g,expected,s))
    variance = 1/sum(g*g*e*(1-e) for g,e,s in values)
    improvement = sum(g*(s-e) for g,e,s in values)
    delta = variance*improvement
    alpha = log(sigma*sigma)
    def f(x):
        ex = exp(x)
        return ex*(delta*delta-phi*phi-variance-ex)/(2*(phi*phi+variance+ex)**2)-(x-alpha)/(tau*tau)
    A = alpha
    if delta*delta > phi*phi+variance:
        B = log(delta*delta-phi*phi-variance)
    else:
        for k in range(1,101):
            B = alpha-k*tau
            if f(B) >= 0:
                break
        else:
            raise ValueError("GLICKO_VOLATILITY_BRACKET_FAILED")
    fa,fb = f(A),f(B)
    for _ in range(100):
        if abs(B-A) <= 1e-6:
            break
        C = A+(A-B)*fa/(fb-fa)
        fc = f(C)
        if fc*fb <= 0:
            A,fa = B,fb
        else:
            fa /= 2
        B,fb = C,fc
    else:
        raise ValueError("GLICKO_VOLATILITY_NOT_CONVERGED")
    volatility = exp(A/2)
    phistar = sqrt(phi*phi+volatility*volatility)
    newphi = 1/sqrt(1/(phistar*phistar)+1/variance)
    result = {"rating":1500+SCALE*(mu+newphi*newphi*improvement),
              "rd":SCALE*newphi,"volatility":volatility}
    _state(result)
    return result


def _age(state, periods):
    r,d,s = _state(state)
    return {"rating":r,"rd":min(350.,SCALE*sqrt((d/SCALE)**2+max(0,periods)*s*s)),
            "volatility":s}


def capture(context, *, now, references=None):
    """Replay already available results, scoped to one league and team identity."""
    fixture_identity(context,now)
    if context.get("version") != "CURRENT_RESULTS_CONTEXT_V1":
        raise ValueError("CURRENT_RESULT_CONTEXT_REQUIRED")
    histories = context.get("results",[])
    periods,seen = defaultdict(list),set()
    for row in histories:
        if (row.get("status") != "RESOLVED" or not row.get("source_fingerprint")
                or row.get("league_id") != context["league_id"]
                or row.get("fixture_id") == context["fixture_id"]
                or row.get("home_team_id") == row.get("away_team_id")):
            raise ValueError("GLICKO_RESULT_PROVENANCE_INVALID")
        if row["fixture_id"] in seen:
            raise ValueError("GLICKO_DUPLICATE_RESULT")
        seen.add(row["fixture_id"])
        if not utc(row["kickoff_utc"]) < utc(row["available_at"]) <= utc(context["captured_at"]):
            raise ValueError("GLICKO_RESULT_NOT_AVAILABLE")
        if any(isinstance(row[k],bool) or not isinstance(row[k],int) or not 0<=row[k]<=30
               for k in ("home_goals","away_goals")):
            raise ValueError("GLICKO_RESULT_SCORE_INVALID")
        # Same kickoff day is one simultaneous rating period. Every input
        # result must already be available at the current capture time.
        periods[utc(row["kickoff_utc"]).date()].append(row)
    states,counts,last = {},defaultdict(int),{}
    draws = 0
    for day,games in sorted(periods.items()):
        teams = {row[k] for row in games for k in ("home_team_id","away_team_id")}
        before = {team:_age(states.get(team,INITIAL),
                    max(0,(day-last[team]).days-1) if team in last else 0) for team in teams}
        opponents = defaultdict(list)
        for row in sorted(games,key=lambda r:r["fixture_id"]):
            home,away = row["home_team_id"],row["away_team_id"]
            score = 1 if row["home_goals"]>row["away_goals"] else 0 if row["home_goals"]<row["away_goals"] else .5
            advantage = 0. if row.get("neutral_venue") else CONFIG["home_advantage"]
            opponents[home].append((before[away]["rating"]-advantage,before[away]["rd"],score))
            opponents[away].append((before[home]["rating"]+advantage,before[home]["rd"],1-score))
            counts[home] += 1
            counts[away] += 1
            draws += int(score==.5)
        for team in sorted(teams):
            states[team] = update(before[team],opponents[team],tau=CONFIG["tau"])
            last[team] = day
    teams = [context["home_team_id"],context["away_team_id"]]
    if any(counts[t] < CONFIG["minimum_team_matches"] for t in teams):
        raise ValueError("GLICKO_TEAM_HISTORY_INSUFFICIENT")
    home,away = [_age(states[t],(utc(context["captured_at"]).date()-last[t]).days) for t in teams]
    advantage = 0. if context.get("neutral_venue") else CONFIG["home_advantage"]
    attenuation = _g(sqrt(home["rd"]**2+away["rd"]**2)/SCALE)
    difference = attenuation*(home["rating"]+advantage-away["rating"])/SCALE
    prior = (draws+CONFIG["draw_prior"]*CONFIG["draw_prior_sample"])/(len(histories)+CONFIG["draw_prior_sample"])
    # Davidson-style three-way link is an uncalibrated research adaptation,
    # not part of the Glicko-2 rating equations.
    draw_weight = 2*prior/(1-prior)
    weights = [exp(difference/2),draw_weight,exp(-difference/2)]
    probs = dict(zip(("HOME_WIN","DRAW","AWAY_WIN"),(v/sum(weights) for v in weights)))
    output = {"probabilities":probs,"home_state":home,"away_state":away,
              "home_matches":counts[teams[0]],"away_matches":counts[teams[1]],
              "league_draw_prior":prior,"source_result_count":len(histories),
              "config":CONFIG,"config_fingerprint":digest(CONFIG),
              "uncertainty_treatment":"RD_ATTENUATION_AND_IDLE_PERIOD_INFLATION",
              "draw_link":"UNCALIBRATED_DAVIDSON_STYLE_V1",
              "independence_group":"RESULT_HISTORY_MODEL_CONTEXT"}
    return record("DYNAMIC_STRENGTH",context,output,now=now,references=references)
