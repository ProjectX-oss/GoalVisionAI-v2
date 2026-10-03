"""Deterministic feasible damped Newton with an explicit local KKT check."""
from __future__ import annotations
from math import fsum, isfinite, sqrt
import time
from typing import Callable
from .geometry import Infeasible

def cholesky_direction(matrix: list[list[float]], gradient: list[float], damping: float) -> list[float]:
    n=len(gradient); lower=[[0.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(i+1):
            value=(matrix[i][j]+matrix[j][i])/2+(damping if i==j else 0)
            value-=fsum(lower[i][k]*lower[j][k] for k in range(j))
            if i==j:
                if not isfinite(value) or value<=0: raise ArithmeticError("NON_POSITIVE_HESSIAN")
                lower[i][j]=sqrt(value)
            else: lower[i][j]=value/lower[j][j]
    y=[]
    for i in range(n):
        y.append((-gradient[i]-fsum(lower[i][k]*y[k] for k in range(i)))/lower[i][i])
    result=[0.0]*n
    for i in range(n-1,-1,-1):
        result[i]=(y[i]-fsum(lower[k][i]*result[k] for k in range(i+1,n)))/lower[i][i]
    return result

def solve(initial: list[float], function: Callable, settings: dict, *,
          cpu_clock: Callable[[],float]=time.process_time) -> tuple[list[float],dict]:
    """Approximate local stationarity, feasibility and complementarity, never a global guarantee."""
    x=initial[:];started=cpu_clock();evaluations=0;stages=[];total_steps=0;max_damping=0.0
    def evaluate(point,weight,hessian):
        nonlocal evaluations
        if evaluations>=settings["max_evaluations"]: raise ValueError("CONSTRAINED_EVALUATION_BUDGET")
        if cpu_clock()-started>settings["cpu_seconds_per_fit"]: raise ValueError("CONSTRAINED_CPU_BUDGET")
        evaluations+=1
        result=function(point,weight,hessian=hessian)
        if cpu_clock()-started>settings["cpu_seconds_per_fit"]: raise ValueError("CONSTRAINED_CPU_BUDGET")
        return result
    initial_objective=None
    for weight in settings["barrier_weights"]:
        for iteration in range(settings["max_iterations_per_stage"]+1):
            value,g,h,certificate=evaluate(x,weight,True)
            if initial_objective is None: initial_objective=certificate["objective"]
            if not isfinite(value) or any(not isfinite(v) for v in g):
                raise ValueError("NONFINITE_CONSTRAINED_OBJECTIVE")
            norm=max(abs(v) for v in g)
            if norm<=settings["stationarity_tolerance"]:
                stages.append({"weight":weight,"steps":iteration,"stationarity_inf":norm})
                break
            if iteration==settings["max_iterations_per_stage"]:
                raise ValueError("CONSTRAINED_ITERATION_BUDGET")
            damping=0.0;direction=None
            for attempt in range(settings["max_damping_attempts"]):
                try:
                    candidate=cholesky_direction(h,g,damping)
                    slope=fsum(a*b for a,b in zip(g,candidate))
                    if not isfinite(slope) or slope>=0: raise ArithmeticError("NON_DESCENT")
                    direction=candidate;break
                except ArithmeticError:
                    damping=settings["damping_start"] if damping==0 else damping*settings["damping_growth"]
            if direction is None: raise ValueError("CONSTRAINED_HESSIAN_UNAVAILABLE")
            max_damping=max(max_damping,damping)
            step=1.0
            for _ in range(settings["max_line_search_steps"]):
                trial=[a+step*b for a,b in zip(x,direction)]
                try:
                    fv,_,_,_=evaluate(trial,weight,False)
                    if isfinite(fv) and fv<=value+settings["armijo"]*step*slope:
                        x=trial;total_steps+=1;break
                except Infeasible:
                    pass
                step*=.5
            else: raise ValueError("CONSTRAINED_LINE_SEARCH_UNAVAILABLE")
    _,g,_,certificate=evaluate(x,settings["barrier_weights"][-1],False)
    if (certificate["minimum_slack"]<=0 or not certificate["dual_feasible"]
            or max(abs(v) for v in g)>settings["stationarity_tolerance"]
            or certificate["complementarity_inf"]>settings["complementarity_inf_tolerance"]):
        raise ValueError("CONSTRAINED_KKT_FAILED")
    return x,{"converged":True,"criterion":"LOCAL_APPROXIMATE_KKT","certificate":certificate,
              "initial_objective":initial_objective,"steps":total_steps,"evaluations":evaluations,
              "maximum_hessian_damping":max_damping,"stages":stages}
