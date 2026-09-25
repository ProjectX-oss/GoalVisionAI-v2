"""Offline integration: genuine renewed reviews; explicitly synthetic clocks/football."""
from contextlib import closing, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import socket
import sqlite3

import httpx
import pytest

from app.prematch_football_context.fingerprint import canonical_bytes
from app.prematch_football_context.readiness.__main__ import initialize, main
from app.prematch_football_context.readiness.composition import ProspectiveObservation
from app.prematch_football_context.readiness.ledger import Ledger
from app.prematch_football_context.readiness.report import coverage
from app.prematch_football_context.readiness.regulations import verify_retained
from app.prematch_football_context.regulation_registry import Registry, initialize as init_registry
from app.prematch_football_context.regulation_registry.__main__ import main as registry_cli
from app.prematch_football_context.regulation_registry.contracts import decode
from app.prematch_football_context.snapshot.service import reproduce
from tests.test_prematch_football_context_readiness import ROW, ID
from tests.test_prematch_football_context_sources import T, raw
from tests.test_prematch_football_context_regulation_registry import record, append

EVIDENCE = Path(__file__).resolve().parents[1]/'docs/rehearsals/ucl_2026_regulation_renewed'


def renewed_registry(path: Path) -> datetime:
    """Import exact genuine reviews through existing CLI; return a TEST clock."""
    with redirect_stdout(io.StringIO()):
        assert registry_cli(['init', '--db', str(path)]) == 0
        for name in ('ifab.json', 'uefa.json'):
            assert registry_cli(['import', '--db', str(path), str(EVIDENCE/name)]) == 0
    records = tuple(decode((EVIDENCE/name).read_text()) for name in ('ifab.json', 'uefa.json'))
    return max(r.reviewed_at for r in records)+timedelta(hours=1)


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        pytest.fail('NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', fail)
    monkeypatch.setattr(socket, 'create_connection', fail)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', fail)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', fail)


def start(root: Path, registry: Path | None, clock, competition: int = 10) -> ProspectiveObservation:
    initialize(root)
    o = ProspectiveObservation(root, environment='TEST', clock=clock, regulation_registry=registry)
    o.prepare(((9999, competition, *ROW[2:]),))
    return o


def decide(o: ProspectiveObservation, competition: int = 10, *, market: str = 'HOME_WIN', target: bool = True):
    now = o.clock()
    if target:
        payload = raw(9999, status='NS', kickoff=now+timedelta(hours=1))
        payload['league']['id'] = competition
        o.capture('/fixtures', {'id':9999}, [payload], now)
    rows = [raw(i, kickoff=now-timedelta(days=i)) for i in range(1,9)]
    for r in rows: r['league']['id'] = competition
    o.capture('/fixtures', {'league':competition,'season':2026,'status':'FT','last':99}, rows, now)
    decision = replace(ID, competition_id=competition, market=market,
                       candidate_id='lab-v2-candidate-'+('a' if market=='HOME_WIN' else 'b')*64)
    o.bind(o.begin(), (decision,))
    o.observe(decision, new_opportunity=True)
    return o.snapshots.load('9999:'+market)


@pytest.mark.parametrize('case', ['valid','none','empty','expired','equal','late','conflict','missing','corrupt','locked','competition36'])
def test_exact_scope_fail_closed(tmp_path: Path, case: str) -> None:
    db=tmp_path/'registry.db';init_registry(db)
    if case not in ('empty','missing'):
        changes = {'source_effective_until':T} if case=='expired' else {'reviewed_at':T} if case=='equal' else {'reviewed_at':T+timedelta(seconds=1)} if case=='late' else {}
        append(db, record(**changes))
    if case=='conflict': append(db, record(review_id='SYNTHETIC_CONFLICT', regulation_minutes=80))
    if case=='corrupt': db.write_bytes(b'CORRUPT TEST DATABASE')
    if case=='missing': db.unlink()
    lock=None
    if case=='locked':
        lock=sqlite3.connect(db);lock.execute('BEGIN EXCLUSIVE')
    before=db.read_bytes() if db.exists() else None
    try:
        o=start(tmp_path/'readiness',None if case=='none' else db,lambda:T,36 if case=='competition36' else 10)
        s=decide(o,36 if case=='competition36' else 10)
        assert s.binding.current_format.verdict(T)==('VERIFIED_90' if case=='valid' else 'REGULATION_UNVERIFIED')
        assert s.binding.previous_format.verdict(T)=='REGULATION_UNVERIFIED'
        assert s.projection.missing==((0,)*7 if case=='valid' else (1,)*7)
        counts=o.finish(completed=True)
        assert coverage(tmp_path/'readiness')['reproduction']['VERIFIED']==1
        if case in ('missing','corrupt','locked'): assert counts['REGISTRY_VIEW_UNAVAILABLE']==1
    finally:
        if lock: lock.rollback();lock.close()
    assert (db.read_bytes() if db.exists() else None)==before


def test_new_cutoff_expiry_and_later_backdated_import(tmp_path: Path) -> None:
    db=tmp_path/'registry.db';init_registry(db)
    append(db, record(source_effective_until=T+timedelta(seconds=1)))
    now=[T];o=start(tmp_path/'readiness',db,lambda:now[0])
    # Import after pin, with earlier supplied review time. It cannot contaminate this run.
    append(db, record(review_id='SYNTHETIC_LATE_IMPORT',regulation_minutes=80))
    first=decide(o)
    assert first.binding.current_format.verdict(T)=='VERIFIED_90'
    now[0]+=timedelta(seconds=1)
    second=decide(o,market='DRAW')
    assert second.binding.current_format.verdict(now[0])=='REGULATION_UNVERIFIED'
    assert second.receipt!=first.receipt
    o.finish(completed=True)
    assert coverage(tmp_path/'readiness')['reproduction']['VERIFIED']==2


def test_prepare_does_not_freeze_format(tmp_path: Path) -> None:
    db=tmp_path/'registry.db';init_registry(db);append(db,record(source_effective_until=T+timedelta(seconds=1)))
    now=[T];o=start(tmp_path/'readiness',db,lambda:now[0])
    assert o.scopes[9999].current_format.minutes is None
    now[0]+=timedelta(seconds=1)
    assert decide(o).binding.current_format.minutes is None
    o.finish(completed=True)


@pytest.mark.parametrize('kind', ['REGISTRY_VIEW','REGISTRY_ACQUISITION','REGISTRY_DECISION','REGULATION_PROOF','REGULATION_LINK'])
def test_write_interruption_never_leaves_verified_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    db=tmp_path/'registry.db';init_registry(db);append(db,record())
    original=Ledger.append
    def fail(self, event, *args):
        if event==kind: raise OSError('SECRET_TEST_FAILURE')
        return original(self,event,*args)
    monkeypatch.setattr(Ledger,'append',fail)
    o=start(tmp_path/'readiness',db,lambda:T)
    s=decide(o)
    assert s is None or s.binding.current_format.minutes is None
    counts=o.finish(completed=True)
    assert 'SECRET' not in str(counts)
    assert coverage(tmp_path/'readiness')['regulation_counts']['VERIFIED_90']==0


def test_retained_genuine_proof_offline_idempotent_and_scope(tmp_path: Path, capsys) -> None:
    db=tmp_path/'registry.db';now=renewed_registry(db)
    o=start(tmp_path/'readiness',db,lambda:now,2)
    s=decide(o,2)
    assert s.binding.current_format.verdict(now)=='VERIFIED_90'
    assert s.binding.previous_format.verdict(now)=='REGULATION_UNVERIFIED'
    assert s.projection.missing==(0,)*7
    assert reproduce(o.evidence,s)==s
    before=(tmp_path/'readiness/attempts.db').read_bytes()
    o.registry.retain(o.ledger,s)
    assert (tmp_path/'readiness/attempts.db').read_bytes()==before
    events,bad=o.ledger.read();assert not bad
    verify_retained(s,events,o.run_id)
    proof=next(doc for kind,_,doc in events if kind=='REGULATION_PROOF')
    assert len(proof['resolution']['records'])==2
    assert proof['format_evidence']['proof_hash']==proof['resolution_fingerprint']
    db.unlink()
    o.finish(completed=True)
    before={p.name:p.read_bytes() for p in (tmp_path/'readiness').iterdir()}
    for command in ('report','verify','diagnostics'):
        assert main(['--root',str(tmp_path/'readiness'),command])==0
        assert json.loads(capsys.readouterr().out)['reproduction']['VERIFIED']==1
    assert before=={p.name:p.read_bytes() for p in (tmp_path/'readiness').iterdir()}
    # Genuine current proof never validates another competition or missing TARGET.
    db=tmp_path/'other.db';renewed_registry(db)
    o=start(tmp_path/'other',db,lambda:now,36)
    assert decide(o,36).binding.current_format.minutes is None
    o.finish(completed=True)
    o=start(tmp_path/'no-target',db,lambda:now,2)
    assert decide(o,2,target=False) is None
    o.finish(completed=True)


@pytest.mark.parametrize('damage', ['missing_proof','tamper_proof','missing_link','missing_view'])
def test_retained_proof_damage_is_explicit_failure(tmp_path: Path, damage: str) -> None:
    db=tmp_path/'registry.db';init_registry(db);append(db,record())
    o=start(tmp_path/'readiness',db,lambda:T);s=decide(o)
    c=o.ledger.connection
    if damage.startswith('missing'):
        kind={'missing_proof':'REGULATION_PROOF','missing_link':'REGULATION_LINK','missing_view':'REGISTRY_VIEW'}[damage]
        c.execute('DROP TRIGGER fc_readiness_events_no_delete')
        c.execute('DELETE FROM fc_readiness_events WHERE kind=?',(kind,))
        c.execute("CREATE TRIGGER fc_readiness_events_no_delete BEFORE DELETE ON fc_readiness_events BEGIN SELECT RAISE(ABORT,'READINESS_IMMUTABLE'); END")
    else:
        c.execute('DROP TRIGGER fc_readiness_events_no_update')
        c.execute("UPDATE fc_readiness_events SET document='{}' WHERE kind='REGULATION_PROOF'")
        c.execute("CREATE TRIGGER fc_readiness_events_no_update BEFORE UPDATE ON fc_readiness_events BEGIN SELECT RAISE(ABORT,'READINESS_IMMUTABLE'); END")
    o.finish(completed=True)
    r=coverage(tmp_path/'readiness')
    assert r['reproduction']['VERIFIED']==0 and r['reproduction']['FAILED']==1
    assert r['regulation_counts']['VERIFIED_90']==0
    assert r['integrity_failures']['REGULATION_PROOF_UNAVAILABLE_OR_INVALID']==1
    assert r['v2_observation_attempts']==1


def test_old_unverified_bytes_and_hashes_unchanged(tmp_path: Path) -> None:
    from tests.test_prematch_football_context_readiness import collect
    import hashlib
    root=tmp_path/'readiness'
    o=collect(root)
    s=o.snapshots.load('9999:HOME_WIN')
    # Golden values independently obtained from the requested base 87f9f249.
    assert s.snapshot_hash=='61e7584615e4ab5bd93ae87122c3f4095f52d30426c5c386d47e4d0c3084d3f3'
    assert hashlib.sha256(canonical_bytes(s)).hexdigest()=='c8c510b2fa6a750425088fdcd90249f5488b9d17368ae05f9fa06ca1bdf177b5'
    o.finish(completed=True)
    before=(root/'snapshots.db').read_bytes()
    db=tmp_path/'registry.db';init_registry(db);append(db,record())
    o=ProspectiveObservation(root,environment='TEST',clock=lambda:T,regulation_registry=db)
    o.prepare((ROW,));o.bind(o.begin(),(ID,));o.observe(ID,new_opportunity=False)
    assert o.snapshots.load('9999:HOME_WIN')==s
    o.finish(completed=True)
    assert (root/'snapshots.db').read_bytes()==before
    assert coverage(root)['regulation_counts']['REGULATION_UNVERIFIED']==1


def test_genuine_format_does_not_supply_pi_support(tmp_path: Path) -> None:
    db=tmp_path/'registry.db';now=renewed_registry(db)
    o=start(tmp_path/'readiness',db,lambda:now,2)
    target=raw(9999,status='NS',kickoff=now+timedelta(hours=1));target['league']['id']=2
    o.capture('/fixtures',{'id':9999},[target],now)
    rows=[raw(i,home=1 if i<5 else 2,away=100+i,kickoff=now-timedelta(days=i)) for i in range(1,9)]
    for r in rows:r['league']['id']=2
    o.capture('/fixtures',{'league':2,'season':2026,'status':'FT','last':99},rows,now)
    identity=replace(ID,competition_id=2)
    o.bind(o.begin(),(identity,));o.observe(identity,new_opportunity=True)
    s=o.snapshots.load('9999:HOME_WIN')
    assert s.projection.missing==(0,0,0,0,1,1,1)
    assert s.projection.reasons[4:]==(('UNSUPPORTED_PI_STATE',),('UNSUPPORTED_PI_STATE',),('INSUFFICIENT_SAMPLE',))
    assert s.selected_sources[2] is None
    o.finish(completed=True)


def test_acquisition_must_precede_receipt_even_if_clock_rolls_back(tmp_path: Path) -> None:
    db=tmp_path/'registry.db';init_registry(db);append(db,record())
    now=[T];o=start(tmp_path/'readiness',db,lambda:now[0])
    now[0]-=timedelta(seconds=1)
    s=decide(o)
    assert s.binding.current_format.minutes is None
    assert o.finish(completed=True)['REGISTRY_DECISION_UNAVAILABLE']==1


def test_no_registry_argument_does_not_open_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs): pytest.fail('UNREQUESTED_REGISTRY_OPEN')
    monkeypatch.setattr('app.prematch_football_context.readiness.regulations.Registry',fail)
    o=start(tmp_path/'readiness',None,lambda:T)
    assert decide(o).binding.current_format.minutes is None
    o.finish(completed=True)


def test_identical_resolution_deduplicated_across_markets(tmp_path: Path) -> None:
    db=tmp_path/'registry.db';init_registry(db);append(db,record())
    o=start(tmp_path/'readiness',db,lambda:T)
    first=decide(o)
    # Same decision receipt shared by another market; no new receipt or resolution cutoff.
    second_id=replace(ID,market='DRAW',candidate_id='lab-v2-candidate-'+'b'*64)
    o.bind(o.receipt,(second_id,));o.observe(second_id,new_opportunity=True)
    second=o.snapshots.load('9999:DRAW')
    events,_=o.ledger.read()
    assert first.receipt==second.receipt
    assert len([1 for kind,_,_ in events if kind=='REGULATION_PROOF'])==1
    assert len([1 for kind,_,_ in events if kind=='REGULATION_LINK'])==2
    o.finish(completed=True)


def test_cli_registry_is_explicit_and_no_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from app.lab_v2_shadow import cli
    db=tmp_path/'registry.db';init_registry(db)
    initialize(tmp_path/'readiness')
    async def fake_cycle(args, *, football_context):
        assert args.send is False and football_context.registry is not None
        return {'terminal_error':None,'synthetic_test':True}
    monkeypatch.setattr(cli,'_cycle',fake_cycle)
    assert main(['--root',str(tmp_path/'readiness'),'cycle','--environment','TEST','--observe',
                 '--regulation-registry',str(db)])==0
    assert json.loads(capsys.readouterr().out)=={'terminal_error':None,'synthetic_test':True}


def test_inventory_is_coherent_during_concurrent_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db=tmp_path/'registry.db';init_registry(db);append(db,record())
    with closing(sqlite3.connect(db)) as c:
        c.execute('PRAGMA journal_mode=WAL')
    original=Registry.records
    imported=[]
    def records(self):
        result=original(self)
        if not self.writable and not imported:
            imported.append(True)
            append(db,record(review_id='SYNTHETIC_CONCURRENT',regulation_minutes=80))
        return result
    monkeypatch.setattr(Registry,'records',records)
    o=start(tmp_path/'readiness',db,lambda:T)
    assert len(o.registry.records)==1
    assert decide(o).binding.current_format.minutes==90
    o.finish(completed=True)
    with closing(Registry(db)) as registry: assert len(registry.verify())==2
    assert coverage(tmp_path/'readiness')['reproduction']['VERIFIED']==1


def test_semantic_proof_tampering_fails_even_with_new_content_hash(tmp_path: Path) -> None:
    from copy import deepcopy
    from app.prematch_football_context.sources import digest
    db=tmp_path/'registry.db';init_registry(db);append(db,record())
    o=start(tmp_path/'readiness',db,lambda:T);s=decide(o)
    events,_=o.ledger.read();events=deepcopy(events)
    proof=next(doc for kind,_,doc in events if kind=='REGULATION_PROOF')
    proof['resolution']['records']=[]
    proof_id=digest(proof)
    events=[(kind,proof_id if kind=='REGULATION_PROOF' else key,doc) for kind,key,doc in events]
    next(doc for kind,_,doc in events if kind=='REGULATION_LINK')['proofs']['current']=proof_id
    with pytest.raises(ValueError,match='REGULATION_PROOF_INTEGRITY'):
        verify_retained(s,events,o.run_id)
    o.finish(completed=True)
