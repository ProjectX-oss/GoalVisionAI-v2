import json
import sqlite3
from app.lab_v2_shadow.audit import settled_loss_postmortems


def test_v2_loss_audit_uses_frozen_evidence_without_v1_timestamp(tmp_path):
    ledger, analysis = tmp_path/"ledger.db", tmp_path/"analysis.db"
    c = sqlite3.connect(ledger)
    c.execute("CREATE TABLE evidence(kind,identity,document)")
    prediction = {"prediction_id": "p", "fixture_id": 7, "market": "HOME_WIN",
                  "captured_odds": "1.5", "ensemble_probability": ".6", "expected_value": "-.1"}
    for kind, value in (("single_prediction", prediction),
                        ("single_settlement", {"prediction_id": "p", "status": "LOST"})):
        c.execute("INSERT INTO evidence VALUES(?,?,?)", (kind, "p", json.dumps(value)))
    c.commit()
    c.close()
    sqlite3.connect(analysis).close()
    result, = settled_loss_postmortems(ledger, analysis)
    assert result["status"] == "FROZEN_V2_EVIDENCE_NO_RETROSPECTIVE_REPLAY"
    assert result["outcome"] == "LOST" and result["expected_value"] == "-.1"
