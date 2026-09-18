"""Reviewed deterministic model registry. JSON artifacts contain no executable code.

The search may replace a full classifier, select features/interactions and learn
profile/market residuals. No eval, pickle, dynamic import or source generation.
"""
from __future__ import annotations
from math import exp, log, sqrt
from statistics import mean, median
from .contracts import canonical, digest, number
from .features import BASE_FEATURES, CONTEXT_FEATURES, LIVE_FEATURES, SAFE_FEATURES, FEATURE_SCHEMA, features
from .policy import POLICY

REGISTRY_VERSION = 'LAB_MODEL_REGISTRY_V1'
FAMILIES = ('LOGISTIC','REGULARIZED_LOGISTIC','STUMP_ENSEMBLE','CALIBRATED_ENSEMBLE')


def validate_spec(spec: dict) -> None:
    if set(spec) != {'family','features','interactions','l2','learning_rate','iterations','half_life_days',
                     'history_days','scope','seed','registry_version','feature_schema'}:
        raise ValueError('MODEL_SPEC_KEYS_INVALID')
    if spec['family'] not in FAMILIES or spec['registry_version'] != REGISTRY_VERSION or spec['feature_schema'] != FEATURE_SCHEMA:
        raise ValueError('UNREVIEWED_MODEL_FAMILY')
    if not 1 <= len(spec['features']) <= 24 or len(set(spec['features'])) != len(spec['features']) or not set(spec['features']) <= SAFE_FEATURES:
        raise ValueError('FEATURE_SELECTION_INVALID')
    if len(spec['interactions']) > 4 or any(len(pair)!=2 or not set(pair)<=set(spec['features']) for pair in spec['interactions']):
        raise ValueError('INTERACTION_INVALID')
    if spec['scope'] not in {'GLOBAL','PROFILE','MARKET','PROFILE_MARKET'}:
        raise ValueError('SCOPE_INVALID')
    if (spec['seed'] != POLICY.seed or spec['iterations'] not in (50,100,150) or
        spec['half_life_days'] not in (0,60,180) or spec['history_days'] not in (0,180,365) or
        spec['l2'] not in (0.,.01,.1,1.) or spec['learning_rate'] not in (.03,.1)):
        raise ValueError('HYPERPARAMETER_OUT_OF_BOUNDS')


def candidate_specs(stream: str) -> list[dict]:
    """A bounded reviewed search grid; no holdout or targets influence generation."""
    basic = list(BASE_FEATURES)
    contextual = basic + list(CONTEXT_FEATURES[:12])
    if stream == 'LIVE':
        basic += list(LIVE_FEATURES[:5])
        contextual = basic + list(LIVE_FEATURES[5:])
    output = []
    for family in FAMILIES:
        for names in (basic, contextual):
            for l2 in (.01,.1):
                for decay in (0,180):
                    spec = dict(family=family,features=names,interactions=[],l2=l2,learning_rate=.1,
                        iterations=150,half_life_days=decay,history_days=0,scope='GLOBAL',seed=POLICY.seed,
                        registry_version=REGISTRY_VERSION,feature_schema=FEATURE_SCHEMA)
                    validate_spec(spec)
                    output.append(spec)
    for scope in ('PROFILE','MARKET','PROFILE_MARKET'):
        spec = {**output[0],'scope':scope,'interactions':[['prior_probability','implied_probability']]}
        output.append(spec)
    output.extend([{**output[0],'history_days':180},{**output[0],'history_days':365}])
    return sorted({digest(s):s for s in output}.values(),key=digest)[:POLICY.candidate_limit]


def _sigmoid(z: float) -> float:
    return 1/(1+exp(-max(-30,min(30,z))))


def _logit(p: float) -> float:
    p = max(1e-8,min(1-1e-8,p))
    return log(p/(1-p))


def _raw(row: dict, spec: dict) -> list[float | None]:
    raw = features(row)
    values = [raw[k] for k in spec['features']]
    for a,b in spec['interactions']:
        values.append(None if raw[a] is None or raw[b] is None else raw[a]*raw[b])
    return values


def _transform(values: list[float | None], preprocessing: list[dict]) -> list[float]:
    result = []
    for v, params in zip(values,preprocessing,strict=True):
        result.extend([max(-10,min(10,((params['median'] if v is None else v)-params['mean'])/params['scale'])),float(v is None)])
    return result


def scope_key(row: dict, scope: str) -> str:
    if scope == 'PROFILE':
        return str(row.get('competition_profile'))
    if scope == 'MARKET':
        return row['market']
    return str(row.get('competition_profile'))+'|'+row['market']


def train(spec: dict, rows: list[dict]) -> dict:
    """Fit only caller's TRAIN partition with a hard row and iteration budget."""
    from .contracts import utc
    validate_spec(spec)
    rows = [r for r in rows if r['target'] is not None]
    if not rows or len(rows)>POLICY.training_rows_limit or len({r['stream'] for r in rows})!=1:
        raise ValueError('TRAINING_RESOURCE_OR_STREAM_CONTRACT')
    latest = max(utc(r['prediction_created_at']) for r in rows)
    if spec['history_days']:
        rows = [r for r in rows if (latest-utc(r['prediction_created_at'])).days <= spec['history_days']]
    if spec['family'] == 'CALIBRATED_ENSEMBLE' and len(rows) < POLICY.calibration_min:
        raise ValueError('CALIBRATION_SAMPLE_INSUFFICIENT')
    y = [r['target'] for r in rows]
    if set(y)!={0,1}:
        raise ValueError('TRAIN_CLASS_DIVERSITY_REQUIRED')
    raw = [_raw(r,spec) for r in rows]
    preprocessing = []
    for column in zip(*raw):
        available = [v for v in column if v is not None]
        med = median(available) if available else 0.
        imputed = [med if v is None else v for v in column]
        avg = mean(imputed)
        scale = sqrt(mean((v-avg)**2 for v in imputed)) or 1.
        preprocessing.append({'median':med,'mean':avg,'scale':scale,'all_missing':not available})
    x = [_transform(row,preprocessing) for row in raw]
    weights = [2**(-(latest-utc(r['prediction_created_at'])).total_seconds()/86400/spec['half_life_days'])
               if spec['half_life_days'] else 1. for r in rows]
    total_weight = sum(weights)
    bias = _logit((sum(y)+1)/(len(y)+2))
    coefficients = [0.]*len(x[0])
    stumps = []
    if spec['family']=='STUMP_ENSEMBLE':
        for j in range(len(x[0])):
            values = sorted({v[j] for v in x})
            for fraction in (.25,.5,.75):
                threshold = values[min(len(values)-1,int(len(values)*fraction))]
                left = [i for i,v in enumerate(x) if v[j]<=threshold]
                right = [i for i,v in enumerate(x) if v[j]>threshold]
                if min(len(left),len(right)) < 10:
                    continue
                lp=(sum(weights[i]*y[i] for i in left)+1)/(sum(weights[i] for i in left)+2)
                rp=(sum(weights[i]*y[i] for i in right)+1)/(sum(weights[i] for i in right)+2)
                error=sum(weights[i]*((lp if x[i][j]<=threshold else rp)-y[i])**2 for i in range(len(y)))
                stumps.append({'feature':j,'threshold':threshold,'left':lp,'right':rp,'error':error})
        stumps = sorted(stumps,key=lambda s:(s['error'],s['feature'],s['threshold']))[:8]
        if not stumps:
            raise ValueError('NO_VALID_STUMP')
    else:
        for _ in range(spec['iterations']):
            errors=[(_sigmoid(bias+sum(a*b for a,b in zip(v,coefficients)))-target)*w
                    for v,target,w in zip(x,y,weights)]
            bias -= spec['learning_rate']*sum(errors)/total_weight
            for j in range(len(coefficients)):
                penalty = 0 if spec['family']=='LOGISTIC' else spec['l2']*coefficients[j]
                coefficients[j] -= spec['learning_rate']*(sum(e*v[j] for e,v in zip(errors,x))/total_weight+penalty)
    artifact={'spec':spec,'stream':rows[0]['stream'],'preprocessing':preprocessing,'bias':bias,
              'coefficients':coefficients,'stumps':stumps,'specialists':{},
              'training_fingerprint':digest([(r['observation_id'],r['observation_fingerprint']) for r in rows])}
    if spec['scope']!='GLOBAL':
        for key in sorted({scope_key(r,spec['scope']) for r in rows}):
            group=[r for r in rows if scope_key(r,spec['scope'])==key]
            days=(max(utc(r['prediction_created_at']) for r in group)-min(utc(r['prediction_created_at']) for r in group)).days
            odds_bands={int(number(r['offered_decimal_odds'])*2) for r in group}
            if (len(group)>=POLICY.specialized_min and days>=POLICY.specialized_days and
                min(sum(r['target'] for r in group),sum(1-r['target'] for r in group))>=20 and len(odds_bands)>=3):
                # Partial pooling: bounded logit residual fitted only to TRAIN.
                baseline=mean(predict(artifact,r) for r in group)
                observed=(sum(r['target'] for r in group)+20*baseline)/(len(group)+20)
                artifact['specialists'][key]=max(-1,min(1,_logit(observed)-_logit(baseline)))
    artifact['artifact_fingerprint']=digest(artifact)
    validate_artifact(artifact)
    return artifact


def validate_artifact(artifact: dict) -> None:
    validate_spec(artifact['spec'])
    material={k:v for k,v in artifact.items() if k!='artifact_fingerprint'}
    if digest(material)!=artifact.get('artifact_fingerprint'):
        raise ValueError('ARTIFACT_INTEGRITY_FAILURE')
    canonical(artifact)
    allowed={'spec','stream','preprocessing','bias','coefficients','stumps','specialists',
             'training_fingerprint','artifact_fingerprint'}
    if set(artifact)!=allowed or artifact['stream'] not in {'PREMATCH','LIVE'}:
        raise ValueError('ARTIFACT_SCHEMA_INVALID')
    width=len(artifact['spec']['features'])+len(artifact['spec']['interactions'])
    if len(artifact['preprocessing'])!=width or len(artifact['coefficients'])!=width*2:
        raise ValueError('ARTIFACT_DIMENSION_INVALID')
    for params in artifact['preprocessing']:
        if set(params)!={'median','mean','scale','all_missing'} or type(params['all_missing']) is not bool:
            raise ValueError('ARTIFACT_PREPROCESSING_INVALID')
        number(params['median']); number(params['mean'])
        if number(params['scale'],low=0)<=0:
            raise ValueError('ARTIFACT_SCALE_INVALID')
    if len(artifact['stumps'])>8 or len(artifact['specialists'])>1000:
        raise ValueError('ARTIFACT_RESOURCE_BOUND')
    for stump in artifact['stumps']:
        if set(stump)!={'feature','threshold','left','right','error'} or type(stump['feature']) is not int or not 0<=stump['feature']<width*2:
            raise ValueError('ARTIFACT_STUMP_INVALID')
        number(stump['threshold']); number(stump['error'],low=0)
        for key in ('left','right'):
            if not 0<number(stump[key],low=0,high=1)<1:
                raise ValueError('ARTIFACT_STUMP_PROBABILITY_INVALID')
    if artifact['spec']['family']=='STUMP_ENSEMBLE' and not artifact['stumps']:
        raise ValueError('ARTIFACT_STUMP_REQUIRED')
    for v in [artifact['bias'],*artifact['coefficients'],*artifact['specialists'].values()]:
        number(v,low=-1e6,high=1e6)


def predict(artifact: dict, row: dict) -> float:
    """One full predictive model per stream; no transport or threshold logic."""
    if 'artifact_fingerprint' in artifact:
        validate_artifact(artifact)
    if row['stream']!=artifact['stream']:
        raise ValueError('MODEL_STREAM_MISMATCH')
    x=_transform(_raw(row,artifact['spec']),artifact['preprocessing'])
    if artifact['spec']['family']=='STUMP_ENSEMBLE':
        p=mean(s['left'] if x[s['feature']]<=s['threshold'] else s['right'] for s in artifact['stumps'])
    else:
        p=_sigmoid(artifact['bias']+sum(a*b for a,b in zip(x,artifact['coefficients'],strict=True)))
        if artifact['spec']['family']=='CALIBRATED_ENSEMBLE':
            p=(p+number(row['frozen_model_probability'],low=0,high=1))/2
    offset=artifact['specialists'].get(scope_key(row,artifact['spec']['scope']),0)
    result=_sigmoid(_logit(p)+offset)
    if not 0<result<1:
        raise ValueError('PROBABILITY_CONTRACT_VIOLATION')
    return result
