"""Separate COMBO bot, recipient enrollment, cohort and rollback tests; no network."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.lab_combo import bot_routing as routing
from app.lab_combo.bot_delivery import deliver_batch
from app.lab_combo.service import LabComboService
from app.lab_combo.settlement import statistics
from tests.test_lab_accuracy_combo import candidates, prepare
from tests.test_prematch_v2_enablement import ledger, config, Transport
from tests.test_lab_v2_shadow import NOW
from tests.test_lab_combo_early_loss import Provider, payload

TOKEN = "777777777:" + "synthetic_token_" * 3


@pytest.fixture
def routed(tmp_path, monkeypatch):
    path = tmp_path / "private/combo.json"
    path.parent.mkdir()
    stamp = (NOW - timedelta(minutes=1)).isoformat()
    route = {"version": routing.VERSION, "product": "COMBO",
             "bot_username": routing.BOT_USERNAME, "bot_id": "777777777",
             "chat_id": "55555555", "chat_type": "private",
             "statistics_period": routing.PERIOD, "period_started_at": stamp}
    data = {"token": TOKEN, "route": route, "verified_at": stamp, "start_update_id": 9}
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    monkeypatch.setattr(routing, "CONFIG_PATH", path)
    monkeypatch.setenv(routing.FLAG, "1")
    monkeypatch.setenv("GOALVISION_LAB_SINGLE_MIN_ODDS_130", "1")
    monkeypatch.setenv("GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130", "1")
    return path, data, routing.load_config()


class Bot:
    def __init__(self, username, identity):
        self.username, self.id = username, identity

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def shutdown(self):
        return None


class RoutedTransport:
    instances = []

    def __init__(self, token):
        self.bot = Bot("GoalVision_AI_Combo_Bot" if token == TOKEN else "GoalVision_AI_Lab_Bot",
                       777777777 if token == TOKEN else 111111111)
        self.calls, self.fail, self.wrong_receipt = [], False, False
        type(self).instances.append(self)

    async def send_message_receipt(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise TimeoutError("SENSITIVE_SYNTHETIC_TOKEN")
        return SimpleNamespace(chat_id="999" if self.wrong_receipt else kwargs["chat_id"], message_id=123)

    async def send_photo_receipt(self, **kwargs):
        return await self.send_message_receipt(**kwargs)


def send(store, kind, pid, cfg, transport, now=NOW):
    return asyncio.run(LabComboService(store, None, clock=lambda: now).publish_experimental(
        kind, pid, cfg, transport))


def test_new_combo_and_single_use_separate_bots_and_frozen_claims(ledger, routed):
    _, _, cfg = routed
    result = prepare(ledger)
    combo, = result["combos"]
    single = result["singles"][0]
    service = LabComboService(ledger, None, clock=lambda: NOW)
    RoutedTransport.instances = []
    deliveries, failure = asyncio.run(deliver_batch(service, [
        ("single_prediction",single["prediction_id"]),("combo_prediction",combo["prediction_id"])],
        config(), RoutedTransport))
    assert failure is None and all(d["sent"] for d in deliveries)
    lab, separate = RoutedTransport.instances
    assert lab.calls[0]["chat_id"] == "-1003510920417"
    assert separate.calls[0]["chat_id"] == cfg.chat_id
    assert separate.calls[0]["text"].startswith("⚽ GoalVision AI COMBO")
    assert "Katras likmes koef. ≥1.30." in separate.calls[0]["text"]
    identity = "combo_prediction:" + combo["prediction_id"]
    for kind in ("claim", "receipt"):
        assert ledger.get(kind, identity)["delivery_route"] == cfg.route
        assert TOKEN not in json.dumps(ledger.get(kind, identity))
    assert routing.cohort_statistics(ledger, cfg.route)["total_published"] == 1
    assert routing.cohort_statistics(ledger, None)["total_published"] == 0
    assert statistics(ledger, published_only=True)["total_published"] == 1


@pytest.mark.parametrize("problem", ["missing", "permissions", "wrong_route", "wrong_bot", "wrong_id", "future", "paused", "invalid_flag"])
def test_misconfiguration_never_claims_or_falls_back(ledger, routed, monkeypatch, problem):
    path, data, cfg = routed
    combo, = prepare(ledger)["combos"]
    transport = RoutedTransport(TOKEN)
    if problem == "missing":
        path.unlink()
    elif problem == "permissions":
        path.chmod(0o644)
    elif problem == "wrong_route":
        cfg = routing.ComboBotConfig(TOKEN, {**cfg.route, "chat_id": "666"}, cfg.verified_at, 9)
    elif problem == "wrong_bot":
        transport.bot.username = "other_bot"
    elif problem == "wrong_id":
        transport.bot.id = 123
    elif problem == "future":
        stamp = (NOW+timedelta(days=1)).isoformat()
        data["route"]["period_started_at"] = data["verified_at"] = stamp
        path.write_text(json.dumps(data))
        cfg = routing.load_config()
    elif problem == "paused":
        monkeypatch.setenv(routing.FLAG, "0")
    else:
        monkeypatch.setenv(routing.FLAG, "yes")
    outcome = send(ledger, "combo_prediction", combo["prediction_id"], cfg, transport)
    assert not outcome["sent"] and not outcome["transport_attempted"]
    assert not ledger.all("claim") and not transport.calls


@pytest.mark.parametrize("problem", ["missing", "identity", "initialization"])
def test_combo_failure_does_not_suppress_single(ledger, routed, problem):
    path, _, cfg = routed
    result = prepare(ledger)
    if problem == "missing":
        path.unlink()
    class Factory(RoutedTransport):
        def __init__(self, token):
            if token == TOKEN and problem == "initialization":
                raise RuntimeError("PRIVATE_TOKEN")
            super().__init__(token)
            if token == TOKEN and problem == "identity":
                self.bot.username = "wrong"
    service = LabComboService(ledger,None,clock=lambda:NOW)
    outcomes, failure = asyncio.run(deliver_batch(service,[
        ("combo_prediction",result["combos"][0]["prediction_id"]),
        ("single_prediction",result["singles"][0]["prediction_id"])],config(),Factory))
    assert any(x["kind"]=="single_prediction" and x["sent"] for x in outcomes)
    assert not any(x["kind"]=="combo_prediction" and x["sent"] for x in outcomes)
    assert "PRIVATE_TOKEN" not in json.dumps([outcomes,failure])


@pytest.mark.parametrize("unknown", ["timeout","wrong_receipt","receipt_persistence"])
def test_unknown_stays_claimed_across_pause_and_never_resends(ledger, routed, monkeypatch, unknown):
    _, _, cfg = routed
    combo, = prepare(ledger)["combos"]
    transport=RoutedTransport(TOKEN)
    transport.fail = unknown=="timeout"
    transport.wrong_receipt = unknown=="wrong_receipt"
    if unknown=="receipt_persistence":
        original=ledger.append
        def append(kind, identity, value):
            if kind=="receipt":
                raise RuntimeError("SENSITIVE")
            return original(kind,identity,value)
        monkeypatch.setattr(ledger,"append",append)
        from app.lab_combo.service import DeliveryFailure
        with pytest.raises(DeliveryFailure):
            send(ledger,"combo_prediction",combo["prediction_id"],cfg,transport)
    else:
        outcome=send(ledger,"combo_prediction",combo["prediction_id"],cfg,transport)
        assert outcome["reconciliation_required"] and not outcome["sent"]
    monkeypatch.setenv(routing.FLAG,"0")
    outcome=send(ledger,"combo_prediction",combo["prediction_id"],config(),Transport())
    assert outcome["status"]=="DELIVERY_ALREADY_CLAIMED" and len(transport.calls)==1
    assert routing.cohort_statistics(ledger,cfg.route)["total_published"]==0


def test_old_and_new_results_keep_original_routes_and_cohorts_after_pause(ledger,routed,monkeypatch):
    _, _, cfg=routed
    monkeypatch.delenv(routing.FLAG)
    old,=prepare(ledger)["combos"]
    assert send(ledger,"combo_prediction",old["prediction_id"],config(),Transport())["sent"]
    monkeypatch.setenv(routing.FLAG,"1")
    new,=prepare(ledger,candidates(6)[3:])["combos"]
    assert send(ledger,"combo_prediction",new["prediction_id"],cfg,RoutedTransport(TOKEN))["sent"]
    now=NOW+timedelta(hours=8)
    responses={int(leg["fixture_id"]):payload(int(leg["fixture_id"]),score=(0,0))
               for c in (old,new) for leg in c["legs"]}
    service=LabComboService(ledger,None,clock=lambda:now,early_combo_loss=True)
    report=asyncio.run(service.check_results(Provider(responses)))
    assert len(report["completed"])==2
    monkeypatch.setenv(routing.FLAG,"0")
    RoutedTransport.instances=[]
    outcomes,failure=asyncio.run(deliver_batch(service,[
        ("combo_settlement",old["prediction_id"]),("combo_settlement",new["prediction_id"])],
        config(),RoutedTransport))
    assert failure is None and all(x["sent"] for x in outcomes)
    assert {t.calls[0]["chat_id"] for t in RoutedTransport.instances}=={"-1003510920417",cfg.chat_id}
    for c in (old,new):
        frozen=ledger.get("settlement_preview",c["prediction_id"])
        assert frozen["statistics"]["total_published"]==1
        assert frozen["statistics"]["total_settled"]==1
    assert statistics(ledger,published_only=True)["total_published"]==2
    before=deepcopy(ledger.all("settlement"))
    asyncio.run(service.check_results(Provider({})))
    assert ledger.all("settlement")==before
    assert len(ledger.all("receipt"))==4


def test_new_route_early_loss_keeps_pending_legs_and_one_outcome(ledger,routed,monkeypatch):
    _, _, cfg=routed
    stamp=(NOW-timedelta(hours=5)).isoformat()
    combo={"prediction_id":"early-new", "combined_odds":"3.375", "legs":[
        {"observation_id":f"early-{i}","fixture_id":i,"market":"OVER_2_5","odds":"1.5",
         "home_team":f"H{i}","away_team":f"A{i}",
         "kickoff_utc":(NOW+timedelta(hours=-4 if i==1 else i)).isoformat()}
        for i in (1,2,3)]}
    ledger.append("prediction","early-new",combo)
    route=cfg.route
    identity="combo_prediction:early-new"
    ledger.claim_publication("combo_prediction",combo,{"chat_id":cfg.chat_id,"delivery_route":route})
    ledger.append("receipt",identity,{"status":"SENT","sent":True,"chat_id":cfg.chat_id,"message_id":8,
        "sent_at_utc":stamp,"delivery_route":route})
    service=LabComboService(ledger,None,clock=lambda:NOW,early_combo_loss=True)
    asyncio.run(service.check_results(Provider({1:payload(1)})))
    result=ledger.get("settlement","early-new")
    assert result["status"]=="LOST" and len(result["pending_legs"])==2
    assert send(ledger,"combo_settlement","early-new",cfg,RoutedTransport(TOKEN))["sent"]
    monkeypatch.setenv(routing.FLAG,"0")
    later=NOW+timedelta(hours=6)
    service=LabComboService(ledger,None,clock=lambda:later)
    asyncio.run(service.check_results(Provider({2:payload(2,score=(2,2)),3:payload(3,"CANC",(None,None))})))
    assert len(ledger.all("settlement"))==1 and len(ledger.all("combo_result_detail"))==1
    assert ledger.get("settlement","early-new")==result
    assert routing.cohort_statistics(ledger,route)["hypothetical_profit_loss"]=="-1"
    assert send(ledger,"combo_settlement","early-new",cfg,RoutedTransport(TOKEN),later)["status"]=="DELIVERY_ALREADY_CLAIMED"


def setup_module_source():
    path=Path(__file__).resolve().parents[1]/"operations/combo-bot/configure.py"
    spec=importlib.util.spec_from_file_location("combo_enrollment",path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("bad",["text","old","group","different_sender","bot","ambiguous","expired","forward"])
def test_recipient_requires_fresh_unique_private_start(bad):
    mod=setup_module_source()
    row={"update_id":1,"message":{"text":"/start nonce","date":1000,
        "from":{"id":7,"is_bot":False},"chat":{"id":7,"type":"private"}}}
    rows=[row]
    now=1001
    if bad=="text":row["message"]["text"]="/start"
    elif bad=="old":row["message"]["date"]=900
    elif bad=="group":row["message"]["chat"]["type"]="group"
    elif bad=="different_sender":row["message"]["from"]["id"]=8
    elif bad=="bot":row["message"]["from"]["is_bot"]=True
    elif bad=="ambiguous":
        second=deepcopy(row);second["message"]["from"]["id"]=second["message"]["chat"]["id"]=8;rows.append(second)
    elif bad=="expired":now=2000
    else:row["message"]["forward_origin"]={}
    with pytest.raises(ValueError):mod.recipient(rows,"nonce",1000,now)


def test_recipient_positive_and_no_arbitrary_api_method():
    mod=setup_module_source()
    row={"update_id":1,"message":{"text":"/start nonce","date":1000,
        "from":{"id":7,"is_bot":False},"chat":{"id":7,"type":"private"}}}
    assert mod.recipient([row],"nonce",1000,1001)==("7",1)
    with pytest.raises(ValueError,match="READ_ONLY"):
        mod.telegram_read("fictional","sendMessage")


def test_credentials_never_appear_in_repr_and_symlinks_rejected(routed):
    path,_,cfg=routed
    assert TOKEN not in repr(cfg)
    alias=path.with_name("alias.json")
    alias.symlink_to(path)
    with pytest.raises(routing.RoutingBlocked):
        routing.load_config(alias)


def test_operator_enrollment_writes_0600_after_exact_private_start(routed, monkeypatch, capsys):
    import dotenv
    path, _, cfg = routed
    path.unlink()
    path.parent.chmod(0o700)
    mod = setup_module_source()
    monkeypatch.setattr(mod, "contract", lambda package: routing)
    monkeypatch.setattr(mod.secrets, "token_hex", lambda count: "a"*32)
    monkeypatch.setattr(mod.time, "time", lambda: 1000)
    monkeypatch.setattr(dotenv, "dotenv_values", lambda path: {"LAB_TOKEN": "different"})
    calls = []
    def reader(token, method, parameters=None):
        calls.append((method, parameters))
        assert token == TOKEN
        if method == "getMe":
            return {"is_bot":True,"id":777777777,"username":routing.BOT_USERNAME[1:]}
        return [{"update_id":8,"message":{"date":1000,"text":"/start gvcombo_"+"a"*32,
                 "chat":{"type":"private","id":55555555},"from":{"id":55555555,"is_bot":False}}}]
    answers=iter(["","JA"])
    mod.configure(Path("."), reader=reader, ask=lambda text:next(answers), secret=lambda text:TOKEN)
    assert [item[0] for item in calls] == ["getMe","getUpdates"]
    assert calls[1][1] == {"limit":100,"timeout":0}  # no update acknowledgement or filter mutation
    loaded=routing.load_config()
    assert loaded.chat_id=="55555555" and loaded.start_update_id==8
    assert path.stat().st_mode & 0o777 == 0o600
    assert TOKEN not in capsys.readouterr().out


def test_cross_destination_duplicate_is_blocked_economically(ledger,routed,monkeypatch):
    _,_,cfg=routed
    monkeypatch.delenv(routing.FLAG)
    old,=prepare(ledger)["combos"]
    assert send(ledger,"combo_prediction",old["prediction_id"],config(),Transport())["sent"]
    monkeypatch.setenv(routing.FLAG,"1")
    assert not prepare(ledger)["combos"]
    assert send(ledger,"combo_prediction",old["prediction_id"],cfg,RoutedTransport(TOKEN))["status"]=="DELIVERY_ALREADY_CLAIMED"
    clone=deepcopy(old)
    clone["prediction_id"]="different-version-same-economic-bet"
    ledger.append("prediction",clone["prediction_id"],clone)
    assert not ledger.claim_publication("combo_prediction",clone,{"delivery_route":cfg.route})
    assert len(ledger.all("economic_claim"))==1


def test_legacy_direct_sender_cannot_escape_active_route(ledger,routed):
    _,_,cfg=routed
    combo,=prepare(ledger)["combos"]
    transport=Transport()
    result=asyncio.run(LabComboService(ledger,None,clock=lambda:NOW).publish(
        combo["prediction_id"],config(),transport))
    assert result["status"]=="COMBO_CREDENTIAL_ROUTE_MISMATCH"
    assert not transport.calls and not ledger.all("claim")


def test_missing_frozen_binding_is_rejected_even_with_other_valid_credentials(ledger,routed):
    _,_,cfg=routed
    combo,=prepare(ledger)["combos"]
    identity="combo_prediction:"+combo["prediction_id"]
    ledger.claim_publication("combo_prediction",combo,{"chat_id":cfg.chat_id,"delivery_route":cfg.route})
    ledger.append("receipt",identity,{"sent":True,"status":"SENT","chat_id":cfg.chat_id,"message_id":5})
    with pytest.raises(routing.RoutingBlocked):
        routing.frozen_route(ledger,combo["prediction_id"])
