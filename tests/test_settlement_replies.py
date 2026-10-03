"""Settlement reply contracts and service integration; fake Telegram/provider only."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.lab_combo.presentation import LabTelegramTransport, ResultImagePaths
from app.lab_combo.service import LabComboService, DeliveryFailure
from app.lab_combo.settlement_reply import FLAG, settlement_reply
from tests.test_combo_bot_routing import routed, send
from tests.test_lab_accuracy_combo import prepare
from tests.test_lab_combo_early_loss import Provider, payload
from tests.test_lab_v2_shadow import NOW
from tests.test_prematch_v2_enablement import ledger, config

LAB = "-1003510920417"


@pytest.fixture(autouse=True)
def replies(monkeypatch):
    monkeypatch.setenv(FLAG, "1")


class FakeBot:
    """Return real-shaped Telegram messages without creating a network client."""
    username = "GoalVision_AI_Lab_Bot"
    id = 111111111

    def __init__(self, parent="present"):
        self.parent, self.calls = parent, []

    async def send_message(self, **kwargs):
        self.calls.append(("text", kwargs))
        return self.result(kwargs)

    async def send_photo(self, **kwargs):
        assert kwargs["photo"].read() == b"fixture-image"
        self.calls.append(("photo", kwargs))
        return self.result(kwargs)

    def result(self, kwargs):
        if self.parent == "timeout":
            raise TimeoutError("synthetic-secret-must-not-escape")
        reply = kwargs.get("reply_parameters")
        parent = None
        if reply is not None and self.parent != "deleted":
            parent = SimpleNamespace(
                message_id=reply.message_id + (1 if self.parent == "wrong_id" else 0),
                chat=SimpleNamespace(id="999" if self.parent == "wrong_chat" else kwargs["chat_id"]))
        return SimpleNamespace(message_id=100 + len(self.calls),
                               chat=SimpleNamespace(id=kwargs["chat_id"]), reply_to_message=parent)


def transport(parent="present", private=False):
    result = object.__new__(LabTelegramTransport)
    result.bot = FakeBot(parent)
    if private:
        result.bot.username, result.bot.id = "GoalVision_AI_Combo_Bot", 777777777
    return result


@pytest.mark.parametrize("kind,prefix", [
    ("single_settlement", "single_prediction:"), ("combo_settlement", "combo_prediction:"),
    ("settlement", "prediction:")])
def test_binding_uses_original_publication_not_latest_message(ledger, kind, prefix):
    ledger.append("receipt", prefix+"old", {"sent":True,"status":"SENT","chat_id":LAB,"message_id":7})
    ledger.append("receipt", prefix+"new", {"sent":True,"status":"SENT","chat_id":LAB,"message_id":90})
    binding = settlement_reply(ledger, kind, "old", LAB)
    assert binding["message_id"] == 7 and binding["publication_identity"] == prefix+"old"
    assert binding["chat_id"] == LAB and binding["allow_sending_without_reply"] is True


@pytest.mark.parametrize("bad", ["missing", "chat", "bool", "zero", "negative", "string", "status", "sent"])
def test_invalid_original_receipt_cannot_bind(ledger, bad):
    row = {"sent":True, "status":"SENT", "chat_id":LAB, "message_id":7}
    if bad == "chat": row["chat_id"] = "999"
    if bad in {"bool","zero","negative","string"}:
        row["message_id"] = {"bool":True,"zero":0,"negative":-1,"string":"7"}[bad]
    if bad == "status": row["status"] = "UNKNOWN"
    if bad == "sent": row["sent"] = 1
    if bad != "missing": ledger.append("receipt", "single_prediction:p", row)
    with pytest.raises(ValueError, match="ORIGINAL_RECEIPT_REQUIRED"):
        settlement_reply(ledger, "single_settlement", "p", LAB)


def test_flag_is_strict_and_predictions_do_not_require_a_parent(ledger, monkeypatch):
    monkeypatch.setenv(FLAG, "bad")
    assert settlement_reply(ledger, "combo_prediction", "p", LAB) is None
    with pytest.raises(ValueError, match="CONFIGURATION_INVALID"):
        settlement_reply(ledger, "combo_settlement", "p", LAB)
    monkeypatch.setenv(FLAG, "0")
    assert settlement_reply(ledger, "combo_settlement", "p", LAB) is None


@pytest.mark.parametrize("photo", [False, True])
@pytest.mark.parametrize("parent", ["present", "deleted", "wrong_id", "wrong_chat", "timeout"])
def test_transport_same_chat_reply_one_request_and_receipt(tmp_path, photo, parent):
    client = transport(parent)
    image = tmp_path/"win.png"; image.write_bytes(b"fixture-image")
    kwargs = dict(chat_id=LAB, timeout_seconds=10, reply_to_message_id=7)
    operation = (client.send_photo_receipt(image_path=image, caption="result", **kwargs) if photo
                 else client.send_message_receipt(text="result", **kwargs))
    if parent in {"wrong_id", "wrong_chat", "timeout"}:
        with pytest.raises((ValueError, TimeoutError)):
            asyncio.run(operation)
    else:
        receipt = asyncio.run(operation)
        assert receipt.reply_to_message_id == (7 if parent == "present" else None)
        assert receipt.chat_id == LAB
    assert len(client.bot.calls) == 1
    arguments = client.bot.calls[0][1]
    reply = arguments["reply_parameters"]
    assert reply.message_id == 7 and reply.allow_sending_without_reply is True
    assert reply.chat_id is None
    assert all(arguments[k+"_timeout"] == 10 for k in ("read","write","connect","pool"))


@pytest.mark.parametrize("value", [True, 0, -1, "7"])
@pytest.mark.parametrize("photo", [False, True])
def test_invalid_parent_rejected_before_send(tmp_path, value, photo):
    client = transport()
    image = tmp_path/"win.png"; image.write_bytes(b"fixture-image")
    kwargs = dict(chat_id=LAB, timeout_seconds=10, reply_to_message_id=value)
    operation = (client.send_photo_receipt(image_path=image, caption="result", **kwargs) if photo
                 else client.send_message_receipt(text="result", **kwargs))
    with pytest.raises(ValueError, match="INVALID_REPLY"):
        asyncio.run(operation)
    assert not client.bot.calls


@pytest.mark.parametrize("product,outcome", [(product,outcome)
    for product in ("single","old_combo","private_combo")
    for outcome in ("WON","LOST","VOID","PARTIAL_VOID")
    if product != "single" or outcome != "PARTIAL_VOID"])
@pytest.mark.parametrize("photo", [False, True])
def test_result_replies_to_actual_prediction_with_frozen_evidence(
        ledger, routed, monkeypatch, tmp_path, product, outcome, photo):
    _, _, combo_cfg = routed
    if product == "old_combo":
        monkeypatch.delenv("GOALVISION_COMBO_BOT_ROUTING")
    prepared = prepare(ledger)
    single = product == "single"
    prediction = prepared["singles"][0] if single else prepared["combos"][0]
    prefix = "single" if single else "combo"
    cfg = combo_cfg if product == "private_combo" else config()
    client = transport(private=product == "private_combo")
    published = send(ledger, prefix+"_prediction", prediction["prediction_id"], cfg, client)
    assert published["sent"]
    assert "reply_parameters" not in client.bot.calls[0][1]
    original_id = published["message_id"]
    legs = [prediction] if single else prediction["legs"]
    responses = {}
    for i, leg in enumerate(legs):
        fid = int(leg["fixture_id"])
        cancel = outcome == "VOID" or (outcome == "PARTIAL_VOID" and i == 0)
        responses[fid] = payload(fid, "CANC" if cancel else "FT",
                                 (None,None) if cancel else ((0,0) if outcome=="LOST" else (2,2)))
    image = tmp_path/"result.png"; image.write_bytes(b"fixture-image")
    images = ResultImagePaths(image,image,image) if photo else ResultImagePaths()
    later = NOW + timedelta(hours=12)
    service = LabComboService(ledger,None,clock=lambda:later,result_images=images,early_combo_loss=True)
    asyncio.run(service.check_results(Provider(responses)))
    economic_kind = "single_settlement" if single else "settlement"
    economic = deepcopy(ledger.get(economic_kind,prediction["prediction_id"]))
    assert economic["status"] == outcome
    # Original route persists even if new COMBO publication is paused.
    monkeypatch.setenv("GOALVISION_COMBO_BOT_ROUTING", "0")
    result = asyncio.run(service.publish_experimental(prefix+"_settlement", prediction["prediction_id"],cfg,client))
    assert result["sent"] and result["reply_status"] == "CONFIRMED"
    assert result["reply_to"]["message_id"] == original_id
    assert client.bot.calls[1][0] == ("photo" if photo else "text")
    assert client.bot.calls[1][1]["reply_parameters"].message_id == original_id
    assert client.bot.calls[1][1]["chat_id"] == cfg.chat_id
    identity = prefix+"_settlement:"+prediction["prediction_id"]
    assert ledger.get("claim",identity)["reply_to"] == ledger.get("receipt",identity)["reply_to"]
    monkeypatch.setenv(FLAG, "0")
    assert asyncio.run(service.publish_experimental(prefix+"_settlement",prediction["prediction_id"],cfg,client))["status"] == "DELIVERY_ALREADY_CLAIMED"
    assert len(client.bot.calls) == 2
    assert ledger.get(economic_kind,prediction["prediction_id"]) == economic


@pytest.mark.parametrize("failure", ["timeout","wrong_id","wrong_chat","receipt_persistence","deleted"])
def test_result_unknown_never_retries_and_deleted_parent_is_not_claimed_confirmed(
        ledger, monkeypatch, failure):
    ledger.append("receipt","single_prediction:p",{"sent":True,"status":"SENT","chat_id":LAB,"message_id":7})
    ledger.append("single_settlement","p",{"prediction_id":"p","status":"WON"})
    ledger.append("single_settlement_preview","p",{"message":"result"})
    client = transport("present" if failure=="receipt_persistence" else failure)
    service = LabComboService(ledger,None,clock=lambda:NOW)
    if failure == "receipt_persistence":
        original = ledger.append
        def append(kind, identity, value):
            if kind == "receipt": raise RuntimeError("synthetic-secret")
            return original(kind,identity,value)
        monkeypatch.setattr(ledger,"append",append)
        with pytest.raises(DeliveryFailure):
            asyncio.run(service.publish_experimental("single_settlement","p",config(),client))
    else:
        result = asyncio.run(service.publish_experimental("single_settlement","p",config(),client))
        if failure == "deleted":
            assert result["sent"] and result["reply_status"] == "NOT_CONFIRMED"
        else:
            assert result["reconciliation_required"] and not result["sent"]
            assert "synthetic-secret" not in str(result)
    assert ledger.get("claim","single_settlement:p")["reply_to"]["message_id"] == 7
    monkeypatch.setenv(FLAG,"0")
    assert asyncio.run(service.publish_experimental("single_settlement","p",config(),client))["status"] == "DELIVERY_ALREADY_CLAIMED"
    assert len(client.bot.calls) == 1


def test_legacy_direct_settlement_replies_and_retains_deduplication(ledger):
    from tests.test_lab_combo import legs, select_combo, NOW as old_now
    from app.lab_combo.settlement import aggregate, statistics, settlement_message
    combo = select_combo(legs(),old_now)[0]
    pid = combo["prediction_id"]
    ledger.append("prediction",pid,combo)
    ledger.append("receipt","prediction:"+pid,{"status":"SENT","sent":True,"chat_id":LAB,"message_id":19})
    results = [dict(observation_id=l["observation_id"],fixture_id=l["fixture_id"],
                    market=l["market"],outcome="LOST") for l in combo["legs"]]
    for row in results: ledger.append("leg_result",row["observation_id"],row)
    settled = aggregate(combo,results,old_now)
    ledger.append("settlement",pid,settled)
    stats = statistics(ledger,published_only=True)
    ledger.append("settlement_preview",pid,{"message":settlement_message(settled,stats),"statistics":stats})
    service = LabComboService(ledger,None,clock=lambda:old_now)
    client = transport()
    result = asyncio.run(service.publish(pid,config(),client,settlement=True))
    assert result["sent"] and result["reply_status"] == "CONFIRMED"
    assert result["reply_to"]["message_id"] == 19
    assert asyncio.run(service.publish(pid,config(),client,settlement=True))["status"] == "DELIVERY_ALREADY_CLAIMED"
    assert len(client.bot.calls) == 1


def test_early_loss_replies_once_while_remaining_legs_continue(ledger,routed,monkeypatch):
    _, _, cfg = routed
    combo = {"prediction_id":"early-reply","combined_odds":"3.375","legs":[
        {"observation_id":f"early-{i}","fixture_id":i,"market":"OVER_2_5","odds":"1.5",
         "home_team":f"H{i}","away_team":f"A{i}",
         "kickoff_utc":(NOW+timedelta(hours=-4 if i==1 else i)).isoformat()}
        for i in (1,2,3)]}
    pid = combo["prediction_id"]
    ledger.append("prediction",pid,combo)
    ledger.claim_publication("combo_prediction",combo,{"chat_id":cfg.chat_id,"delivery_route":cfg.route})
    ledger.append("receipt","combo_prediction:"+pid,{"status":"SENT","sent":True,"chat_id":cfg.chat_id,
        "message_id":8,"sent_at_utc":(NOW-timedelta(hours=5)).isoformat(),"delivery_route":cfg.route})
    service = LabComboService(ledger,None,clock=lambda:NOW,early_combo_loss=True)
    asyncio.run(service.check_results(Provider({1:payload(1)})))
    result = deepcopy(ledger.get("settlement",pid))
    assert result["status"]=="LOST" and len(result["pending_legs"])==2
    client = transport(private=True)
    sent = asyncio.run(service.publish_experimental("combo_settlement",pid,cfg,client))
    assert sent["reply_status"]=="CONFIRMED" and sent["reply_to"]["message_id"]==8
    later = LabComboService(ledger,None,clock=lambda:NOW+timedelta(hours=6))
    asyncio.run(later.check_results(Provider({2:payload(2,score=(2,2)),3:payload(3,"CANC",(None,None))})))
    assert ledger.get("settlement",pid)==result and len(ledger.all("combo_result_detail"))==1
    assert asyncio.run(later.publish_experimental("combo_settlement",pid,cfg,client))["status"]=="DELIVERY_ALREADY_CLAIMED"
    assert len(client.bot.calls)==1
