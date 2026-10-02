"""Inert-by-default de-vig adapters: current inputs in, research evidence out."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Callable

from app.real_match_lab_analysis.fingerprint import fingerprint
from app.lab_v2_shadow.market_consensus import _market, _FAMILIES
from app.lab_v2_shadow.single_odds_policy import FLOOR_SELECTION_POLICY, minimum_single_odds
from .contracts import canonical, digest, utc
from .devig_research import VERSION, capture, capture_prefix, capture_identity, forward_metrics

ENVIRONMENT_FLAG = "GOALVISION_LAB_DEVIG_RESEARCH"
MAX_CAPTURE_ROWS = 50_000
MAX_CAPTURE_BYTES = 256 * 1024 * 1024


def enabled() -> bool:
    """Only the exact opt-in value enables this isolated research consumer."""
    return os.environ.get(ENVIRONMENT_FLAG, "0") == "1"


def unavailable(reason: str) -> dict:
    return {"version": VERSION, "status": "UNAVAILABLE", "reason": reason,
            "quality_verdict": "NEEDS_MORE_EVIDENCE", "selection_effect": "NONE",
            "model_learning_observations": 0}


def _json_value(value: object) -> str:
    # Match the existing runner's persisted Decimal spelling exactly.
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError("UNSUPPORTED_RESEARCH_SOURCE_TYPE")


def _duplicate_issues(payload: dict, fixture_id: int, family: str) -> list[dict]:
    from app.lab_v2_shadow.market_consensus import _FAMILIES
    counts: Counter = Counter()
    for row in payload.get("response", []):
        if str((row.get("fixture") or {}).get("id")) != str(fixture_id):
            continue
        for book in row.get("bookmakers", []):
            bid = book.get("id")
            bid = int(bid) if bid is not None else None
            name = str(book.get("name") or bid or "UNKNOWN")
            for bet in book.get("bets", []):
                for price in bet.get("values", []):
                    market = _market(str(bet.get("name", "")), str(price.get("value", "")))
                    if market in _FAMILIES[family]:
                        counts[(bid, name, market)] += 1
    return [{"bookmaker_id": bid, "bookmaker": name, "market": market}
            for (bid, name, market), n in sorted(counts.items(), key=lambda i: str(i[0])) if n > 1]


def _valid_books(record: dict) -> set[tuple]:
    return {(b["bookmaker_id"], b["bookmaker"]) for b in record["bookmakers"]
            if b["status"] == "AVAILABLE"} if record["status"] == "AVAILABLE" else set()


def _needs_capture(connection: sqlite3.Connection, record: dict) -> bool:
    """Indexed first-observation sampling, not one full record per timer tick."""
    prefix = capture_prefix(record["fixture_id"], record["market_family"])
    rows = connection.execute(
        "SELECT identity,content_fingerprint,document_json FROM lab_v2_shadow_evidence "
        "WHERE kind='devig_research' AND identity>=? AND identity<? LIMIT 1001",
        (prefix, prefix+"~")).fetchall()
    if len(rows) > 1000:
        raise ValueError("RESEARCH_FAMILY_CAPACITY_EXCEEDED")
    seen = set()
    current = _valid_books(record)
    for identity, fp, raw in rows:
        previous = json.loads(raw)
        if (digest(previous) != fp or previous.get("capture_id") != identity or
                capture_identity({k:v for k,v in previous.items() if k != "capture_id"}) != identity):
            raise ValueError("RESEARCH_STORAGE_INTEGRITY_FAILURE")
        if utc(previous["captured_at"]) > utc(record["captured_at"]):
            raise ValueError("RESEARCH_BACKDATED_CAPTURE")
        books = _valid_books(previous)
        if (previous["captured_at"] == record["captured_at"] and identity != record["capture_id"]
                and books & current):
            raise ValueError("AMBIGUOUS_FIRST_FORWARD_CAPTURE")
        seen.update(books)
    # Retain initial missing/blocked evidence; admit a later first valid bookmaker.
    # Subsequent cycle availability remains visible in the existing cycle report.
    return not rows or bool(current - seen)


def capture_cycle(repository: object, odds_evidence: dict, fixtures: dict,
                  candidates: list[dict], *, clock: datetime,
                  runtime_clock: Callable[[], datetime] | None, today_only: bool) -> dict:
    """Use only already received inputs, after selection. No provider access."""
    by_fixture: dict[int, dict] = {}
    for candidate in candidates:
        refs = by_fixture.setdefault(candidate["fixture_id"], {})
        market = candidate["market"]
        if market in refs:
            raise ValueError("AMBIGUOUS_RESEARCH_MODEL_REFERENCE")
        refs[market] = {"probability": candidate.get("ensemble_probability"),
                        "candidate_id": candidate["candidate_id"],
                        "candidate_fingerprint": fingerprint(candidate),
                        **{k: candidate.get(k) for k in ("model_generation", "model_artifact_identity",
                           "calibration_status", "profile_policy_version", "readiness_policy_version")}}
    minimum = minimum_single_odds()
    context = {"single_policy": FLOOR_SELECTION_POLICY if minimum is not None else
               "LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V2_NO_ODDS_FLOOR",
               "single_minimum": str(minimum) if minimum is not None else None,
               "today_only": today_only, "combo_minimum": None,
               "scope": "ALL_CAPTURED_CURRENT_MARKETS_NOT_ONLY_PUBLISHED"}
    counts: Counter = Counter()
    # Research-only lock contention must not delay the publication path by 30s.
    connection = repository.connection
    previous_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    try:
        connection.execute("PRAGMA busy_timeout=50")
        for fid, (payload, retrieved, families) in sorted(odds_evidence.items()):
            if fid not in fixtures:
                counts["missing_fixture"] += 1
                continue
            for family in sorted(_FAMILIES):
                consensus = families.get(family)
                stamp = runtime_clock() if runtime_clock else clock
                # In offline/frozen execution, a provider receipt may be later than
                # cycle start. In runtime use the actual clock; never future-date.
                if runtime_clock is None:
                    stamp = max(clock, retrieved)
                source = (json.loads(json.dumps(asdict(consensus), default=_json_value, allow_nan=False)) if consensus is not None else
                          {"fixture_id": fid, "market_family": family, "status": "CURRENT_QUOTES_UNAVAILABLE",
                           "quotes": []})
                source.update(source="API_FOOTBALL_CURRENT_ODDS", historical_bookmaker_odds_used=False,
                              retrieved_at_utc=retrieved.isoformat())
                record = capture(source, captured_at=stamp, kickoff=fixtures[fid]["kickoff_utc"],
                                 model_probabilities=by_fixture.get(fid, {}), policy_context=context,
                                 source_issues=_duplicate_issues(payload, fid, family))
                if _needs_capture(connection, record):
                    added = repository.append("devig_research", record["capture_id"], record, created_at=stamp)
                    counts["persisted" if added else "replayed"] += 1
                else:
                    counts["already_captured"] += 1
                counts[record["status"]] += 1
                if record.get("reason"):
                    counts["reason:" + record["reason"]] += 1
    finally:
        connection.execute(f"PRAGMA busy_timeout={int(previous_timeout)}")
    return {"version": VERSION, "status": "CAPTURED", "counts": dict(counts),
            "selection_effect": "NONE", "additional_provider_calls": 0,
            "model_learning_observations": 0}


def read_captures(path: Path, *, now: datetime) -> list[dict]:
    """Bounded read-only snapshot; release source locks before parsing/scoring."""
    deadline = time.monotonic() + 5
    connection = sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True, timeout=.1)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        rows, size = [], 0
        cursor = connection.execute(
            "SELECT identity,created_at_utc,content_fingerprint,document_json "
            "FROM lab_v2_shadow_evidence WHERE kind='devig_research' AND created_at_utc<=? "
            "ORDER BY created_at_utc,identity LIMIT ?", (utc(now).isoformat(), MAX_CAPTURE_ROWS+1))
        for row in cursor:
            size += len(row[3].encode())
            if len(rows) >= MAX_CAPTURE_ROWS or size > MAX_CAPTURE_BYTES:
                raise ValueError("RESEARCH_SNAPSHOT_CAPACITY_EXCEEDED")
            rows.append(row)
    finally:
        connection.close()
    values = []
    for identity, created, fp, raw in rows:
        record = json.loads(raw)
        if (digest(record) != fp or record.get("capture_id") != identity
                or utc(record["captured_at"]) != utc(created)):
            raise ValueError("RESEARCH_STORAGE_INTEGRITY_FAILURE")
        values.append(record)
    return values



def persist_metrics(path: Path, snapshot: dict, *, now: datetime) -> None:
    """Append full metrics separately; never expand the ADMIN health document.

    Uses the already initialized shadow evidence table. No file/schema creation,
    no overwriting history, and no long source read transaction.
    """
    fp = snapshot["snapshot_fingerprint"]
    if fp != digest({k: v for k, v in snapshot.items() if k != "snapshot_fingerprint"}):
        raise ValueError("RESEARCH_METRICS_FINGERPRINT_MISMATCH")
    if utc(snapshot["as_of"]) != utc(now):
        raise ValueError("RESEARCH_METRICS_CUTOFF_MISMATCH")
    identity, content = "devig-metrics-" + fp, canonical(snapshot)
    connection = sqlite3.connect(path.resolve().as_uri()+"?mode=rw", uri=True, timeout=.05)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT content_fingerprint FROM lab_v2_shadow_evidence WHERE kind=? AND identity=?",
                ("devig_metrics", identity)).fetchone()
            if previous is not None:
                if previous[0] != digest(snapshot):
                    raise ValueError("RESEARCH_METRICS_CONFLICT")
                return
            connection.execute("INSERT INTO lab_v2_shadow_evidence VALUES (?,?,?,?,?)",
                               ("devig_metrics", identity, utc(now).isoformat(), digest(snapshot), content))
    finally:
        connection.close()


def _result(row: dict, *, product: str) -> dict:
    terminal = row.get("status") or row.get("outcome")
    return {"fixture_id": int(row["fixture_id"]),
            "status": ("VOID" if terminal == "VOID" else "RESOLVED"
                       if row.get("provider_status") in {"FT", "AET", "PEN"} else "UNRESOLVED"),
            "home_goals": row.get("fulltime_home"), "away_goals": row.get("fulltime_away"),
            "settled_at": row.get("settled_at_utc") or row.get("retrieved_at_utc"),
            "source_fingerprint": row.get("source_fingerprint"),
            "source_document_fingerprint": digest(row), "source_product": product}


def observed_snapshot(repository: object, ledger: object, path: Path, *, now: datetime) -> dict:
    """Use existing single/canonical/shadow result facts, never combo legs."""
    try:
        captures = read_captures(path, now=now)
        results = [_result(row, product="SINGLE") for row in ledger.all("single_settlement")]
        results.extend(_result(row, product="SHADOW")
                       for row in repository.all("canonical_results", "PREMATCH"))
        for row in repository.all("shadow_settlements", "PREMATCH"):
            observation = row.get("shadow_observation") or {}
            result = observation.get("result_evidence")
            if result:
                results.append(_result(result, product="SHADOW"))
        return forward_metrics(captures, results, now=now)
    except Exception as exc:
        # This is only the optional research adapter. Core observer import,
        # settlement and publication validation execute outside this boundary.
        reason = str(exc) if isinstance(exc, ValueError) and str(exc) in {
            "RESEARCH_SNAPSHOT_CAPACITY_EXCEEDED", "RESEARCH_STORAGE_INTEGRITY_FAILURE",
            "RESEARCH_CAPTURE_REQUIRED", "RESEARCH_CAPTURE_REPRODUCTION_FAILED",
            "CONFLICTING_FORWARD_RESULT", "AMBIGUOUS_FIRST_FORWARD_CAPTURE"} else "RESEARCH_EVALUATION_UNAVAILABLE"
        return unavailable(reason)
