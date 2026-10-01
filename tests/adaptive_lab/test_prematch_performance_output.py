"""Scheduled output remains readable without truncating immutable audit evidence."""
from copy import deepcopy
from app.adaptive_lab import prematch

def test_observer_stdout_projects_only_performance(monkeypatch, capsys, tmp_path):
    full = {"PERFORMANCE": {"status":"COMPLETE", "as_of":"2026-10-01T19:00:00+00:00",
             "SINGLE":{"WON":2,"LOST":1,"pending":5},
             "COMBO":{"WON":1,"LOST":3,"pending":2},
             "segments":{"SINGLE":[{"dimension":"league","value":str(i)} for i in range(20000)]}},
             "LIVE":"DISABLED", "api_calls":0, "telegram_sends":0}
    original = deepcopy(full)
    class Repo:
        def __init__(self,*args,**kwargs): pass
        def close(self): pass
    monkeypatch.setattr(prematch,"AuditRepository",Repo)
    monkeypatch.setattr(prematch,"ReadOnlyLedger",Repo)
    monkeypatch.setattr("app.adaptive_lab.observer.observe",lambda *a,**k:full)
    assert prematch.main(["observe","--database",str(tmp_path/"a.db"),"--ledger",str(tmp_path/"b.db")])==0
    import json
    output = capsys.readouterr().out
    assert len(output.encode())<8192
    result=json.loads(output)
    assert result["PERFORMANCE"]["SINGLE"]["WON"]==2
    assert result["PERFORMANCE"]["segment_counts"]["SINGLE"]==20000
    assert full==original
    assert prematch.main(["observe","--database",str(tmp_path/"a.db"),"--ledger",str(tmp_path/"b.db"),"--full-performance"])==0
    result=json.loads(capsys.readouterr().out)
    assert result==original
