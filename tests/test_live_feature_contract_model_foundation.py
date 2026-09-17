import hashlib
import json
import unittest
from decimal import Decimal
from pathlib import Path

from app.feature_store import FEATURE_DEFINITIONS
from app.historical_data_import import NormalizedHistoricalStatistics
from app.historical_model_training import (
    FEATURE_NAMES,
    LIVE_TRAINING_FEATURE_CONTRACT,
    resolve_training_feature_contract,
)
from app.historical_training_dataset import (
    HistoricalSourceMatch,
    LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY,
    live_feature_coverage,
    project_live_features,
)
from app.historical_training_dataset import TemporalLeakageError
from app.model_input_builder import (
    GOALVISION_MODEL_INPUT_V1,
    LIVE_MODEL_INPUT_CONTRACT,
)


def source(index, home="alpha", away="bravo", kickoff=None):
    kickoff = kickoff or f"2025-01-{index + 1:02d}T12:00:00Z"
    stats = NormalizedHistoricalStatistics(
        possession=Decimal("50"), shots=10, shots_on_target=4,
        expected_goals=Decimal("1.2"), corners=5, yellow_cards=1,
        red_cards=0, fouls=8, offsides=1,
    )
    return HistoricalSourceMatch(
        historical_match_id=f"history-{index}",
        import_ids=("import-1",),
        match_fingerprint=hashlib.sha256(f"history-{index}".encode()).hexdigest(),
        competition="League",
        competition_identity="league",
        season="2024/25",
        kickoff_utc=kickoff,
        home_team_identity=home,
        away_team_identity=away,
        full_time_home_score=index % 4,
        full_time_away_score=(index + 1) % 3,
        home_statistics=stats,
        away_statistics=stats,
    )


class LiveFeatureContractFoundationTests(unittest.TestCase):
    def setUp(self):
        self.prior = tuple(
            source(index, "alpha", "bravo" if index % 2 else "charlie")
            for index in range(8)
        )
        self.target = source(
            20, "alpha", "bravo", "2025-02-01T12:00:00Z"
        )

    def test_live_schema_is_single_authority(self):
        self.assertEqual(
            LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names,
            GOALVISION_MODEL_INPUT_V1.ordered_feature_names,
        )
        self.assertEqual(
            LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names,
            tuple(item.name for item in FEATURE_DEFINITIONS),
        )

    def test_exact_live_contract_identity_count_and_fingerprint(self):
        self.assertEqual(LIVE_MODEL_INPUT_CONTRACT.schema_identifier,
                         "goalvision_model_input_v1")
        self.assertEqual(LIVE_MODEL_INPUT_CONTRACT.schema_version, "v1")
        self.assertEqual(LIVE_MODEL_INPUT_CONTRACT.feature_count, 78)
        self.assertRegex(LIVE_MODEL_INPUT_CONTRACT.schema_fingerprint,
                         r"^[0-9a-f]{64}$")

    def test_training_contract_is_the_live_contract(self):
        self.assertEqual(
            LIVE_TRAINING_FEATURE_CONTRACT.ordered_feature_names,
            LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names,
        )
        self.assertEqual(
            LIVE_TRAINING_FEATURE_CONTRACT.schema_fingerprint,
            LIVE_MODEL_INPUT_CONTRACT.schema_fingerprint,
        )

    def test_legacy_contract_remains_distinct(self):
        self.assertEqual(len(FEATURE_NAMES), 145)
        self.assertNotEqual(
            FEATURE_NAMES, LIVE_TRAINING_FEATURE_CONTRACT.ordered_feature_names
        )

    def test_historical_projection_is_exact_and_deterministic(self):
        first = project_live_features(
            self.target, self.prior,
            LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY,
        )
        second = project_live_features(
            self.target, self.prior,
            LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY,
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first.values), 78)
        self.assertEqual(len(first.missingness_mask), 78)

    def test_required_baselines_are_present(self):
        projected = project_live_features(
            self.target, self.prior,
            LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY,
        )
        for name in LIVE_MODEL_INPUT_CONTRACT.required_feature_names:
            index = LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names.index(name)
            self.assertFalse(projected.missingness_mask[index], name)

    def test_optional_unavailable_inputs_stay_missing(self):
        projected = project_live_features(
            self.target, self.prior,
            LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY,
        )
        index = LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names.index(
            "home_injuries_count"
        )
        self.assertIsNone(projected.values[index])
        self.assertTrue(projected.missingness_mask[index])

    def test_missing_required_baseline_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Required live feature"):
            project_live_features(
                self.target, (),
                LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY,
            )

    def test_future_source_is_rejected(self):
        future = source(
            30, "alpha", "bravo", "2025-03-01T12:00:00Z"
        )
        with self.assertRaises(TemporalLeakageError):
            project_live_features(
                self.target, (*self.prior, future),
                LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY,
            )

    def test_same_kickoff_source_is_rejected(self):
        same = source(
            31, "alpha", "bravo", self.target.kickoff_utc
        )
        with self.assertRaises(TemporalLeakageError):
            project_live_features(
                self.target, (*self.prior, same),
                LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY,
            )

    def test_coverage_is_complete_ordered_and_honest(self):
        coverage = live_feature_coverage()
        self.assertEqual(
            tuple(item.feature_name for item in coverage),
            LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names,
        )
        self.assertEqual(len(coverage), 78)
        self.assertIn(
            "OPTIONAL_LEGITIMATELY_MISSING",
            {item.classification for item in coverage},
        )
        self.assertNotIn(
            "UNAVAILABLE_AND_BLOCKING",
            {item.classification for item in coverage},
        )

    def test_wrong_count_order_version_and_fingerprint_reject(self):
        contract = LIVE_TRAINING_FEATURE_CONTRACT
        invalid = (
            (contract.schema_version, contract.schema_fingerprint,
             contract.ordered_feature_names[:-1]),
            (contract.schema_version, contract.schema_fingerprint,
             tuple(reversed(contract.ordered_feature_names))),
            ("v2", contract.schema_fingerprint, contract.ordered_feature_names),
            (contract.schema_version, "0" * 64, contract.ordered_feature_names),
        )
        for declaration in invalid:
            with self.subTest(declaration=declaration[0:2]), self.assertRaises(ValueError):
                resolve_training_feature_contract(*declaration)

    def test_committed_rehearsal_evidence_fingerprint(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "rehearsals"
            / "live_78_feature_champion_rehearsal_2026-07-30.json"
        )
        evidence = json.loads(path.read_text(encoding="utf-8"))
        claimed = evidence.pop("evidence_fingerprint")
        encoded = json.dumps(
            evidence,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        self.assertEqual(claimed, hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    unittest.main()
