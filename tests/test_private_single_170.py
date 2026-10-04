"""Private filter, complete-pool search, delivery and isolated results; offline."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.lab_private_single import policy, routing, runtime
from app.lab_private_single.repository import PrivateSingleRepository, ledger_path
from app.lab_combo.repository import ComboRepository
from app.lab_combo.service import LabComboService
from app.lab_combo.settlement import single_statistics
from app.lab_combo.presentation import ResultImagePaths
from app.lab_v2_shadow.publication import prepare_v2_publications
from tests.test_lab_accuracy_delivery import accuracy_candidate, accuracy_cycle
from tests.test_lab_v2_shadow import NOW, bind_candidate_evidence
from tests.test_lab_combo_early_loss import Provider, payload
from tests.test_settlement_replies import transport


def candidate(index=0, odds="1.70", probability="0.75", market="OVER_2_5"):
    row = accuracy_candidate(market)
    row.update(candidate_id=f"private-{index}-{market}", fixture_id=7001+index,
        home_team_id=9001+index*2, away_team_id=9002+index*2,
        captured_odds=odds, offered_odds=odds, ensemble_probability=probability,
        decision="APPROVED", stage="READY_TO_PUBLISH", candidate_lane="STANDARD",
        hard_failures=[], rejection_reasons=[], soft_findings=[],
        edge=str(Decimal(probability)-1/Decimal(odds)),
        predictive_family_count=1, predictive_families=["PI_RATINGS"],
        final_review_completed_at_utc=NOW.isoformat())
    signal = dict(name="PI_RATINGS", market=market, selection=market, probability=probability,
                  reliability="0.9", availability="AVAILABLE", provenance="SYNTHETIC_PRIVATE_TEST",
                  independence_group="PI_RATINGS")
    row["signals"] = [signal, {**signal, "name": "CURRENT_MARKET_CONSENSUS",
        "independence_group": "CURRENT_MARKET_CONSENSUS", "probability": str(1/Decimal(odds))}]
    bind_candidate_evidence(row)
    return row


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(policy.FLAG, "1")
    monkeypatch.setenv("GOALVISION_LAB_TODAY_ONLY", "1")
    monkeypatch.setenv("GOALVISION_LAB_SINGLE_MIN_ODDS_150", "1")
    monkeypatch.setenv("GOALVISION_LAB_SETTLEMENT_REPLIES", "1")
    route = {"version": routing.VERSION, "product": "PRIVATE_SINGLE", "bot_username": "@GoalVision_AI_Lab_Bot",
        "bot_id": "111111111", "chat_id": "55555555", "chat_type": "private",
        "statistics_period": routing.PERIOD, "period_started_at": (NOW-timedelta(minutes=1)).isoformat()}
    config = routing.PrivateLabConfig("synthetic_private_token", route)
    monkeypatch.setattr(routing, "load_config", lambda *args: config)
    store = PrivateSingleRepository(ledger_path())
    yield store, config
    store.close()


def prepare(store, config, rows=None, now=NOW):
    return policy.prepare({"candidate_markets": rows if rows is not None else [candidate()]},
                          store, config.route, now=now)


def send(store, config, value, client=None, now=NOW, kind="single_prediction", images=None):
    client = client or transport()
    outcome = asyncio.run(LabComboService(store, None, clock=lambda: now, result_images=images)
        .publish_experimental(kind, value["prediction_id"], config, client))
    return outcome, client


@pytest.mark.parametrize("odds,p,expected", [
    ("1.6999999999999999999999",".75",False), ("1.70",".70",True),
    ("1.70",".80",True), ("1.71",".75",True), ("2.00",".70",True),
    ("2.25",".75",False),  # Existing severe-disagreement guard remains authoritative.
    ("1.70",".699999999999999999999",False), ("1.70",".800000000000000000001",False)])
def test_exact_filter_and_real_service_delivery(setup, odds, p, expected):
    store, config = setup
    result = prepare(store, config, [candidate(odds=odds,probability=p)])
    assert bool(result["singles"]) is expected
    if expected:
        value, = result["singles"]
        outcome, client = send(store, config, value)
        assert outcome["receipt_persisted"] and outcome["sent"]
        assert client.bot.calls[0][1]["chat_id"] == "55555555"
        assert "70–80%" in client.bot.calls[0][1]["text"]
        assert "nekalibrēts" in client.bot.calls[0][1]["text"]


def test_full_pool_before_regular_per_fixture_and_cycle_truncation(setup):
    store, config = setup
    rows = [candidate(i,"1.50",".79") for i in range(4)]
    alternative = candidate(3,"1.75",".73",market="UNDER_2_5")
    rows.append(alternative)
    before = deepcopy(rows)
    public = ComboRepository(Path("var/lab_combo/ledger.db"))
    try:
        regular = prepare_v2_publications({"candidate_markets":rows},public,now=NOW,label_origin=True)
        assert len(regular["singles"]) == 3
        assert all(v["captured_odds"] == "1.50" for v in regular["singles"])
        private, = prepare(store,config,rows)["singles"]
        assert private["candidate_id"] == alternative["candidate_id"]
        assert rows == before
        assert len(public.all("single_prediction")) == 3
        assert len(store.all("single_prediction")) == 1
    finally:
        public.close()


@pytest.mark.parametrize("bad", ["stale", "tomorrow", "started", "quote", "probability", "rejected",
                                     "missing_signals", "market_only", "contradiction", "missing_identity"])
def test_quality_fail_closed_no_forced_private_pick(setup,bad):
    store, config = setup
    row = candidate()
    if bad == "stale": row["provider_origin_timestamp_utc"]=(NOW-timedelta(days=1)).isoformat()
    if bad == "tomorrow": row["kickoff_utc"]=(NOW+timedelta(days=1)).isoformat()
    if bad == "started": row["kickoff_utc"]=(NOW-timedelta(seconds=1)).isoformat()
    if bad == "quote": row["quote_provenance_fingerprint"]="wrong"
    if bad == "probability": row["ensemble_probability"]=".80"
    if bad == "rejected": row.update(decision="REJECTED",stage="REJECTED")
    if bad == "missing_signals": row.pop("signals")
    if bad == "market_only":
        row["signals"]=[row["signals"][1]]
        row["signals"][0]["probability"]=".75"
    if bad == "contradiction": row["soft_findings"]=["SEVERE_MODEL_MARKET_CONTRADICTION"]
    if bad == "missing_identity": row.pop("provider_metadata")
    assert not prepare(store,config,[row])["singles"]
    assert not store.all("claim")


@pytest.mark.parametrize("bad", ["wrong_bot","wrong_bot_id","wrong_recipient","policy","preview","odds","probability","scope"])
def test_frozen_preclaim_private_boundary(setup,bad,monkeypatch):
    store, config = setup
    value, = prepare(store,config)["singles"]
    client = transport()
    if bad == "wrong_bot": client.bot.username="GoalVision_AI_Combo_Bot"
    if bad == "wrong_bot_id": client.bot.id=777777777
    if bad == "wrong_recipient": config=routing.PrivateLabConfig(config.token,{**config.route,"chat_id":"999"})
    if bad in {"policy","preview","odds","probability"}:
        get=store.get
        def corrupt(kind, identity):
            d=get(kind,identity)
            if identity==value["prediction_id"]:
                if bad=="preview" and kind=="single_preview":return {"message":"fabricated"}
                if kind=="single_prediction":
                    k,v={"policy":("maximum_published_probability",".90"),
                         "odds":("captured_odds","1.60"),"probability":("ensemble_probability",".69")}.get(bad,("unused",None))
                    return {**d,k:v}
            return d
        monkeypatch.setattr(store,"get",corrupt)
    if bad=="scope":
        public=ComboRepository(Path("var/lab_combo/ledger.db"))
        public.append("single_prediction",value["prediction_id"],value)
        public.append("single_preview",value["prediction_id"],store.get("single_preview",value["prediction_id"]))
        store=public
    try:
        outcome,_=send(store,config,value,client)
        assert not outcome["sent"] and not client.bot.calls and not store.all("claim")
    finally:
        if bad=="scope":store.close()


def test_unknown_send_remains_claimed_and_other_market_same_fixture_blocked(setup):
    store,config=setup
    first,=prepare(store,config)["singles"]
    second,=prepare(store,config,[candidate(market="UNDER_2_5")])["singles"]
    result,client=send(store,config,first,transport("timeout"))
    assert result["reconciliation_required"] and result["transport_attempted"]
    for value in (first,second):
        outcome,c=send(store,config,value)
        assert not outcome["sent"] and not c.bot.calls
    assert not prepare(store,config,[candidate(market="UNDER_2_5")])["singles"]


@pytest.mark.parametrize("photo",[False,True])
@pytest.mark.parametrize("score,status",[((2,2),"WON"),((0,1),"LOST"),((None,None),"VOID")])
def test_results_reply_and_statistics_survive_pause_without_learning_duplication(setup,monkeypatch,tmp_path,photo,score,status):
    store,config=setup
    value,=prepare(store,config)["singles"]
    assert send(store,config,value)[0]["sent"]
    monkeypatch.setenv(policy.FLAG,"0")
    now=NOW+timedelta(hours=4)
    cache={str(value["fixture_id"]):payload(value["fixture_id"],"CANC" if status=="VOID" else "FT",score)}
    provider=Provider({})
    result=asyncio.run(LabComboService(store,None,clock=lambda:now).check_results(provider,maximum_calls=0,result_cache=cache))
    assert result["single_completed"]==[value["prediction_id"]] and not provider.calls
    assert single_statistics(store)[status]==1
    images=None
    if photo:
        image=tmp_path/"result.png";image.write_bytes(b"fixture-image")
        images=ResultImagePaths(**{{"WON":"win","LOST":"loss","VOID":"void"}[status]:image})
    output,client=send(store,config,value,now=now,kind="single_settlement",images=images)
    assert output["sent"] and output["reply_status"]=="CONFIRMED"
    call=client.bot.calls[0][1]
    assert call["chat_id"]==config.route["chat_id"] and call["reply_parameters"].message_id==101
    public=ComboRepository(Path("var/lab_combo/ledger.db"))
    try:assert single_statistics(public)["total_published"]==0
    finally:public.close()


def test_expired_pending_preview_cannot_send(setup):
    store,config=setup
    value,=prepare(store,config)["singles"]
    result,client=send(store,config,value,now=NOW+timedelta(hours=2))
    assert not result["sent"] and not client.bot.calls


def test_config_failure_and_disabled_hook_never_construct_transport(setup,monkeypatch):
    def forbidden(*args):pytest.fail("No transport should be constructed")
    monkeypatch.setenv(policy.FLAG,"0")
    assert asyncio.run(runtime.publish_natural({},transport_factory=forbidden))["status"]=="DISABLED"
    monkeypatch.setenv(policy.FLAG,"1")
    def missing():raise routing.RoutingBlocked("PRIVATE_LAB_RECIPIENT_NOT_CONFIGURED")
    monkeypatch.setattr(routing,"load_config",missing)
    assert asyncio.run(runtime.publish_natural({},transport_factory=forbidden))["status"]=="PRIVATE_LAB_RECIPIENT_NOT_CONFIGURED"


def test_main_cycle_no_send_never_calls_private_hook(accuracy_cycle,monkeypatch):
    async def forbidden(*args,**kwargs):pytest.fail("Private hook in no-send mode")
    monkeypatch.setattr(runtime,"publish_natural",forbidden)
    accuracy_cycle(candidate(),send=False)


def test_main_cycle_private_hook_receives_complete_pool_and_counts_separately(accuracy_cycle,monkeypatch):
    seen=[]
    async def captured(report,**kwargs):
        seen.extend(report["candidate_markets"])
        return {"status":"COMPLETED","transport_constructed":True,
                "deliveries":[{"receipt_persisted":True,"transport_attempted":True}]}
    monkeypatch.setattr(runtime,"publish_natural",captured)
    summary,evidence=accuracy_cycle(candidate())
    assert seen[0]["candidate_id"]==candidate()["candidate_id"]
    assert evidence["controlled_publication"]["singles_sent"]==1
    assert evidence["controlled_publication"]["private_singles_sent"]==1
    assert evidence["telegram_sends"]==2


def test_atomic_fixture_claim_across_concurrent_different_markets(setup):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    store,config=setup
    a,=prepare(store,config)["singles"]
    b,=prepare(store,config,[candidate(market="UNDER_2_5")])["singles"]
    barrier=Barrier(2)
    def claim(value):
        db=PrivateSingleRepository(ledger_path())
        try:
            barrier.wait()
            return db.claim_publication('single_prediction',value,{'prediction_id':value['prediction_id']})
        finally:db.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim,[a,b]))==[False,True]
    assert len(store.all('claim'))==len(store.all('economic_claim'))==1


def test_public_and_private_results_share_one_provider_request(setup):
    store,config=setup
    row=candidate()
    private,=prepare(store,config,[row])["singles"]
    assert send(store,config,private)[0]['sent']
    public=ComboRepository(Path('var/lab_combo/ledger.db'))
    try:
        prediction,=prepare_v2_publications({'candidate_markets':[row]},public,now=NOW,label_origin=True)['singles']
        public.append('receipt','single_prediction:'+prediction['prediction_id'],
            {'sent':True,'status':'SENT','chat_id':'-1003510920417','message_id':9,'sent_at_utc':NOW.isoformat()})
        provider=Provider({row['fixture_id']:payload(row['fixture_id'],score=(2,2))})
        cache={};now=NOW+timedelta(hours=4)
        asyncio.run(LabComboService(public,None,clock=lambda:now).check_results(provider,result_cache=cache))
        asyncio.run(LabComboService(store,None,clock=lambda:now).check_results(provider,maximum_calls=0,result_cache=cache))
        assert provider.calls==[row['fixture_id']]
        assert single_statistics(public)['WON']==single_statistics(store)['WON']==1
    finally:public.close()


def test_private_result_budget_and_pending_survive_no_send(setup):
    store,config=setup
    rows=[candidate(i) for i in range(3)]
    for row in rows:
        value,=prepare(store,config,[row])['singles']
        assert send(store,config,value)[0]['sent']
    provider=Provider({r['fixture_id']:payload(r['fixture_id'],score=(2,2)) for r in rows})
    result=asyncio.run(runtime.settle_natural(provider,result_cache={},maximum_calls=2,
        transport_factory=lambda *a:pytest.fail('No transport in no-send result check'),send=False,
        clock=lambda:NOW+timedelta(hours=4)))
    assert result['status']=='COMPLETED' and len(provider.calls)==2
    assert single_statistics(store)['total_settled']==2 and single_statistics(store)['pending']==1
