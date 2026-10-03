"""Exact derivatives in identifiable coordinates; strictly feasible evaluations."""
from __future__ import annotations
from math import exp, fsum, isfinite, lgamma, log, tanh
from app.dixon_coles_research.contracts import POLICY

class Infeasible(ValueError):
    """A trial point is outside the original model domain."""

def full_theta(x: list[float], n: int) -> list[float]:
    if len(x) != 2*n+1 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) for v in x):
        raise ValueError("INVALID_REDUCED_PARAMETERS")
    attack=x[2:n+1]; defense=x[n+1:2*n]
    return x[:2]+attack+[-fsum(attack)]+defense+[-fsum(defense)]+[x[-1]]

def features(team: int, offset: int, n: int) -> dict[int,float]:
    return {offset+team:1.0} if team<n-1 else {offset+i:-1.0 for i in range(n-1)}

def design(rows: list[tuple], n: int) -> list[tuple]:
    output=[]
    for hi,ai,h,a,neutral,w in rows:
        vh={0:1.0, **({1:1.0} if not neutral else {}),
            **features(hi,2,n), **features(ai,n+1,n)}
        va={0:1.0, **features(ai,2,n), **features(hi,n+1,n)}
        output.append((h,a,w,(vh,va,{2*n:1.0})))
    return output

def low_cells(lam: float, mu: float, raw: float) -> list[tuple]:
    """(tau, gradient, Hessian) with respect to log-lambda/log-mu/raw-rho."""
    t=tanh(raw); rho=POLICY["rho_scale"]*t
    dr=POLICY["rho_scale"]*(1-t*t); ddr=-2*t*dr
    def cell(value, dl, da, drr, dll, dla, dlr, daa, dar, drrr):
        return value,[dl,da,drr],[[dll,dla,dlr],[dla,daa,dar],[dlr,dar,drrr]]
    k=-lam*mu*rho; kr=-lam*mu*dr; krr=-lam*mu*ddr
    return [
        cell(1+k,k,k,kr,k,k,kr,k,kr,krr),
        cell(1+lam*rho,lam*rho,0,lam*dr,lam*rho,0,lam*dr,0,0,lam*ddr),
        cell(1+mu*rho,0,mu*rho,mu*dr,0,0,0,mu*rho,mu*dr,mu*ddr),
        cell(1-rho,0,0,-dr,0,0,0,0,0,-ddr)]

def evaluate(x: list[float], rows: list[tuple], n: int, weight: float,
             *, hessian: bool=True, prepared: list[tuple] | None=None) -> tuple:
    """Likelihood + log barrier; constraints match V1 without clipping."""
    full_theta(x,n)
    if not isfinite(weight) or weight<0: raise ValueError("INVALID_BARRIER_WEIGHT")
    prepared=design(rows,n) if prepared is None else prepared
    size=len(x); g=[0.0]*size; matrix=[[0.0]*size for _ in range(size)] if hessian else None
    objective=barrier=0.0; mass=fsum(r[2] for r in prepared)
    if mass<=0: raise ValueError("INVALID_TRAINING_MASS")
    min_slack=float("inf"); max_rate=0.0; min_tau=float("inf"); max_multiplier=0.0
    for h,a,w,vectors in prepared:
        lh,la,raw=(fsum(x[i]*v for i,v in vector.items()) for vector in vectors)
        if min(lh,la)<=-12.0 or max(lh,la)>=log(POLICY["maximum_goal_rate"]):
            raise Infeasible("GOAL_RATE_BOUNDARY")
        lam,mu=exp(lh),exp(la)
        cells=low_cells(lam,mu,raw)
        if min(c[0] for c in cells)<=1e-10: raise Infeasible("LOW_CELL_BOUNDARY")
        max_rate=max(max_rate,lam,mu);min_tau=min(min_tau,*(c[0] for c in cells))
        scale=w/mass
        local_g=[scale*(lam-h),scale*(mu-a),0.0]
        local_h=[[scale*lam,0.0,0.0],[0.0,scale*mu,0.0],[0.0,0.0,0.0]]
        value=lam-h*lh+lgamma(h+1)+mu-a*la+lgamma(a+1)
        if h<=1 and a<=1:
            tau,tg,th=cells[2*h+a]
            value-=log(tau)
            for j in range(3):
                local_g[j]-=scale*tg[j]/tau
                if hessian:
                    for k in range(3):
                        local_h[j][k]+=scale*(tg[j]*tg[k]/(tau*tau)-th[j][k]/tau)
        objective+=scale*value
        zero=[[0.0]*3 for _ in range(3)]
        constraints=[(lh+12,[1,0,0],zero),(log(8.0)-lh,[-1,0,0],zero),
                     (la+12,[0,1,0],zero),(log(8.0)-la,[0,-1,0],zero)]
        constraints.extend((tau-1e-10,tg,th) for tau,tg,th in cells)
        for slack,sg,sh in constraints:
            min_slack=min(min_slack,slack)
            multiplier=weight/slack
            max_multiplier=max(max_multiplier,multiplier)
            barrier-=weight*log(slack)
            for j in range(3):
                local_g[j]-=multiplier*sg[j]
                if hessian:
                    for k in range(3):
                        local_h[j][k]+=multiplier*(sg[j]*sg[k]/slack-sh[j][k])
        for j,vector in enumerate(vectors):
            for i,v in vector.items():
                g[i]+=v*local_g[j]
                if hessian:
                    for k,other in enumerate(vectors):
                        scalar=v*local_h[j][k]
                        if scalar:
                            for q,u in other.items(): matrix[i][q]+=scalar*u
    ridge=POLICY["ridge"]
    for start in (2,n+1):
        values=x[start:start+n-1];last=-fsum(values)
        objective+=ridge*(fsum(v*v for v in values)+last*last)/(2*n)
        for j,v in enumerate(values):
            g[start+j]+=ridge*(v-last)/n
            if hessian:
                for k in range(n-1):
                    matrix[start+j][start+k]+=ridge*((j==k)+1)/n
    for j in (1,size-1):
        objective+=ridge*x[j]*x[j]/2;g[j]+=ridge*x[j]
        if hessian: matrix[j][j]+=ridge
    certificate={"objective":objective,"minimum_slack":min_slack,
        "maximum_fitted_rate":max_rate,"minimum_low_cell_factor":min_tau,
        "constraints":8*len(rows),"barrier_weight":weight,
        "stationarity_inf":max(abs(v) for v in g),"complementarity_inf":weight,
        "complementarity_sum":weight*8*len(rows),"maximum_multiplier":max_multiplier,
        "dual_feasible":True,"strictly_feasible":True,"global_optimum_claim":False}
    return objective+barrier,g,matrix,certificate
