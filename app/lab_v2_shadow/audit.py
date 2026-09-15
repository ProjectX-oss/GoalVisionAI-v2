"""Focused persisted-evidence audit and the three settled-loss post-mortems."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

from .context_signals import PlayerUsage, availability_impact
from .market_consensus import current_market_consensus
from .pi_ratings import PiRatingAdapter, parse_api_fixture_results


PREFILTER_REASONS = frozenset({
    "MALFORMED_FIXTURE_IDENTITY", "NOT_UPCOMING_OR_POSTPONED",
    "UNSUPPORTED_COMPETITION_TYPE", "STALE_OR_UNRESOLVED_SEASON",
    "NO_FIXTURE_COVERAGE", "NO_ODDS_CAPABILITY", "EXCLUDED_FIXTURE_CLASS",
    "ALREADY_STARTED", "KICKOFF_TOO_CLOSE", "DUPLICATE_EVENT",
})


def audit_recent_lab(
    ledger_path: Path, analysis_path: Path, *, window: timedelta = timedelta(hours=24),
) -> dict[str, object]:
    ledger = _connect_readonly(ledger_path)
    analysis = _connect_readonly(analysis_path)
    try:
        run_rows = ledger.execute(
            "SELECT identity, document FROM evidence WHERE kind='run' ORDER BY identity"
        ).fetchall()
        runs = [(datetime.fromisoformat(row[0]), json.loads(row[1])) for row in run_rows]
        discovery_runs = [(stamp, doc) for stamp, doc in runs if isinstance(doc.get("discovery"), dict)]
        if not discovery_runs:
            return {"status": "NO_PERSISTED_DISCOVERY_EVIDENCE"}
        end = max(stamp for stamp, _ in discovery_runs)
        start = end - window
        recent = [(stamp, doc) for stamp, doc in discovery_runs if stamp >= start]
        totals = Counter()
        skip_reasons = Counter()
        rejection_reasons = Counter()
        endpoint_calls = Counter()
        leagues = set()
        ceiling_runs = 0
        useful_unanalyzed = 0
        for _, doc in recent:
            discovery = doc["discovery"]
            totals["fixtures_discovered"] += int(discovery.get("provider_fixture_rows") or 0)
            totals["fixtures_with_current_odds"] += int(discovery.get("fresh_odds_candidates") or 0)
            totals["fixtures_with_sufficient_data"] += len(doc.get("intelligence_enrichment") or ())
            totals["candidate_markets"] += int(doc.get("candidate_markets_evaluated") or 0)
            totals["approved_candidates"] += int(doc.get("approved_single_candidates") or 0)
            totals["early"] += int(doc.get("early_candidates") or 0)
            totals["final_review"] += int(doc.get("final_review_candidates") or 0)
            totals["ready"] += int(doc.get("ready_to_publish_candidates") or 0)
            totals["api_calls_consumed"] += int(doc.get("api_calls_consumed") or 0)
            skip_reasons.update({key: int(value) for key, value in (discovery.get("skip_reasons") or {}).items()})
            rejection_reasons.update({key: int(value) for key, value in (doc.get("rejection_reasons") or {}).items()})
            for trace in discovery.get("request_cost_report") or ():
                if trace.get("competition_id") is not None:
                    leagues.add(int(trace["competition_id"]))
                endpoint_calls.update({
                    {"odds": "/odds", "team_history": "/fixtures(team history)",
                     "injuries": "/injuries", "lineups": "/fixtures/lineups",
                     "statistics": "/fixtures/statistics", "standings": "/standings",
                     "fixture_list": "/fixtures(date)"}.get(key, key): int(value)
                    for key, value in (trace.get("calls") or {}).items() if key != "retries"
                })
            for stage in discovery.get("stage_request_costs") or ():
                endpoint_calls["/leagues_or_status" if "CAPABILITY" in str(stage.get("stage")) else "/fixtures(date)"] += int(stage.get("actual_calls") or 0)
            consumed = int(doc.get("api_calls_consumed") or 0)
            if consumed >= int(discovery.get("maximum_api_calls") or 40) or (discovery.get("skip_reasons") or {}).get("API_FOOTBALL_QUOTA_INSUFFICIENT"):
                ceiling_runs += 1
                useful_unanalyzed += max(0, int(discovery.get("fresh_odds_candidates") or 0) - len(doc.get("intelligence_enrichment") or ()))
        snapshot_ids = {
            item["snapshot_id"] for _, doc in recent
            for item in (doc.get("intelligence_enrichment") or ()) if item.get("snapshot_id")
        }
        for snapshot_id in sorted(snapshot_ids):
            row = analysis.execute(
                "SELECT snapshot_json FROM current_match_intelligence_snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
            snapshot = json.loads(row[0]) if row else {}
            for call in snapshot.get("api_calls") or ():
                endpoint_calls[str(call.get("endpoint") or "UNKNOWN")] += int(call.get("calls_used") or 0)
        totals["fixtures_excluded_before_odds"] = sum(skip_reasons[key] for key in PREFILTER_REASONS)
        attributed_calls = sum(endpoint_calls.values())
        if totals["api_calls_consumed"] > attributed_calls:
            endpoint_calls["/status_or_unattributed_failure"] = totals["api_calls_consumed"] - attributed_calls
        return {
            "status": "AVAILABLE_WITH_PERSISTENCE_LIMITATIONS",
            "window_start_utc": start.astimezone(timezone.utc).isoformat(),
            "window_end_utc": end.astimezone(timezone.utc).isoformat(),
            "discovery_cycles": len(recent),
            **dict(totals),
            "deeply_evaluated_leagues": len(leagues),
            "deeply_evaluated_league_ids": sorted(leagues),
            "all_encountered_leagues": "NOT_RECONSTRUCTABLE_V1_PERSISTS_COUNTS_NOT_ROW_IDENTITIES",
            "skip_reasons": dict(sorted(skip_reasons.items())),
            "rejection_reasons": dict(sorted(rejection_reasons.items())),
            "api_call_allocation": dict(sorted(endpoint_calls.items())),
            "runs_reaching_40_call_or_quota_ceiling": ceiling_runs,
            "fresh_odds_fixtures_left_unenriched_on_ceiling_runs": useful_unanalyzed,
            "league_restriction": {
                "hard_major_league_only_gate": False,
                "effective_bias": "FIXED_PRIORITY_COMPETITIONS_RUN_BEFORE_ALL_SUPPORTED_FALLBACK",
                "advanced_data_gate": "V1_REQUIRES_LINEUPS_INJURIES_TEAM_STATS_AND_HISTORY_FOR_EVERY_MARKET",
            },
            "measurement_note": "Counts are cycle observations and include repeated fixtures across cycles.",
        }
    finally:
        ledger.close(); analysis.close()


def settled_loss_postmortems(ledger_path: Path, analysis_path: Path) -> list[dict[str, object]]:
    ledger, analysis = _connect_readonly(ledger_path), _connect_readonly(analysis_path)
    try:
        predictions = {
            row[0]: json.loads(row[1]) for row in ledger.execute(
                "SELECT identity, document FROM evidence WHERE kind='single_prediction'"
            )
        }
        losses = [json.loads(row[0]) for row in ledger.execute(
            "SELECT document FROM evidence WHERE kind='single_settlement' AND json_extract(document,'$.status')='LOST' ORDER BY identity"
        )]
        results = []
        for settled in losses:
            prediction = predictions[settled["prediction_id"]]
            evaluated = datetime.fromisoformat(prediction["evaluated_at_utc"])
            snapshot = _snapshot(analysis, prediction.get("snapshot_id"))
            fields = {item["name"]: item.get("value") for item in snapshot.get("fields", ())}
            histories = _history_payloads(analysis, evaluated)
            matches = parse_api_fixture_results(histories)
            league_id = int(prediction["competition_id"])
            pi = PiRatingAdapter(league_id)
            pi.replay(matches, before=datetime.fromisoformat(prediction["kickoff_utc"]))
            pi_signal = pi.signal(int(prediction["home_team_id"]), int(prediction["away_team_id"]))
            odds_payload, retrieved = _odds_payload(analysis, int(prediction["fixture_id"]), evaluated)
            consensus = current_market_consensus(
                odds_payload, fixture_id=int(prediction["fixture_id"]),
                retrieved_at=retrieved, now=retrieved,
            ) if odds_payload is not None and retrieved is not None else {}
            family = _family(prediction["market"])
            market_consensus = consensus.get(family)
            impacts = {}
            for side in ("home", "away"):
                absences = _absences(fields, side)
                usage = _usage(fields, side)
                impacts[side] = asdict(availability_impact(absences, usage))
            v2_reasons = ["INSUFFICIENT_INDEPENDENT_SIGNALS"]
            if market_consensus is None or market_consensus.status != "AVAILABLE":
                v2_reasons.append("MULTI_BOOK_CURRENT_CONSENSUS_UNAVAILABLE")
            elif market_consensus.fair_probabilities.get(prediction["market"], Decimal(0)) <= Decimal(1) / Decimal(prediction["captured_odds"]):
                v2_reasons.append("CURRENT_CONSENSUS_DOES_NOT_SUPPORT_VALUE")
            if prediction.get("lineup_status") != "CONFIRMED":
                v2_reasons.append("LINEUP_NOT_CONFIRMED_DOWNGRADE_WHERE_SUPPORTED")
            # API prediction was not collected by V1; never fetch it retrospectively.
            v2_reasons.append("API_PREDICTION_NOT_PERSISTED")
            results.append({
                "fixture": f"{prediction.get('home_team')} vs {prediction.get('away_team')}",
                "fixture_id": prediction["fixture_id"], "league": prediction.get("competition"),
                "market": prediction["market"], "odds": prediction["captured_odds"],
                "result": f"{settled.get('fulltime_home')}-{settled.get('fulltime_away')}",
                "v1_approval_signals": {
                    "experimental_probability": prediction.get("experimental_signal"),
                    "single_book_implied_probability": prediction.get("implied_market_probability"),
                    "market_context_edge": prediction.get("market_context_edge"),
                    "confidence": prediction.get("experimental_confidence"),
                    "approval_reasons": prediction.get("approval_reasons"),
                },
                "pi_signal": _plain(asdict(pi_signal)),
                "api_football_prediction": "NOT_PERSISTED_NO_RETROSPECTIVE_FETCH",
                "lineup_status": prediction.get("lineup_status"),
                "availability_impact": _plain(impacts),
                "market_consensus": _plain(asdict(market_consensus)) if market_consensus else "NOT_CAPTURED_AS_COMPARABLE_CONSENSUS",
                "v2_disposition": "REJECT_OR_DOWNGRADE",
                "v2_reasons": sorted(set(v2_reasons)),
            })
        return results
    finally:
        ledger.close(); analysis.close()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _snapshot(connection: sqlite3.Connection, snapshot_id: object) -> dict:
    row = connection.execute(
        "SELECT snapshot_json FROM current_match_intelligence_snapshots WHERE snapshot_id=?", (snapshot_id,)
    ).fetchone()
    return json.loads(row[0]) if row else {}


def _history_payloads(connection: sqlite3.Connection, before: datetime) -> list[object]:
    rows = connection.execute(
        """SELECT payload_json FROM current_match_intelligence_cache
        WHERE endpoint='/fixtures' AND query_json LIKE '%\"team\"%'
        AND retrieved_at<=? ORDER BY retrieved_at""", (before.isoformat(),)
    ).fetchall()
    return [json.loads(row[0]) for row in rows]


def _odds_payload(connection: sqlite3.Connection, fixture_id: int, before: datetime) -> tuple[object | None, datetime | None]:
    row = connection.execute(
        """SELECT payload_json,retrieved_at FROM current_match_intelligence_cache
        WHERE endpoint='/odds' AND query_json=? AND retrieved_at<=?
        ORDER BY retrieved_at DESC LIMIT 1""",
        (json.dumps({"fixture": fixture_id}, separators=(",", ":"), sort_keys=True), before.isoformat()),
    ).fetchone()
    return (json.loads(row[0]), datetime.fromisoformat(row[1])) if row else (None, None)


def _absences(fields: dict[str, object], side: str) -> list[dict[str, object]]:
    ids = {name.split(".")[2] for name in fields if name.startswith(f"{side}.availability.") and name.endswith(".player_id")}
    return [{"player_id": player, "status": fields.get(f"{side}.availability.{player}.status")} for player in sorted(ids)]


def _usage(fields: dict[str, object], side: str) -> dict[str, PlayerUsage]:
    result = {}
    prefix = f"{side}.player_usage."
    for name, value in fields.items():
        if name.startswith(prefix) and name.endswith(".recent_starts"):
            player = name[len(prefix):].split(".")[0]
            result[player] = PlayerUsage(player_id=player, starts=int(value), recent_start_frequency=Decimal(str(value)) / Decimal(3))
    return result


def _family(market: str) -> str:
    if market in {"HOME_WIN", "DRAW", "AWAY_WIN"}: return "1X2"
    if market.startswith(("OVER_", "UNDER_")): return "TOTAL_" + market.split("_", 1)[1]
    return "BTTS"


def _plain(value: object) -> object:
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, dict): return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [_plain(item) for item in value]
    return value
