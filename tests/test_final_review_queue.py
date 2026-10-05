"""Offline regression for missed final reviews; real runner and fake provider only."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import socket

import pytest

from app.lab_v2_shadow.capability import LeagueCapabilityCache
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.runner import LabV2ShadowRunner, _fixture_rows_with_evidence
from app.lab_v2_shadow.tracking import new_review
from test_lab_v2_global import fixture
from test_lab_v2_shadow import FakeClient, Response, NOW, odds_payload


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Real network forbidden in final-review regression")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def row(identity, *, minutes=45, priority=False, now=NOW):
    value = fixture("World Cup" if priority else "Regional Division 4", identity)
    value["fixture"]["date"] = (now + timedelta(minutes=minutes)).isoformat()
    return value


class QueueClient(FakeClient):
    def __init__(self, rows, *, clock=NOW, failures=()):
        super().__init__()
        self.rows = {r["fixture"]["id"]: deepcopy(r) for r in rows}
        self.clock, self.failures, self.requests = clock, set(failures), []

    def _hit(self, endpoint, query, payload):
        value = super()._hit(endpoint, query, payload)
        self.last["retrieved_at_utc"] = self.clock.isoformat()
        self.requests.append((endpoint, query))
        return value

    async def leagues(self, *, current=True):
        return self._hit("/leagues", {}, {"response": []})

    async def fixtures_by_date(self, day, *, timezone_name="UTC"):
        return self._hit("/fixtures", {"date": day}, {"response": list(self.rows.values())})

    async def fixture(self, identity):
        return self._hit("/fixtures", {"id": identity}, {"response": [self.rows[identity]]})

    async def current_odds_by_date(self, day, *, page=1):
        return self._hit("/odds", {"date": day, "page": page}, {
            "response": [odds_payload(self.clock, fixture_id=i)["response"][0] for i in self.rows],
            "paging": {"current": 1, "total": 1}})

    async def current_odds(self, identity):
        payload = ({"response": []} if identity in self.failures
                   else odds_payload(self.clock, fixture_id=identity))
        return self._hit("/odds", {"fixture": identity}, payload)

    async def finished_matches(self, league_id, season, last=99):
        return self._hit("/fixtures", {"league": league_id}, [])

    async def _get(self, endpoint, *, params):
        if endpoint == "/odds/bookmakers":
            return await super()._get(endpoint, params=params)
        return Response(self._hit(endpoint, params, {"response": []}))


def cycle(tmp_path, monkeypatch, rows, *, clock=NOW, tracked=(), maximum=200, failures=()):
    monkeypatch.chdir(tmp_path)
    repo = ShadowEvidenceRepository(tmp_path / "shadow.db")
    capabilities = LeagueCapabilityCache.from_api_payload({"response": []}, retrieved_at=clock)
    accepted, _ = _fixture_rows_with_evidence({"response": rows}, capabilities, clock)
    for value in accepted:
        if value["fixture_id"] in tracked:
            seed = dict(value, market="UNDER_2_5", candidate_id="synthetic-early-" + str(value["fixture_id"]),
                        kickoff_utc=value["kickoff_utc"].isoformat(), league=value["league_name"])
            repo.save_tracked_review(new_review(seed, clock-timedelta(minutes=30)),
                                     now=clock-timedelta(minutes=30))
    client = QueueClient(rows, clock=clock, failures=failures)
    try:
        report = asyncio.run(LabV2ShadowRunner(client, repo, maximum_calls=maximum,
            capability_cache_path=tmp_path / "var/caps.json").run(now=clock, horizon_days=1))
        assert report["telegram_sends"] == report["official_mutations"] == 0
        assert report["api_calls_consumed"] <= maximum
        assert repo.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        return report, client
    finally:
        repo.close()


def exact_ids(client):
    return [query["id"] for endpoint, query in client.requests
            if endpoint == "/fixtures" and "id" in query]


def test_tracked_lower_league_gets_review_before_new_priority_backlog(tmp_path, monkeypatch):
    rows = [row(i, priority=True) for i in range(1, 7)] + [row(99, minutes=30)]
    report, client = cycle(tmp_path, monkeypatch, rows, tracked=(99,))
    assert exact_ids(client)[0] == 99
    assert 99 in report["tracked_final_review_shortlist"]
    assert client.requests.count(("/odds", {"fixture": 99})) == 1


def test_second_batch_uses_unreviewed_fixtures_not_first_batch_slots(tmp_path, monkeypatch):
    rows = [row(i, priority=True) for i in range(1, 6)] + [row(i) for i in range(6, 11)]
    report, client = cycle(tmp_path, monkeypatch, rows)
    assert set(exact_ids(client)) == set(range(1, 11))
    assert len(exact_ids(client)) == 10
    assert len(report["final_review_queue"]["attempted_fixture_ids"]) == 10


def test_2300_cutoff_fixtures_cannot_displace_2230_pending_match(tmp_path, monkeypatch):
    clock = datetime(2026, 10, 4, 19, tzinfo=timezone.utc)  # 22:00 Riga
    rows = [row(i, minutes=60, priority=True, now=clock) for i in range(1, 6)]
    rows.append(row(99, minutes=30, now=clock))
    report, client = cycle(tmp_path, monkeypatch, rows, clock=clock, tracked=(99,))
    assert exact_ids(client) == [99]
    assert report["final_review_queue"]["due_fixture_ids"] == [99]


def test_failed_exact_review_is_not_retried_within_same_cycle(tmp_path, monkeypatch):
    rows = [row(i, priority=True) for i in range(1, 6)] + [row(i) for i in range(6, 11)]
    report, client = cycle(tmp_path, monkeypatch, rows, tracked=(1,), failures=(1,))
    assert exact_ids(client).count(1) == 1
    assert client.requests.count(("/odds", {"fixture": 1})) == 1
    assert set(exact_ids(client)) == set(range(1, 11))
    tracked = next(r for r in report["tracked_final_reviews"] if r["fixture_id"] == 1)
    assert tracked["state"] == "CURRENT_ODDS_UNAVAILABLE"


def test_low_budget_reports_pending_without_claiming_exact_review(tmp_path, monkeypatch):
    report, client = cycle(tmp_path, monkeypatch, [row(99)], tracked=(99,), maximum=3)
    assert exact_ids(client) == []
    assert report["near_kickoff_cycle_result"] == "EXACT_REVIEW_BUDGET_PENDING"
    assert report["final_review_queue"]["pending_fixture_ids"] == [99]
    assert {r["state"] for r in report["tracked_final_reviews"]} == {"FINAL_REVIEW_REQUIRED"}

@pytest.mark.parametrize("minutes,allowed", [(-1, False), (0, False), (10, False),
    (11, True), (75, True), (76, False)])
def test_queue_preserves_final_review_time_boundaries(tmp_path, minutes, allowed):
    from app.lab_v2_shadow.runner import _final_review_queue
    repo = ShadowEvidenceRepository(tmp_path / "boundary.db")
    fixture_value = dict(fixture_id=7, league_id=999, country="Testland",
        competition_profile="UNKNOWN", kickoff_utc=NOW+timedelta(minutes=minutes))
    try:
        result = _final_review_queue([fixture_value], repo, now=NOW, tracked_ids={7})
        assert bool(result) == allowed
        assert not repo.all("enrichment_service")
    finally:
        repo.close()


def test_last_attempt_survives_restart_and_prevents_tie_starvation(tmp_path):
    from app.lab_v2_shadow.runner import _final_review_queue
    from app.lab_v2_shadow.scheduling import record_service
    path = tmp_path / "rotation.db"
    fixtures = [dict(fixture_id=i, league_id=999, country="Testland",
        competition_profile="UNKNOWN", kickoff_utc=NOW+timedelta(minutes=60)) for i in range(1, 8)]
    repo = ShadowEvidenceRepository(path)
    for item in fixtures[:5]:
        record_service(repo, item, NOW, "review")
    repo.close()
    repo = ShadowEvidenceRepository(path)
    try:
        queued = _final_review_queue(list(reversed(fixtures)), repo, now=NOW+timedelta(minutes=30),
                                      tracked_ids=set(range(1, 8)))
        assert [v["fixture_id"] for v in queued[:2]] == [6, 7]
        assert [v["fixture_id"] for v in _final_review_queue(fixtures, repo,
            now=NOW+timedelta(minutes=30), tracked_ids=set(range(1, 8)))] == [v["fixture_id"] for v in queued]
        assert _final_review_queue(fixtures, repo, now=NOW, attempted_ids=frozenset(range(1, 8))) == []
    finally:
        repo.close()


def test_queue_is_bounded_and_capacity_pending_is_explicit(tmp_path, monkeypatch):
    rows = [row(i, priority=i<=5) for i in range(1, 16)]
    report, client = cycle(tmp_path, monkeypatch, rows, tracked=range(1, 16))
    assert len(exact_ids(client)) == len(set(exact_ids(client))) == 10
    assert len(report["final_review_queue"]["pending_fixture_ids"]) == 5
    pending = set(report["final_review_queue"]["pending_fixture_ids"])
    for value in report["tracked_final_reviews"]:
        if value["fixture_id"] in pending:
            assert value["reasons"] == ["FINAL_REVIEW_QUEUE_CAPACITY_PENDING"]


def test_nonprematch_fixture_never_enters_queue(tmp_path):
    from app.lab_v2_shadow.runner import _final_review_queue
    repo = ShadowEvidenceRepository(tmp_path / "invalid.db")
    value = dict(fixture_id=7, kickoff_utc=NOW+timedelta(minutes=45), prematch_eligible=False)
    try:
        assert _final_review_queue([value], repo, now=NOW, tracked_ids={7}) == []
    finally:
        repo.close()


def test_optional_early_context_is_retained_without_exact_review(tmp_path, monkeypatch):
    from test_lab_v2_shadow import coverage
    monkeypatch.chdir(tmp_path)
    rows = [row(7, minutes=180)]
    rows[0]["league"]["id"] = 999
    class EarlyContext(QueueClient):
        async def leagues(self, *, current=True):
            return self._hit("/leagues", {}, {"response": [coverage(full=True)]})
    repo = ShadowEvidenceRepository(tmp_path / "early.db")
    client = EarlyContext(rows)
    try:
        report = asyncio.run(LabV2ShadowRunner(client, repo, maximum_calls=100,
            capability_cache_path=tmp_path / "var/caps.json").run(now=NOW, horizon_days=1))
        assert exact_ids(client) == []
        assert ("/injuries", {"fixture": 7}) in client.requests
        assert report["cmi_enrichment_count"] == 1
        assert report["final_review_queue"]["attempted_fixture_ids"] == []
    finally:
        repo.close()
