"""SQLite/source/CLI integrations use disposable copies and immutable inputs."""
from copy import deepcopy
from datetime import timedelta
import json
import sqlite3
from pathlib import Path
import pytest
from app.dixon_coles_research import sources,cli
from app.dixon_coles_research.contracts import seal,digest,canonical,load_plan,utc
from app.dixon_coles_research.repository import ResearchStore
from app.dixon_coles_research.service import intake,forecast
from app.dixon_coles_research.metrics import evaluate
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.real_match_lab_analysis.fingerprint import fingerprint
from tests.test_dixon_coles_research import PLAN,START,history,item,result

def databases(tmp_path,*,capture_change=None,candidate_change=None,cache_list=False):
    shadow=tmp_path/"shadow.db";audit=tmp_path/"audit.db"
    source=item()
    if capture_change: capture_change(source)
    repo=ShadowEvidenceRepository(shadow)
    for market,candidate in source["candidates"].items():
        candidate=deepcopy(candidate)
        if candidate_change: candidate_change(candidate)
        repo.append("candidate",candidate["candidate_id"],candidate,created_at=START)
    cap=source["capture"]
    repo.append("devig_research",cap["capture_id"],cap,created_at=utc(cap["captured_at"]))
    # Same immutable cache representation as the natural discovery process.
    payload={"response":[{"fixture":{"id":r["fixture_id"],"date":r["kickoff_utc"],"status":{"short":"FT"}},
                          "league":{"id":r["league_id"]},"teams":{"home":{"id":r["home_team_id"]},"away":{"id":r["away_team_id"]}},
                          "score":{"fulltime":{"home":r["home_goals"],"away":r["away_goals"]}}}
                         for r in history()[-99:]]}
    query={"league":71,"season":2026,"status":"FT","last":99}
    repo.append_cache("/fixtures(results)",query,payload["response"] if cache_list else payload,retrieved_at=START-timedelta(minutes=1),ttl=timedelta(hours=6))
    repo.close()
    with sqlite3.connect(audit) as c:
        c.execute("CREATE TABLE holdout_results(id TEXT,stream TEXT,fingerprint TEXT,document TEXT)")
        c.execute("CREATE TABLE learning_observations(id TEXT,stream TEXT,fingerprint TEXT,document TEXT)")
        c.execute("CREATE TABLE canonical_results(id TEXT,stream TEXT,created_at TEXT,fingerprint TEXT,document TEXT)")
    return shadow,audit

@pytest.mark.parametrize("cache_list",[False,True])
def test_snapshot_ro_fingerprints_history_clock_and_no_source_mutation(tmp_path,cache_list):
    shadow,audit=databases(tmp_path,cache_list=cache_list)
    before={p:p.read_bytes() for p in (shadow,audit)}
    data=sources.snapshot(shadow,audit,plan=PLAN,now=START+timedelta(seconds=1))
    assert len(data["items"])==1 and data["read_only"] is True and data["provider_calls"]==0
    rows=data["items"][0]["training_results"]
    assert len(rows)==99 and all(r["observed_at_utc"]==(START-timedelta(minutes=1)).isoformat() for r in rows)
    assert all(before[p]==p.read_bytes() for p in before)
    with sources.readonly(shadow) as c:
        with pytest.raises(sqlite3.OperationalError): c.execute("DELETE FROM lab_v2_shadow_evidence")

def test_consumed_holdout_is_resolved_by_reference_and_excluded(tmp_path):
    shadow,audit=databases(tmp_path)
    observation={"fixture_id":9000};holdout={"observation_ids":["o"]}
    with sqlite3.connect(audit) as c:
        c.execute("INSERT INTO learning_observations VALUES(?,?,?,?)",("o","PREMATCH",digest(observation),canonical(observation)))
        c.execute("INSERT INTO holdout_results VALUES(?,?,?,?)",("h","PREMATCH",digest(holdout),canonical(holdout)))
    assert sources.consumed_holdout_fixtures(audit)==frozenset({9000})
    data=sources.snapshot(shadow,audit,plan=PLAN,now=START)
    assert not data["items"] and data["diagnostics"]["reserved_holdout"]==1
    with sqlite3.connect(audit) as c: c.execute("DELETE FROM learning_observations")
    with pytest.raises(ValueError,match="HOLDOUT_REFERENCE_MISSING"): sources.consumed_holdout_fixtures(audit)

def test_snapshot_rejects_altered_candidate_provenance(tmp_path):
    shadow,audit=databases(tmp_path,candidate_change=lambda c:c.update(home_team_id=999))
    with pytest.raises(ValueError,match="MODEL_REFERENCE_INTEGRITY"):
        sources.snapshot(shadow,audit,plan=PLAN,now=START)

def test_cache_future_result_snapshot_never_used(tmp_path):
    shadow,audit=databases(tmp_path)
    # Append a later conflicting current-season snapshot; the capture sees the older one.
    repo=ShadowEvidenceRepository(shadow)
    repo.append_cache("/fixtures(results)",{"league":71,"season":2026,"status":"FT","last":99},
                      {"response":[]},retrieved_at=START+timedelta(seconds=1),ttl=timedelta(hours=6));repo.close()
    assert len(sources.snapshot(shadow,audit,plan=PLAN,now=START)["items"][0]["training_results"])==99

@pytest.mark.parametrize("delay,reason",[(901,"stale_capture"),(3601,"not_upcoming_evaluation")])
def test_snapshot_retains_explicit_stale_and_postkickoff_counts(tmp_path,delay,reason):
    shadow,audit=databases(tmp_path)
    data=sources.snapshot(shadow,audit,plan=PLAN,now=START+timedelta(seconds=delay))
    assert not data["items"] and data["diagnostics"][reason]==1

def test_foreign_or_symlink_outputs_do_not_touch_sources(tmp_path):
    shadow,audit=databases(tmp_path)
    alias=tmp_path/"alias.db";alias.symlink_to(shadow)
    before=shadow.read_bytes()
    with pytest.raises(ValueError,match="SYMLINK"): ResearchStore(alias)
    with pytest.raises(ValueError,match="PRODUCTION"): ResearchStore(shadow,protected_paths=(shadow,audit))
    assert shadow.read_bytes()==before

def test_result_reader_skips_combo_legs_and_merges_existing_canonical(tmp_path):
    shadow,audit=databases(tmp_path);ledger=tmp_path/"ledger.db"
    row={"fixture_id":9000,"status":"WON","provider_status":"FT","fulltime_home":1,"fulltime_away":0,
         "settled_at_utc":(START+timedelta(hours=3)).isoformat(),"source_fingerprint":"controlled"}
    with sqlite3.connect(ledger) as c:
        c.execute("CREATE TABLE evidence(kind TEXT,identity TEXT,fingerprint TEXT,document TEXT)")
        c.execute("INSERT INTO evidence VALUES(?,?,?,?)",("single_settlement","s",fingerprint(row),canonical(row)))
        c.execute("INSERT INTO evidence VALUES(?,?,?,?)",("leg_result","l",fingerprint(row),canonical(row)))
    with sqlite3.connect(audit) as c:
        c.execute("INSERT INTO canonical_results VALUES(?,?,?,?,?)",("c","PREMATCH",(START+timedelta(hours=3)).isoformat(),digest(row),canonical(row)))
    assert sources.results(ledger,audit,fixture_ids={9000},now=START)==[]
    read=sources.results(ledger,audit,fixture_ids={9000},now=START+timedelta(days=1))
    assert len(read)==2 and {v["source_product"] for v in read}=={"SINGLE","SHADOW"}

def test_full_source_to_forecast_replay_and_result_evaluation(tmp_path):
    shadow,audit=databases(tmp_path)
    before={p:p.read_bytes() for p in (shadow,audit)}
    snapshot=sources.snapshot(shadow,audit,plan=PLAN,now=START)
    store=ResearchStore(tmp_path/"dc.db",protected_paths=(shadow,audit))
    report=intake(snapshot,store,plan=PLAN,clock=lambda:START+timedelta(seconds=2))
    assert report["counts"]=={"forecast":1}
    values=store.all("forecast");models={m["fingerprint"]:m for m in store.all("model")}
    output=evaluate(values,models,[result()],plan=PLAN,now=START+timedelta(days=1))
    assert output["overall"]["fixtures"]==1 and output["overall"]["common_market_rows"]==3
    assert intake(snapshot,store,plan=PLAN,clock=lambda:START+timedelta(seconds=3))["counts"]=={"already_forecast":1}
    assert all(p.read_bytes()==before[p] for p in before)
    store.close()

def test_cli_readiness_never_creates_research_database_or_raises_priority(tmp_path,monkeypatch,capsys):
    shadow,audit=databases(tmp_path);destination=tmp_path/"never.db"
    monkeypatch.setattr(cli,"snapshot",lambda *a,**k:{"items":[],"diagnostics":{"waiting":1}})
    priorities=[]
    monkeypatch.setattr(cli.os,"getpriority",lambda *a:15)
    monkeypatch.setattr(cli.os,"nice",lambda v:priorities.append(v))
    code=cli.main(["readiness","--shadow-database",str(shadow),"--audit-database",str(audit),
                   "--research-database",str(destination)])
    assert code==0 and not destination.exists() and priorities==[]
    assert json.loads(capsys.readouterr().out)["priority"]=="NORMAL"

def test_cli_limits_own_cpu_without_mutating_systemd(tmp_path,monkeypatch,capsys):
    shadow,audit=databases(tmp_path)
    monkeypatch.setattr(cli,"snapshot",lambda *a,**k:{"items":[],"diagnostics":{}})
    priorities=[]
    monkeypatch.setattr(cli.os,"getpriority",lambda *a:0)
    monkeypatch.setattr(cli.os,"nice",lambda v:priorities.append(v))
    assert cli.main(["readiness","--shadow-database",str(shadow),"--audit-database",str(audit)])==0
    assert priorities==[10]

def test_fixed_plan_rejects_resealed_calendar_or_policy_changes():
    from app.dixon_coles_research.contracts import verify_plan
    for key,value in (("train_end",PLAN["evaluation_end"]),("selection_effect","ENABLED"),("priority","MAX")):
        changed=deepcopy(PLAN);changed.pop("fingerprint");changed[key]=value
        with pytest.raises(ValueError): verify_plan(seal(changed))

def test_cli_missing_source_is_blocked_without_file_creation(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(cli.os,"getpriority",lambda *a:15)
    missing=tmp_path/"missing.db"
    code=cli.main(["readiness","--shadow-database",str(missing),"--audit-database",str(missing)])
    assert code==2 and not missing.exists()
    report=json.loads(capsys.readouterr().out)
    assert report["status"]=="BLOCKED" and report["selection_effect"]=="NONE"
