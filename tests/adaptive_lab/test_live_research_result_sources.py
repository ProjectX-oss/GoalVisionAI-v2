"""Synthetic checks for the isolated, read-only LIVE research result adapter."""
from copy import deepcopy
from pathlib import Path
import runpy

import pytest

from app.adaptive_lab.contracts import digest, utc


UNTIL = utc("2026-10-10T15:00:00+00:00")


@pytest.fixture
def audit() -> dict:
    path = Path(__file__).resolve().parents[2] / "operations/live-combo-hardening/audit.py"
    return runpy.run_path(str(path))


@pytest.fixture
def tables() -> dict:
    candidate = {
        "prediction_id": "candidate-1", "product": "LIVE", "fixture_id": 42,
        "market": "HOME_WIN", "captured_odds": "2.00",
        "ensemble_probability": "0.65",
        "prepared_at_utc": "2026-10-10T12:00:00+00:00",
        "state": {"state_fingerprint": "state"},
        "quote": {"retrieved_at": "2026-10-10T11:59:00+00:00"},
        "rates": {"source_fingerprint": "rates"},
    }
    publication = {
        "publication_id": "publication-1", "selection_id": "candidate-1",
        "product": "LIVE", "fixture_id": 42, "market": "HOME_WIN",
        "captured_odds": "2.00", "sent_at_utc": "2026-10-10T12:01:00+00:00",
        "status": "SENT", "sent": True,
    }
    settlement = {
        "publication_id": "publication-1", "selection_id": "candidate-1",
        "product": "LIVE", "fixture_id": 42, "market": "HOME_WIN",
        "odds": "2.00", "status": "WON", "provider_status": "FT",
        "fulltime_home": 2, "fulltime_away": 1,
        "settled_at_utc": "2026-10-10T14:00:00+00:00",
        "source_fingerprint": digest({"provider": "synthetic", "fixture_id": 42}),
    }
    return {
        "live_candidates": [candidate], "live_publications": [publication],
        "live_settlements": [settlement], "live_claims": [], "live_result_receipts": [],
    }


def test_live_score_labels_all_retained_markets_on_same_fixture(
    audit: dict, tables: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    markets = (
        "HOME_WIN", "DRAW", "AWAY_WIN", "OVER_2_5", "UNDER_2_5", "BTTS_YES", "BTTS_NO",
    )
    rows = [
        {**tables["live_candidates"][0], "prediction_id": f"candidate-{index}", "market": market}
        for index, market in enumerate(markets)
    ]
    facts = audit["live_results"](tables, fixture_ids={42}, until=UNTIL)
    assert len(facts) == 1
    assert facts[0]["source_product"] == "LIVE"
    assert facts[0]["source_fingerprint"] == tables["live_settlements"][0]["source_fingerprint"]
    assert facts[0]["source_document_fingerprint"] == digest(tables["live_settlements"][0])

    def synthetic_won(market: str, home: int, away: int) -> bool:
        assert (home, away) == (2, 1)
        return market in {"HOME_WIN", "OVER_2_5", "BTTS_YES"}

    monkeypatch.setattr("app.current_odds_forward_test.service._won", synthetic_won)
    summary = audit["score_rows"](rows, {42: facts[0]}, until=UNTIL)
    assert summary["outcomes"] == {"WON": 3, "LOST": 4}
    assert summary["settled"] == 7
    assert summary["ranking_eligible"] is False


@pytest.mark.parametrize(("field", "value"), [
    ("settled_at_utc", "2026-10-10T16:00:00+00:00"),
    ("settled_at_utc", "2026-10-10T11:00:00+00:00"),
    ("source_fingerprint", None),
    ("source_fingerprint", ""),
    ("selection_id", "missing-candidate"),
    ("publication_id", "missing-publication"),
    ("fixture_id", 43),
    ("market", "AWAY_WIN"),
    ("odds", "3.00"),
    ("odds", "NaN"),
    ("status", "PENDING"),
    ("status", "LOST"),
    ("retrieved_at_utc", "2026-10-10T16:00:00+00:00"),
    ("status", "VOID"),
    ("provider_status", "2H"),
    ("fulltime_home", None),
    ("fulltime_home", -1),
    ("fulltime_home", True),
])
def test_invalid_live_settlement_is_excluded(
    audit: dict, tables: dict, field: str, value: object,
) -> None:
    tables["live_settlements"][0][field] = value
    assert audit["live_results"](tables, fixture_ids={42}, until=UNTIL) == []


@pytest.mark.parametrize(("field", "value"), [
    ("selection_id", "another-candidate"),
    ("status", "UNKNOWN"),
    ("sent", False),
    ("fixture_id", 43),
    ("market", "AWAY_WIN"),
    ("captured_odds", "3.00"),
    ("sent_at_utc", "2026-10-10T11:00:00+00:00"),
    ("sent_at_utc", "2026-10-10T16:00:00+00:00"),
])
def test_invalid_publication_link_is_excluded(
    audit: dict, tables: dict, field: str, value: object,
) -> None:
    tables["live_publications"][0][field] = value
    assert audit["live_results"](tables, fixture_ids={42}, until=UNTIL) == []


@pytest.mark.parametrize("table", [
    "live_candidates", "live_publications", "live_settlements",
])
def test_combo_cannot_supply_live_labels(audit: dict, tables: dict, table: str) -> None:
    tables[table][0]["product"] = "COMBO"
    assert audit["live_results"](tables, fixture_ids={42}, until=UNTIL) == []


def test_conflicting_live_scores_reach_existing_conflict_exclusion(
    audit: dict, tables: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    conflicting = deepcopy(tables["live_settlements"][0])
    conflicting.update(fulltime_home=0, status="LOST", source_fingerprint="other-provider")
    tables["live_settlements"].append(conflicting)
    assert len(audit["live_results"](tables, fixture_ids={42}, until=UNTIL)) == 2
    names = ("A_CURRENT_60_70", "B_VALUE_CONTROL", "C_CONTEXT_CONFIDENCE")
    globals_ = audit["run"].__globals__
    frozen = []

    def compare(pool: list[dict], **kwargs: object) -> dict:
        frozen.append(True)
        return {"rows": [], "policies": {name: {"nomination": None} for name in names}}

    def prematch_results(*args: object, **kwargs: object) -> list[dict]:
        assert frozen
        return []

    class ScoringReached(Exception):
        pass

    def check_scoring(rows: list[dict], facts: dict, **kwargs: object) -> dict:
        assert facts == {}
        raise ScoringReached

    monkeypatch.setitem(globals_, "read_live", lambda *args, **kwargs: (tables, "source"))
    monkeypatch.setitem(globals_, "compare_pool", compare)
    monkeypatch.setitem(globals_, "score_rows", check_scoring)
    monkeypatch.setattr("app.dixon_coles_research.sources.results", prematch_results)
    with pytest.raises(ScoringReached):
        audit["run"](Path("unused"), Path("unused"),
                     since=utc("2026-10-10T00:00:00+00:00"), until=UNTIL)


def test_persisted_receipt_schema_without_synthetic_publication_metadata(audit, tables):
    tables["live_publications"] = [{
        "selection_id": "candidate-1", "status": "SENT", "sent": True,
        "sent_at_utc": "2026-10-10T12:01:00+00:00",
    }]
    row = tables["live_settlements"][0]
    row.pop("publication_id")
    row["prediction_id"] = row.pop("selection_id")
    row["retrieved_at_utc"] = row["settled_at_utc"]
    assert len(audit["live_results"](tables, fixture_ids={42}, until=UNTIL)) == 1
