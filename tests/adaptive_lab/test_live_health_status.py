"""LIVE monitoring must describe observed timer state, never change execution."""
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import subprocess

import pytest
from app.adaptive_lab import health

NOW = datetime(2026, 10, 7, 21, 0, tzinfo=ZoneInfo("Europe/Riga"))


@pytest.mark.parametrize("timer,expected", [
    ({"LoadState": "loaded", "ActiveState": "active"}, "ACTIVE"),
    ({"LoadState": "loaded", "ActiveState": "inactive"}, "INACTIVE"),
    ({"LoadState": "loaded", "ActiveState": "failed"}, "FAILED"),
    ({"LoadState": "loaded", "ActiveState": "activating"}, "UNKNOWN"),
    ({"LoadState": "not-found", "ActiveState": "inactive"}, "NOT_INSTALLED"),
    ({"status": "SYSTEMD_UNAVAILABLE"}, "UNKNOWN"),
    ({}, "UNKNOWN"),
])
def test_observed_timer_state_is_not_hardcoded(monkeypatch, timer, expected):
    calls = []
    def read(unit):
        calls.append(unit)
        return timer
    monkeypatch.setattr(health, "timer_state", read)
    result = health.live_runtime_status(now=NOW)
    assert result["LIVE"] == expected
    assert result["LIVE_SCOPE"] == "LAB_EVENING_TIMER"
    assert calls == ["goalvision-lab-live-evening.timer"]
    assert result["LIVE_TIMER"]["unit"] == calls[0]


@pytest.mark.parametrize("day", ["2026-01-07", "2026-07-07", "2026-10-07"])
@pytest.mark.parametrize("clock,inside", [
    ("17:59:59", False), ("18:00:00", True),
    ("22:59:59", True), ("23:00:00", False),
])
def test_riga_discovery_boundary_does_not_disable_result_timer(monkeypatch, day, clock, inside):
    monkeypatch.setattr(health, "timer_state",
                        lambda _: {"LoadState": "loaded", "ActiveState": "active"})
    now = datetime.fromisoformat(day + "T" + clock).replace(tzinfo=ZoneInfo("Europe/Riga"))
    result = health.live_runtime_status(now=now)
    assert result["LIVE"] == "ACTIVE"
    assert result["LIVE_DISCOVERY_WINDOW"]["contains_observed_time"] is inside
    assert result["LIVE_RESULTS_WINDOW"] == "24H_WHILE_TIMER_ACTIVE"


@pytest.mark.parametrize("failure", ["nonzero", "empty", "timeout", "oserror"])
def test_systemd_failure_is_unknown_and_stderr_is_not_exposed(monkeypatch, failure):
    def run(command, **kwargs):
        assert command[:2] == ["systemctl", "show"]
        assert kwargs["timeout"] == 5
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 5)
        if failure == "oserror":
            raise OSError("private diagnostic")
        return SimpleNamespace(returncode=1 if failure == "nonzero" else 0,
                               stdout="ActiveState=active\n" if failure == "nonzero" else "",
                               stderr="private diagnostic")
    monkeypatch.setattr(health.subprocess, "run", run)
    result = health.live_runtime_status(now=NOW)
    assert result["LIVE"] == "UNKNOWN"
    assert "private diagnostic" not in str(result)


def test_timer_probe_is_read_only_and_parses_load_state(monkeypatch):
    def run(command, **kwargs):
        assert command[:3] == ["systemctl", "show", "goalvision-lab-live-evening.timer"]
        assert "LoadState" in command[3]
        return SimpleNamespace(returncode=0, stdout="LoadState=loaded\nActiveState=active\n",
                               stderr="")
    monkeypatch.setattr(health.subprocess, "run", run)
    assert health.live_runtime_status(now=NOW)["LIVE"] == "ACTIVE"


def test_historical_prematch_projection_never_probes_current_live_timer(monkeypatch):
    monkeypatch.setattr(health, "timer_state", lambda _: pytest.fail("historical systemd probe"))
    monkeypatch.setenv("GOALVISION_LAB_EVENING_MODE", "1")
    report = health.cycle_health({}, started=NOW, completed=NOW)
    assert report["LIVE"] == "NOT_EVALUATED"
    assert report["LIVE_SCOPE"] == "PREMATCH_CYCLE"
