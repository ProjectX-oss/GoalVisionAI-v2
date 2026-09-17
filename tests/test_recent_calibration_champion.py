from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from app.calibration_freshness import DEFAULT_CALIBRATION_FRESHNESS_POLICY
from app.recent_calibration_champion import (
    ChampionFreshnessError,
    calibration_freshness_status,
)
from app.staging_real_artifact_chain import (
    DEFAULT_REAL_ARTIFACT_CHAIN_PROFILE,
    recent_calibration_rehearsal_profile,
)
from app.real_match_lab_analysis.cli import _human_print


UTC = timezone.utc
NOW = datetime(2026, 7, 31, 12, tzinfo=UTC)


class RecentCalibrationChronologyTests(unittest.TestCase):
    def test_default_chain_chronology_is_unchanged(self):
        profile = DEFAULT_REAL_ARTIFACT_CHAIN_PROFILE
        self.assertEqual(profile.source_match_count, 1200)
        self.assertEqual(profile.match_interval, timedelta(days=1))
        self.assertEqual(profile.champion_validation_test_gap_days, 660)

    def test_recent_profile_has_completed_sources_and_isolation(self):
        profile = recent_calibration_rehearsal_profile(NOW)
        self.assertEqual(profile.source_match_count, 1200)
        self.assertLess(profile.kickoff(profile.source_match_count - 1), profile.import_at)
        self.assertLess(profile.import_at, profile.build_at)
        self.assertLess(profile.build_at, profile.split_at)
        self.assertLess(profile.split_at, profile.train_at)
        self.assertLess(profile.train_at, profile.calibrate_at)
        self.assertLess(profile.calibrate_at, profile.backtest_at)
        self.assertLess(profile.backtest_at, profile.compare_at)
        self.assertLess(profile.compare_at, profile.evidence_cutoff)
        self.assertEqual(profile.challenger_train_end_index, 700)
        self.assertEqual(profile.challenger_validation_end_index, 900)

    def test_recent_profile_requires_explicit_aware_clock(self):
        with self.assertRaises(ValueError):
            recent_calibration_rehearsal_profile(datetime(2026, 7, 31, 12))

    def test_freshness_uses_calibration_reference_timestamp(self):
        age, maximum, status = calibration_freshness_status(
            NOW - timedelta(minutes=5), NOW
        )
        self.assertEqual((age, status), (300, "FRESH"))
        self.assertEqual(
            maximum,
            DEFAULT_CALIBRATION_FRESHNESS_POLICY.lab_evidence_max_age_seconds,
        )

    def test_old_calibration_remains_stale(self):
        with self.assertRaisesRegex(ChampionFreshnessError, "not fresh"):
            calibration_freshness_status(
                NOW - timedelta(
                    seconds=(
                        DEFAULT_CALIBRATION_FRESHNESS_POLICY.lab_evidence_max_age_seconds
                        + 1
                    )
                ),
                NOW,
            )

    def test_future_timestamp_rewriting_fails_closed(self):
        with self.assertRaisesRegex(ChampionFreshnessError, "not fresh"):
            calibration_freshness_status(NOW + timedelta(seconds=1), NOW)

    def test_profile_is_immutable(self):
        profile = recent_calibration_rehearsal_profile(NOW)
        with self.assertRaises(Exception):
            profile.calibrate_at = NOW
        self.assertNotEqual(
            replace(profile, calibrate_at=NOW).calibrate_at,
            profile.calibrate_at,
        )

    def test_nested_human_inspection_is_terminal_safe(self):
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with patch("sys.stdout", stream):
            _human_print({"preview": "🧪 ⭐"})
            stream.flush()
            stream.buffer.seek(0)
            rendered = stream.buffer.read().decode("cp1252")
        self.assertIn(r"\U0001f9ea", rendered)

    def test_canonical_evidence_fingerprint_and_safety_claims(self):
        path = Path("docs/rehearsals/live_78_recent_calibration_champion_2026-07-31.json")
        evidence = json.loads(path.read_text(encoding="utf-8"))
        expected = evidence["evidence_fingerprint"]
        evidence["evidence_fingerprint"] = ""
        actual = hashlib.sha256(
            json.dumps(
                evidence, sort_keys=True, separators=(",", ":"), default=str
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(actual, expected)
        self.assertEqual(evidence["real_match_lab_rehearsal"]["market_count"], 11)
        self.assertEqual(evidence["safety"]["telegram_api_calls"], 0)
        self.assertEqual(evidence["safety"]["delivery_records"], 0)


if __name__ == "__main__":
    unittest.main()
