"""Deterministic Decimal-only governance metrics."""

from decimal import Decimal, localcontext
from statistics import median


def d(value)->Decimal:return value if isinstance(value,Decimal) else Decimal(str(value))


def predictive(rows):
    settled=[row for row in rows if row.get("outcome") in {"WON","LOST"} and row.get("probability") is not None]
    if not settled:return {"sample_size":0,"brier_score":None,"log_loss":None,"accuracy":None,"hit_rate":None,"predicted_probability_mean":None,"observed_outcome_rate":None,"probability_bias":None}
    probabilities=[d(row["probability"]) for row in settled]; outcomes=[Decimal(1) if row["outcome"]=="WON" else Decimal(0) for row in settled];n=Decimal(len(settled));epsilon=Decimal("0.000000000001")
    with localcontext() as context:
        context.prec=40
        clipped=[min(Decimal(1)-epsilon,max(epsilon,p)) for p in probabilities]
        brier=sum(((p-y)**2 for p,y in zip(probabilities,outcomes)),Decimal(0))/n
        loss=-sum((y*p.ln()+(Decimal(1)-y)*(Decimal(1)-p).ln() for p,y in zip(clipped,outcomes)),Decimal(0))/n
    observed=sum(outcomes,Decimal(0))/n;predicted=sum(probabilities,Decimal(0))/n;accuracy=sum((int((p>=Decimal("0.5"))==bool(y)) for p,y in zip(probabilities,outcomes)),0)
    buckets=[]
    for lower in (Decimal("0"),Decimal("0.5"),Decimal("0.6"),Decimal("0.7"),Decimal("0.8"),Decimal("0.9")):
        upper=Decimal("0.5") if lower==0 else lower+Decimal("0.1");pairs=[(p,y) for p,y in zip(probabilities,outcomes) if lower<=p<(upper if upper<1 else Decimal("1.0000001"))]
        if pairs:buckets.append({"lower":str(lower),"upper":str(upper),"count":len(pairs),"predicted_mean":str(sum((p for p,_ in pairs),Decimal(0))/Decimal(len(pairs))),"observed_rate":str(sum((y for _,y in pairs),Decimal(0))/Decimal(len(pairs)))})
    return {"sample_size":len(settled),"brier_score":str(brier),"log_loss":str(loss),"accuracy":str(Decimal(accuracy)/n),"hit_rate":str(observed),"predicted_probability_mean":str(predicted),"observed_outcome_rate":str(observed),"probability_bias":str(predicted-observed),"expected_successes":str(sum(probabilities,Decimal(0))),"observed_successes":str(sum(outcomes,Decimal(0))),"confidence_buckets":buckets}


def calibration(rows,bin_count=10):
    settled=[row for row in rows if row.get("outcome") in {"WON","LOST"} and row.get("probability") is not None];bins=[]
    for index in range(bin_count):
        lower=Decimal(index)/Decimal(bin_count);upper=Decimal(index+1)/Decimal(bin_count);values=[row for row in settled if d(row["probability"])>=lower and (d(row["probability"])<upper or index==bin_count-1)]
        if not values:continue
        confidence=sum((d(row["probability"]) for row in values),Decimal(0))/Decimal(len(values));observed=sum((Decimal(1) if row["outcome"]=="WON" else Decimal(0) for row in values),Decimal(0))/Decimal(len(values));gap=abs(confidence-observed);bins.append({"lower":str(lower),"upper":str(upper),"count":len(values),"mean_probability":str(confidence),"observed_rate":str(observed),"gap":str(gap)})
    total=Decimal(len(settled));ece=sum((d(item["gap"])*Decimal(item["count"])/total for item in bins),Decimal(0)) if total else None;mce=max((d(item["gap"]) for item in bins),default=None)
    bias=d(predictive(rows)["probability_bias"]) if settled else None
    adjustments=[d(row["probability"])-d(row["raw_probability"]) for row in settled if row.get("raw_probability") is not None]
    return {"sample_size":len(settled),"ece":str(ece) if ece is not None else None,"mce":str(mce) if mce is not None else None,"bias":str(bias) if bias is not None else None,"overconfidence":bool(bias is not None and bias>0),"underconfidence":bool(bias is not None and bias<0),"extreme_probability_failure_rate":str(Decimal(sum(d(row["probability"])>=Decimal("0.85") and row["outcome"]=="LOST" for row in settled))/total) if total else None,"mean_calibration_adjustment":str(sum(adjustments,Decimal(0))/Decimal(len(adjustments))) if adjustments else None,"adjustment_direction":{"UP":sum(x>0 for x in adjustments),"DOWN":sum(x<0 for x in adjustments),"UNCHANGED":sum(x==0 for x in adjustments)},"reliability_bins":bins}


def distribution(values):
    numbers=sorted(d(value) for value in values if value is not None)
    if not numbers:return {"count":0,"mean":None,"median":None,"standard_deviation":None,"q25":None,"q75":None,"minimum":None,"maximum":None}
    mean=sum(numbers,Decimal(0))/Decimal(len(numbers));variance=sum(((value-mean)**2 for value in numbers),Decimal(0))/Decimal(len(numbers));q=lambda ratio:numbers[min(len(numbers)-1,int((len(numbers)-1)*ratio))]
    return {"count":len(numbers),"mean":str(mean),"median":str(median(numbers)),"standard_deviation":str(variance.sqrt()),"q25":str(q(.25)),"q75":str(q(.75)),"minimum":str(numbers[0]),"maximum":str(numbers[-1])}


def psi(current,baseline,bins=10):
    current=[d(x) for x in current if x is not None];baseline=[d(x) for x in baseline if x is not None]
    if len(current)<2 or len(baseline)<2:return None
    low=min(current+baseline);high=max(current+baseline)
    if high==low:return Decimal(0)
    width=(high-low)/Decimal(bins);epsilon=Decimal("0.000001");total=Decimal(0)
    with localcontext() as context:
        context.prec=40
        for index in range(bins):
            left=low+width*index;right=high if index==bins-1 else left+width
            cp=Decimal(sum(value>=left and (value<right or index==bins-1) for value in current))/Decimal(len(current));bp=Decimal(sum(value>=left and (value<right or index==bins-1) for value in baseline))/Decimal(len(baseline));cp=max(cp,epsilon);bp=max(bp,epsilon);total+=(cp-bp)*(cp/bp).ln()
    return total
