"""Explicit offline research entry point. No providers, Telegram, or promotion."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from app.real_match_lab_analysis.fingerprint import fingerprint
from .contracts import utc
from .shadow_research import xg, forward_metrics, validate_capture
from .dynamic_strength import capture as strength


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command",required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--method",choices=("xg","dynamic-strength"),required=True)
    capture.add_argument("--input",type=Path,required=True)
    capture.add_argument("--journal",type=Path,required=True)
    metrics = sub.add_parser("metrics")
    metrics.add_argument("--journal",type=Path,required=True)
    metrics.add_argument("--results",type=Path,required=True)
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    if args.command == "capture":
        envelope = json.loads(args.input.read_text())
        try:
            value = (xg if args.method=="xg" else strength)(
                envelope["context"],now=now,references=envelope.get("references"))
            validate_capture(value)
        except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
            print(json.dumps({"status":"BLOCKED","reason":str(exc),"research_only":True}))
            return 2
        from app.lab_v2_shadow.repository import ShadowEvidenceRepository
        repo = ShadowEvidenceRepository(args.journal)
        try:
            added = repo.append("context_research",value["capture_id"],value,created_at=now)
        finally:
            repo.close()
        print(json.dumps({"status":"CAPTURED","capture_id":value["capture_id"],
                          "appended":added,"publication_eligible":False}))
        return 0
    connection = sqlite3.connect(args.journal.resolve().as_uri()+"?mode=ro",uri=True,
                                 isolation_level=None,timeout=.2)
    try:
        rows = connection.execute("SELECT content_fingerprint,document_json FROM lab_v2_shadow_evidence WHERE kind='context_research'").fetchall()
    finally:
        connection.close()
    records = []
    for expected,document in rows:
        row = json.loads(document)
        if fingerprint(row) != expected:
            raise ValueError("SHADOW_JOURNAL_INTEGRITY_FAILURE")
        records.append(row)
    print(json.dumps(forward_metrics(records,json.loads(args.results.read_text()),now=now),sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
