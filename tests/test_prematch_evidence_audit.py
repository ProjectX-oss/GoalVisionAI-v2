"""Audit denominators and privacy boundaries, without production access."""
import importlib.util
import json
from pathlib import Path
import sqlite3


def module(name):
    p=Path(__file__).parents[1]/'operations/prematch-evidence'/f'{name}.py'
    spec=importlib.util.spec_from_file_location('audit_'+name,p)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def test_stale_rates_use_odds_scope_not_closed_discovered_fixtures():
    cycle={'evaluated_at_utc':'2026-10-06T09:30:00+00:00','fixtures_discovered':4,
           'global_fixture_states':[], 'odds_pagination':{'fixture_coverage_reasons':{'1':'ODDS_STALE','2':'ODDS_COMPLETE_SWEEP_NO_FIXTURE_RECORD'},
             'coverage_by_date':{'2026-10-06':{'stable_complete_sweep':True}}},
           'api_calls_consumed':3,'exact_fixture_odds_refresh_calls':1,'api_call_allocation':{'/odds(date)':1}}
    result=module('diagnostics').queue_and_odds([cycle])['quality_cycles'][0]
    assert result['stale_rate']==result['missing_rate']==.5
    assert result['odds_scope_fixtures']==2 and result['discovered']==4


def test_reason_counts_deduplicate_same_reason_in_hard_soft_lists():
    row={'fixture_id':1,'market':'HOME_WIN','ensemble_probability':'.6','market_fair_probability':'.4',
         'captured_odds':'1.8','kickoff_utc':'2026-10-06T10:30:00+00:00',
         'evaluated_at_utc':'2026-10-06T09:30:00+00:00',
         'provider_origin_timestamp_utc':'2026-10-06T09:20:00+00:00',
         'hard_failures':['SEVERE_MODEL_MARKET_CONTRADICTION'],
         'rejection_reasons':['SEVERE_MODEL_MARKET_CONTRADICTION']}
    r=module('diagnostics').disagreements([row])
    assert r['reason_counts']['SEVERE_MODEL_MARKET_CONTRADICTION']==1
    groups={(v['dimension'],v['value']):v for v in r['segments']}
    assert groups['lead_time','[45,90)']['candidate_rows']==1
    assert groups['freshness','[300,900)']['candidate_rows']==1


def test_unknown_delivery_is_not_counted_as_published_or_automatically_retried(tmp_path):
    path=tmp_path/'ledger.db';db=sqlite3.connect(path)
    db.execute('CREATE TABLE evidence(kind TEXT, identity TEXT, document TEXT)')
    for kind,key,v in [('claim','combo_prediction:lost-receipt',{'chat_id':'PRIVATE','message':'SECRET'}),
                        ('delivery_unknown','combo_prediction:lost-receipt',{'status':'UNKNOWN'}),
                        ('prediction','lost-receipt',{'prediction_id':'lost-receipt','created_at_utc':'2026-10-05T09:00:00+00:00'})]:
        db.execute('INSERT INTO evidence VALUES(?,?,?)',(kind,key,json.dumps(v)))
    db.commit();db.close()
    r=module('publication_audit').ledger_audit(path,'2026-10-06T10:00:00+00:00')
    assert r['current_claims_without_receipt']==1
    assert r['current_missing_receipt_details'][0]['unknown_marker_present']
    assert r['confirmed_publications_asof']['COMBO']==0
    assert 'PRIVATE' not in json.dumps(r) and 'SECRET' not in json.dumps(r)
