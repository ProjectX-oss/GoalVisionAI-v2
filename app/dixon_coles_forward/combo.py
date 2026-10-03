"""Deterministic paired shadow triples; ranking scores are not probabilities."""
from collections import Counter
from datetime import datetime
from decimal import Decimal
from itertools import combinations
from zoneinfo import ZoneInfo
from app.dixon_coles_research.repository import ResearchStore
from app.dixon_coles_research.contracts import seal, verify, utc, integer
from app.dixon_coles_research.metrics import won
from app.lab_v2_shadow.publication_policy import review_accuracy_publication
from app.lab_v2_shadow.publication import _single_rank
from .contracts import VERSION, verify_plan, reserved

POLICIES = ("ENSEMBLE_BASELINE", "CONSERVATIVE_AGREEMENT")
RIGA = ZoneInfo("Europe/Riga")

def day(now: datetime) -> str:
    return utc(now).astimezone(RIGA).date().isoformat()

def select(pool: list[dict], policy: str) -> list[dict]:
    if policy not in POLICIES:
        raise ValueError("UNKNOWN_COMBO_SHADOW_POLICY")
    score = "ensemble_probability" if policy == POLICIES[0] else "ranking_score"
    ready = {}
    for leg in pool:
        key = int(leg["fixture_id"])
        tie = leg["tie_rank"]
        rank = (-Decimal(leg[score]), (int(tie[0]), Decimal(tie[1]), tie[2], int(tie[3]), tie[4]))
        if key not in ready or rank < ready[key][0]:
            ready[key] = rank, leg
    available = [v[1] for v in ready.values()]
    triples = []
    while len(triples) < 3:
        best = None
        for group in combinations(available, 3):
            teams = {str(leg[k]) for leg in group for k in ("home_team_id", "away_team_id")}
            if len(teams) != 6:
                continue
            product = Decimal(1)
            for leg in group:
                product *= Decimal(leg[score])
            rank = (-product, tuple(sorted(leg["selection_key"] for leg in group)))
            if best is None or rank < best[0]:
                best = rank, group, teams
        if best is None:
            break
        _, group, teams = best
        odds = Decimal(1); dc = Decimal(1); ens = Decimal(1)
        for leg in group:
            odds *= Decimal(leg["odds"]); dc *= Decimal(leg["dc_probability"])
            ens *= Decimal(leg["ensemble_probability"])
        legs = sorted(group, key=lambda leg: leg["selection_key"])
        triples.append({"legs": legs, "combined_odds": str(odds),
                        "dc_joint_if_independent": str(dc), "ensemble_joint_if_independent": str(ens),
                        "ranking_score": str(-best[0][0]), "independence": "ASSUMED_NOT_VERIFIED"})
        fixtures = {leg["fixture_id"] for leg in legs}
        available = [leg for leg in available if leg["fixture_id"] not in fixtures
                     and not teams.intersection({str(leg["home_team_id"]), str(leg["away_team_id"])})]
    return triples

def build_batch(forecasts: list[dict], *, plan: dict, now: datetime,
                used_fixtures: frozenset[int] = frozenset(),
                used_teams: frozenset[str] = frozenset()) -> dict:
    verify_plan(plan); cutoff = utc(now); counts = Counter(); pool = []
    for record in sorted(forecasts, key=lambda v: v["fingerprint"]):
        verify(record)
        if record["version"] != VERSION or record["plan_fingerprint"] != plan["fingerprint"]:
            raise ValueError("COMBO_FORWARD_COHORT_MIXING")
        fid = record["fixture_id"]
        if fid in reserved(plan) or fid in used_fixtures:
            counts["excluded_or_used_fixture"] += 1; continue
        if not utc(record["forecast_at"]) <= cutoff < utc(record["kickoff_utc"]) or day(record["kickoff_utc"]) != day(cutoff):
            counts["not_today_upcoming"] += 1; continue
        for market, methods in sorted(record["comparisons"].items()):
            candidate = record["candidate_references"][market]
            if candidate.get("candidate_lane") == "TRACKING" or candidate.get("stage") not in {"READY_TO_PUBLISH", "REJECTED"}:
                counts["candidate_not_accuracy_lane"] += 1; continue
            if {str(candidate["home_team_id"]), str(candidate["away_team_id"])} & used_teams:
                counts["team_already_used_today"] += 1; continue
            odds = Decimal(str(candidate["captured_odds"]))
            ensemble = Decimal(str(candidate["ensemble_probability"]))
            if odds < Decimal("1.30"):
                counts["leg_below_130"] += 1; continue
            if ensemble < Decimal("0.55"):
                counts["ensemble_probability_below_existing_minimum"] += 1; continue
            review = review_accuracy_publication(candidate, now=cutoff)
            if not review["eligible"]:
                counts.update(review["rejection_reasons"]); continue
            if "MULTIPLICATIVE" not in methods:
                counts["missing_paired_devig"] += 1; continue
            dc = Decimal(str(methods["DIXON_COLES"]))
            market_p = Decimal(str(methods["MULTIPLICATIVE"]))
            conservative = min(dc, ensemble, market_p)
            # Retain the existing tie preference without treating this score as calibrated.
            tie = _single_rank(candidate)[1:]
            pool.append({"fixture_id": fid, "market": market,
                "home_team_id": candidate["home_team_id"], "away_team_id": candidate["away_team_id"],
                "kickoff_utc": record["kickoff_utc"], "candidate_id": candidate["candidate_id"],
                "selection_key": f"{fid}:{market}", "forecast_fingerprint": record["fingerprint"],
                "quote_fingerprint": candidate["quote_provenance_fingerprint"], "odds": str(odds),
                "dc_probability": str(dc), "ensemble_probability": str(ensemble),
                "multiplicative_probability": str(market_p), "ranking_score": str(conservative),
                "tie_rank": [str(v) for v in tie]})
    return seal({"version": VERSION, "kind": "PAIRED_COMBO_SHADOW", "plan_fingerprint": plan["fingerprint"],
        "selected_at": cutoff.isoformat(), "source_forecasts": sorted(r["fingerprint"] for r in forecasts),
        "used_fixtures": sorted(used_fixtures), "used_teams": sorted(used_teams),
        "pool": sorted(pool, key=lambda v: v["selection_key"]), "rejection_counts": dict(sorted(counts.items())),
        "selections": {policy: select(pool, policy) for policy in POLICIES},
        "eligible_fixtures": len({r["fixture_id"] for r in pool}),
        "score_is_calibrated_probability": False, "selection_effect": "NONE",
        "accounting": "SHADOW_ONLY_HYPOTHETICAL_ONE_UNIT", "telegram_publication": False})

def capture(forecasts: list[dict], store: ResearchStore, *, plan: dict, now: datetime) -> dict:
    used_fixtures = set(); used_teams = set()
    for previous in store.all("combo_batch"):
        verify(previous)
        if previous["plan_fingerprint"] != plan["fingerprint"]:
            raise ValueError("COMBO_FORWARD_COHORT_MIXING")
        for triples in previous["selections"].values():
            for triple in triples:
                for leg in triple["legs"]:
                    used_fixtures.add(leg["fixture_id"])
                    if day(previous["selected_at"]) == day(now):
                        used_teams.update(str(leg[k]) for k in ("home_team_id", "away_team_id"))
    batch = build_batch(forecasts, plan=plan, now=now, used_fixtures=frozenset(used_fixtures),
                        used_teams=frozenset(used_teams))
    store.append("combo_batch", batch["fingerprint"], batch)
    return batch

def evaluate(batches: list[dict], forecasts: list[dict], results: list[dict], *, plan: dict,
             now: datetime, additional_reserved: frozenset[int] = frozenset()) -> dict:
    verify_plan(plan); outcomes = {}; records = {v["fingerprint"]: v for v in forecasts}
    for result in results:
        fid = integer(result["fixture_id"])
        if fid in reserved(plan, additional_reserved) or result.get("source_product") not in {"SINGLE", "SHADOW"}:
            continue
        if utc(result["settled_at"]) > utc(now) or result.get("status") not in {"RESOLVED", "VOID"}:
            continue
        if not result.get("source_fingerprint"):
            raise ValueError("RESULT_PROVENANCE")
        if result["status"] == "RESOLVED":
            integer(result["home_goals"], low=0, high=30); integer(result["away_goals"], low=0, high=30)
        old = outcomes.get(fid)
        if old and any(old.get(k) != result.get(k) for k in ("status", "home_goals", "away_goals")):
            raise ValueError("CONFLICTING_FORWARD_RESULT")
        if old is None or utc(result["settled_at"]) < utc(old["settled_at"]):
            outcomes[fid] = result
    policy_rows = {p: [] for p in POLICIES}; used = set()
    previous_legs = []; exposed_fixtures = set()
    for batch in sorted(batches, key=lambda b: (b["selected_at"], b["fingerprint"])):
        verify(batch)
        if utc(batch["selected_at"]) > utc(now):
            continue
        if batch["fingerprint"] in used:
            raise ValueError("DUPLICATE_COMBO_BATCH")
        used.add(batch["fingerprint"])
        expected_teams = {str(leg[k]) for date,leg in previous_legs
                          if date == day(batch["selected_at"]) for k in ("home_team_id", "away_team_id")}
        if set(batch["used_fixtures"]) != exposed_fixtures or set(batch["used_teams"]) != expected_teams:
            raise ValueError("COMBO_EXPOSURE_HISTORY_MISMATCH")
        replay = build_batch([records[k] for k in batch["source_forecasts"]], plan=plan,
            now=utc(batch["selected_at"]), used_fixtures=frozenset(batch["used_fixtures"]),
            used_teams=frozenset(batch["used_teams"]))
        if replay != batch:
            raise ValueError("COMBO_BATCH_REPRODUCTION_FAILED")
        for triples in batch["selections"].values():
            for triple in triples:
                for leg in triple["legs"]:
                    exposed_fixtures.add(leg["fixture_id"])
                    previous_legs.append((day(batch["selected_at"]), leg))
        for policy, triples in batch["selections"].items():
            for triple in triples:
                if any(leg["fixture_id"] in reserved(plan, additional_reserved) for leg in triple["legs"]):
                    continue
                settled = []; remaining = []; payout = Decimal(1)
                for leg in triple["legs"]:
                    result = outcomes.get(leg["fixture_id"])
                    if result is None:
                        remaining.append(leg["fixture_id"]); continue
                    if utc(result["settled_at"]) <= utc(leg["kickoff_utc"]):
                        raise ValueError("RESULT_BEFORE_KICKOFF")
                    outcome = ("VOID" if result["status"] == "VOID" else
                               "WON" if won(leg["market"], result["home_goals"], result["away_goals"]) else "LOST")
                    settled.append(outcome)
                    if outcome == "WON":
                        payout *= Decimal(leg["odds"])
                status = ("LOST" if "LOST" in settled else "PENDING" if remaining else
                          "VOID" if all(v == "VOID" for v in settled) else
                          "PARTIAL_VOID" if "VOID" in settled else "WON")
                profit = None if status == "PENDING" else "-1" if status == "LOST" else str(payout-1)
                policy_rows[policy].append({"batch": batch["fingerprint"], "status": status,
                    "profit_units": profit, "remaining_fixtures": remaining})
    summaries = {}
    for policy, rows in policy_rows.items():
        closed = [r for r in rows if r["profit_units"] is not None]
        profit = sum((Decimal(r["profit_units"]) for r in closed), Decimal(0))
        summaries[policy] = {"bets": len(rows), "settled": len(closed),
            "lifecycle": dict(Counter(r["status"] for r in rows)), "profit_units": str(profit),
            "roi_per_settled_staked_unit": str(profit / len(closed)) if closed else None, "rows": rows}
    return seal({"version": VERSION, "plan_fingerprint": plan["fingerprint"], "as_of": utc(now).isoformat(),
        "policies": summaries, "quality_verdict": "NEEDS_MORE_EVIDENCE",
        "scope": "PAIRED_COVERED_POOL; SHARED_FIXTURES_CORRELATED; NOT_LIVE_PUBLICATION_REPLAY",
        "selection_effect": "NONE", "automatic_promotion": False})
