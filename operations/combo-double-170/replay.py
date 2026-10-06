"""Replay the last stored candidate pool in a temporary ledger; never publish or fetch."""
from __future__ import annotations
from datetime import datetime, timezone
from contextlib import chdir
import json
import argparse
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import socket
from types import SimpleNamespace

from app.lab_combo.repository import ComboRepository
from app.lab_v2_shadow.publication import prepare_v2_publications
from app.lab_v2_shadow.combo_double import FLAG as DOUBLE_FLAG, POLICY as DOUBLE_POLICY
from app.lab_v2_shadow.combo_agreement import FLAG as DC_FLAG, POLICY as DC_POLICY
from app.lab_v2_shadow.combo_market import FLAG, POLICY as MARKET_POLICY
from app.lab_v2_shadow.combo_market_sources import Inputs as MarketInputs
from app.lab_v2_shadow.combo_agreement_sources import Inputs
from app.real_match_lab_analysis.fingerprint import fingerprint

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-id")
    args=parser.parse_args()
    path = Path("/home/arvis/GoalVisionAI/var/lab_v2/shadow.db")
    connection = sqlite3.connect(path.as_uri()+"?mode=ro", uri=True, timeout=.2)
    connection.execute("PRAGMA query_only=ON")
    deadline=time.monotonic()+45
    connection.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
    try:
        row = connection.execute("""
            SELECT identity,created_at_utc,content_fingerprint,
                CASE WHEN length(document_json)<=33554432 THEN document_json END
            FROM lab_v2_shadow_evidence WHERE kind='rehearsal' AND (? IS NULL OR identity=?)
            ORDER BY rowid DESC LIMIT 1
        """, (args.cycle_id,args.cycle_id)).fetchone()
        if row is None or row[3] is None:
            raise ValueError("STORED_REPLAY_POOL_UNAVAILABLE")
        report = json.loads(row[3])
        if fingerprint(report) != row[2] or len(report.get("candidate_ids", [])) > 6000:
            raise ValueError("REPLAY_SOURCE_INTEGRITY_OR_CAPACITY")
        candidates = []
        for identity in report.get("candidate_ids", []):
            candidate = connection.execute("""
                SELECT content_fingerprint,CASE WHEN length(document_json)<=262144 THEN document_json END
                FROM lab_v2_shadow_evidence WHERE kind='candidate' AND identity=?
            """, (identity,)).fetchone()
            if not candidate or not candidate[1]:
                raise ValueError("REPLAY_CANDIDATE_UNAVAILABLE")
            value = json.loads(candidate[1])
            if fingerprint(value) != candidate[0]:
                raise ValueError("REPLAY_CANDIDATE_HASH_MISMATCH")
            candidates.append(value)
        cutoff = max([datetime.fromisoformat(row[1]),
            *[datetime.fromisoformat(c["goalvision_retrieved_at_utc"]) for c in candidates],
            *[datetime.fromisoformat(c["final_review_completed_at_utc"]) for c in candidates if c.get("final_review_completed_at_utc")]])
        for flag in ("GOALVISION_LAB_SINGLE_MIN_ODDS_130", "GOALVISION_LAB_SINGLE_MIN_ODDS_150",
                     "GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130", "GOALVISION_LAB_TODAY_ONLY"):
            os.environ[flag] = "1"
        os.environ[DC_FLAG] = "1"
        outcomes = {}
        with tempfile.TemporaryDirectory(prefix="goalvision-combo-replay-") as folder, chdir(folder):
            for name, mode in (("BASELINE_DC_MARKET", "0"), ("DC_DOUBLE", "1")):
                os.environ[DOUBLE_FLAG] = mode
                os.environ[FLAG] = "1" if mode == "0" else "0"
                ledger = ComboRepository(Path(folder)/"var/lab_combo"/(name+".db"))
                try:
                    result = prepare_v2_publications({"candidate_markets": candidates}, ledger,
                        now=cutoff, label_origin=True, accuracy_combos=True,
                        combo_inputs=Inputs(SimpleNamespace(connection=connection)),
                        market_combo_inputs=MarketInputs(SimpleNamespace(connection=connection)))
                    outcomes[name] = {
                        "diagnostics": result["combo_diagnostics"],
                        "single_count": len(result["singles"]),
                        "single_selection_keys": sorted(v["publication_key"] for v in result["singles"]),
                        "combos": [{"fixtures": [v["fixture_id"] for v in combo["legs"]],
                                    "markets": [v["market"] for v in combo["legs"]],
                                    "policy": combo["combo_selection_policy"],
                                    "odds": [v["captured_odds"] for v in combo["legs"]],
                                    "probabilities": [v["ensemble_probability"] for v in combo["legs"]],
                                    "teams": [v[k] for v in combo["legs"] for k in ("home_team_id","away_team_id")],
                                    "kickoffs": [v["kickoff_utc"] for v in combo["legs"]]}
                                   for combo in result["combos"]],
                        "claims": len(ledger.all("claim")), "receipts": len(ledger.all("receipt")),
                    }
                finally:
                    ledger.close()
        if outcomes["BASELINE_DC_MARKET"]["single_selection_keys"] != outcomes["DC_DOUBLE"]["single_selection_keys"]:
            raise ValueError("SINGLE_REPLAY_CHANGED")
        dc = [c for c in outcomes["DC_DOUBLE"]["combos"] if c["policy"] == DC_POLICY]
        if dc != [c for c in outcomes["BASELINE_DC_MARKET"]["combos"] if c["policy"] == DC_POLICY]:
            raise ValueError("EXISTING_DC_SELECTION_CHANGED")
        all_combos = outcomes["DC_DOUBLE"]["combos"]
        from decimal import Decimal
        from zoneinfo import ZoneInfo
        fixture_ids = [f for c in all_combos for f in c["fixtures"]]
        team_ids = [t for c in all_combos for t in c["teams"]]
        if len(fixture_ids) != len(set(fixture_ids)) or len(team_ids) != len(set(team_ids)):
            raise ValueError("CROSS_LANE_REUSE")
        if any(Decimal(o)<Decimal("1.30") for c in all_combos for o in c["odds"]):
            raise ValueError("COMBO_FLOOR_BREACH")
        if any(datetime.fromisoformat(k).astimezone(ZoneInfo("Europe/Riga")).date()!=cutoff.astimezone(ZoneInfo("Europe/Riga")).date() for c in all_combos for k in c["kickoffs"]):
            raise ValueError("TODAY_ONLY_BREACH")
        doubles=[c for c in all_combos if c['policy']==DOUBLE_POLICY]
        if len(doubles)>1 or any(c['policy']==MARKET_POLICY for c in all_combos):
            raise ValueError('DOUBLE_REPLACEMENT_POLICY_INVALID')
        if any(len(c['fixtures'])!=2 or any(Decimal(o)<Decimal('1.70') for o in c['odds'])
               or any(not Decimal('0.70')<=Decimal(p)<=Decimal('0.80') for p in c['probabilities']) for c in doubles):
            raise ValueError('DOUBLE_FILTER_INVALID')
        print(json.dumps({"kind": "DEVELOPMENT_REPLAY_ONLY", "observed_at": datetime.now(timezone.utc).isoformat(),
            "source_identity": row[0], "source_fingerprint": row[2], "as_of": cutoff.isoformat(),
            "candidate_count": len(candidates), "outcomes": outcomes,
            "production_sources_read_only": True, "production_claims_considered": False,
            "quality_verdict": "NO_PREDICTIVE_IMPROVEMENT_ESTABLISHED",
            "provider_calls": 0, "telegram_sends": 0, "champion_changed": False}, sort_keys=True, indent=2))
    finally:
        connection.close()

if __name__ == "__main__":
    def denied(*args,**kwargs): raise RuntimeError('NETWORK_FORBIDDEN')
    socket.socket.connect=denied
    socket.socket.connect_ex=denied
    socket.create_connection=denied
    main()
