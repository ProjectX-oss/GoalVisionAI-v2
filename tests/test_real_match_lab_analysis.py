import asyncio
import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from telegram.error import BadRequest

from app.database import Database
from app.database.migrations import MIGRATIONS
from app.real_match_lab_analysis import (
    AnalysisConflictError,
    AnalysisStatus,
    DeliveryConflictError,
    DeliveryStatus,
    EngineEvidence,
    INPUT_SCHEMA_VERSION,
    LAB_BOT_USERNAME,
    LAB_CHAT_ID,
    LabSelectionPolicy,
    MarketEvaluation,
    SEND_CONFIRMATION,
    SQLiteRealMatchLabRepository,
    parse_input,
)
from app.real_match_lab_analysis.input import InputValidationError
from app.real_match_lab_analysis.cli import _json_text, _print_value
from app.real_match_lab_analysis.message import build_message
from app.real_match_lab_analysis.service import RealMatchLabAnalysisService
from app.real_match_lab_analysis.repository import analysis_send_eligible
from app.services.telegram_service import TelegramMessageReceipt


UTC = timezone.utc
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
FIXTURE = Path("tests/fixtures/real_match_lab/valid.json")


def raw_input():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def evaluation(market="HOME_WIN", probability="0.642", odds="1.78", ev="0.142"):
    price = Decimal(odds)
    probability = Decimal(probability)
    return MarketEvaluation(
        market, Decimal("0.63"), probability, Decimal("1.557632"), price,
        (Decimal(1) / price).quantize(Decimal("0.000001")),
        Decimal("0.080202"), Decimal(ev), "⭐⭐⭐⭐", "FRESH", False,
        price >= Decimal("1.60"), True, (), f"{market.lower()}-odds-fp",
        f"assessment-{market.lower()}",
    )


class FakeEngine:
    def __init__(self, reject=None, values=None):
        self.calls = 0
        self.reject = reject
        self.values = values or (
            evaluation(),
            evaluation("OVER_2_5", "0.58", "1.95", "0.131"),
        )

    def analyze(self, command, now):
        self.calls += 1
        if self.reject:
            from app.real_match_lab_analysis.engine import EngineRejected
            raise EngineRejected(self.reject, "rejected")
        values, _ = LabSelectionPolicy().select(self.values)
        return EngineEvidence(
            "snapshot-1", "features-1", "a" * 64, "input-1", "b" * 64,
            "model-1", "c" * 64, "calibration-1", "d" * 64,
            "inference-1", "e" * 64, "assembly-1", values, 120,
            "PARTIAL_OR_PROBABLE",
            ("Arsenal has the stronger supplied recent points rate",
             "lineup information is partial"),
            calibration_quality_report={
                "lab_outcome": "CALIBRATION_QUALITY_ACCEPTABLE",
                "send_eligible": True,
                "reason_codes": [],
            },
            send_eligible=True,
        )


class RecordingTransport:
    def __init__(self, error=None, receipt=None):
        self.calls = []
        self.error = error
        self.receipt = receipt or TelegramMessageReceipt(42, LAB_CHAT_ID)

    async def send_message_receipt(self, chat_id, text, parse_mode=None, *, timeout_seconds):
        self.calls.append((chat_id, text, parse_mode, timeout_seconds))
        if self.error:
            raise self.error
        return self.receipt


class RealMatchLabInputTests(unittest.TestCase):
    def test_json_cli_output_is_ascii_safe_and_round_trips_unicode(self):
        value = {"confidence": "⭐⭐⭐⭐", "status": "NO_SELECTION"}
        rendered = _json_text(value)
        self.assertTrue(rendered.isascii())
        self.assertEqual(json.loads(rendered), value)

    def test_human_structured_cli_output_is_ascii_safe(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            _print_value([{"confidence": "⭐⭐"}], "human")
        self.assertTrue(output.getvalue().isascii())

    def test_valid_real_match_input_validation(self):
        value = parse_input(raw_input(), now=NOW)
        self.assertEqual(value.schema_version, INPUT_SCHEMA_VERSION)
        self.assertEqual(value.match_id, "real-fixture-2099-01")
        self.assertEqual(len(value.odds), 2)

    def test_missing_data_rejection(self):
        raw = raw_input()
        del raw["data"]["home_recent_form"]
        with self.assertRaises(InputValidationError):
            parse_input(raw, now=NOW)

    def test_post_kickoff_rejection(self):
        raw = raw_input()
        raw["kickoff_utc"] = "2026-07-30T11:00:00Z"
        with self.assertRaises(InputValidationError):
            parse_input(raw, now=NOW)

    def test_post_kickoff_odds_rejection(self):
        raw = raw_input()
        raw["odds"][0]["captured_at"] = raw["kickoff_utc"]
        with self.assertRaises(InputValidationError):
            parse_input(raw, now=NOW)

    def test_future_input_timestamp_rejection(self):
        raw = raw_input()
        raw["collected_at"] = "2026-07-30T12:00:01Z"
        with self.assertRaises(InputValidationError):
            parse_input(raw, now=NOW)

    def test_wrong_environment_rejection(self):
        raw = raw_input()
        raw["environment"] = "PRODUCTION"
        with self.assertRaises(InputValidationError):
            parse_input(raw, now=NOW)

    def test_wrong_scope_rejection(self):
        raw = raw_input()
        raw["scope"] = "HIGH_RISK"
        with self.assertRaises(InputValidationError):
            parse_input(raw, now=NOW)

    def test_unsupported_market_and_correct_score_rejection(self):
        for market in ("COMBO", "CORRECT_SCORE"):
            raw = raw_input()
            raw["odds"][0]["market"] = market
            with self.subTest(market=market), self.assertRaises(InputValidationError):
                parse_input(raw, now=NOW)

    def test_equal_team_rejection(self):
        raw = raw_input()
        raw["away_team"] = raw["home_team"]
        with self.assertRaises(InputValidationError):
            parse_input(raw, now=NOW)


class LabPolicyAndMessageTests(unittest.TestCase):
    def test_deterministic_lab_market_selection(self):
        policy = LabSelectionPolicy()
        first = policy.select((evaluation(), evaluation("OVER_2_5", "0.64", "1.90", "0.20")))
        second = policy.select((evaluation(), evaluation("OVER_2_5", "0.64", "1.90", "0.20")))
        self.assertEqual(first, second)
        self.assertEqual(first[1].market, "HOME_WIN")
        self.assertEqual(sum(item.selected for item in first[0]), 1)

    def test_non_positive_ev_produces_no_selection(self):
        values, selected = LabSelectionPolicy().select(
            (evaluation(ev="0"), evaluation("OVER_2_5", ev="-0.1"),)
        )
        self.assertIsNone(selected)
        self.assertTrue(all(not item.selected for item in values))

    def test_no_combo_or_correct_score_output(self):
        value = parse_input(raw_input(), now=NOW)
        evidence = FakeEngine().analyze(value, NOW)
        selected = next(item for item in evidence.evaluations if item.selected)
        message, _ = build_message(value, evidence, selected)
        self.assertNotIn("COMBO", message)
        self.assertNotIn("correct score", message.lower())

    def test_no_stake_percentage_or_betting_instruction(self):
        value = parse_input(raw_input(), now=NOW)
        evidence = FakeEngine().analyze(value, NOW)
        message, _ = build_message(
            value, evidence, next(item for item in evidence.evaluations if item.selected)
        )
        self.assertNotIn("stake", message.lower())
        self.assertNotIn("you should bet", message.lower())

    def test_html_escaping_and_reasoning_traceability(self):
        raw = raw_input()
        raw["home_team"] = "<Arsenal & Co>"
        value = parse_input(raw, now=NOW)
        evidence = FakeEngine().analyze(value, NOW)
        message, fingerprint = build_message(
            value, evidence, next(item for item in evidence.evaluations if item.selected)
        )
        self.assertIn("&lt;Arsenal &amp; Co&gt;", message)
        self.assertNotIn("<Arsenal & Co>", message)
        self.assertIn(evidence.reasoning_facts[0], message)
        self.assertIn(fingerprint, message)


class AnalysisPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.repository = SQLiteRealMatchLabRepository(self.database)
        self.engine = FakeEngine()
        self.service = RealMatchLabAnalysisService(self.repository, self.engine)
        self.command = parse_input(raw_input(), now=NOW)

    def tearDown(self):
        self.database.close()

    def test_deterministic_analysis_result_and_human_preview_data(self):
        first = self.service.analyze(self.command)
        second = self.service.analyze(self.command)
        self.assertEqual(first.result_fingerprint, second.result_fingerprint)
        self.assertEqual(first.status, AnalysisStatus.COMPLETED)
        self.assertIn("Experimental AI prediction", first.message_html)
        self.assertEqual(first.destination_chat_id, LAB_CHAT_ID)

    def test_exact_replay_idempotency(self):
        self.service.analyze(self.command)
        self.service.analyze(self.command)
        count = self.database.connection.execute(
            "SELECT COUNT(*) FROM real_match_lab_analyses"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_conflicting_replay_rejection_before_engine(self):
        self.service.analyze(self.command)
        changed = raw_input()
        changed["operator_notes"] = "changed"
        command = parse_input(changed, now=NOW)
        calls = self.engine.calls
        with self.assertRaises(AnalysisConflictError):
            self.service.analyze(command)
        self.assertEqual(self.engine.calls, calls)

    def test_rejected_pipeline_persists_reason(self):
        service = RealMatchLabAnalysisService(self.repository, FakeEngine("MODEL_INPUT_SCHEMA_INCOMPATIBLE"))
        record = service.analyze(self.command)
        self.assertEqual(record.status, AnalysisStatus.REJECTED)
        self.assertEqual(record.rejection_reasons, ("MODEL_INPUT_SCHEMA_INCOMPATIBLE",))
        self.assertIsNone(record.message_html)

    def test_dry_run_produces_zero_telegram_sends(self):
        transport = RecordingTransport()
        self.service.analyze(self.command)
        self.assertEqual(transport.calls, [])
        self.assertEqual(len(self.repository.delivery_history(
            self.service.analyze(self.command).analysis_id
        )), 0)

    def test_append_only_update_and_delete_rejection(self):
        record = self.service.analyze(self.command)
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "UPDATE real_match_lab_analyses SET status='REJECTED' WHERE analysis_id=?",
                (record.analysis_id,),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "DELETE FROM real_match_lab_analyses WHERE analysis_id=?",
                (record.analysis_id,),
            )

    def test_foreign_key_integrity(self):
        self.assertEqual(
            self.database.connection.execute("PRAGMA foreign_key_check").fetchall(), []
        )

    def test_zero_official_or_activation_mutations(self):
        before = {
            table: self.database.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "official_prediction_publication_events",
                "bankroll_transactions",
                "model_champion_generations",
            )
        }
        self.service.analyze(self.command)
        after = {
            table: self.database.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
        self.assertEqual(before, after)

    def test_latest_migration_is_37(self):
        self.assertEqual(MIGRATIONS[-1].version, 41)

    def test_legacy_analysis_without_quality_report_is_not_send_eligible(self):
        row = {"result_snapshot": json.dumps({"evidence": {}})}
        self.assertFalse(analysis_send_eligible(row))

    def test_controlled_synthetic_quality_is_not_send_eligible(self):
        row = {"result_snapshot": json.dumps({"evidence": {
            "send_eligible": False,
            "calibration_quality_report": {
                "lab_outcome": "CALIBRATION_QUALITY_REVIEW_REQUIRED",
                "send_eligible": False,
            },
        }})}
        self.assertFalse(analysis_send_eligible(row))


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.repository = SQLiteRealMatchLabRepository(self.database)
        self.service = RealMatchLabAnalysisService(self.repository, FakeEngine())
        self.record = self.service.analyze(parse_input(raw_input(), now=NOW))

    def tearDown(self):
        self.database.close()

    def send(self, transport=None, **overrides):
        values = dict(
            token="secret-never-print", configured_chat_id=LAB_CHAT_ID,
            configured_bot=LAB_BOT_USERNAME,
            transport=transport or RecordingTransport(), occurred_at=NOW,
        )
        values.update(overrides)
        return asyncio.run(self.service.send(
            self.record.analysis_id, SEND_CONFIRMATION, **values
        ))

    def test_successful_explicit_fake_transport_send(self):
        transport = RecordingTransport()
        outcome = self.send(transport)
        self.assertEqual(outcome.status, DeliveryStatus.SENT)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0][0], LAB_CHAT_ID)
        self.assertEqual(transport.calls[0][2:], ("HTML", 10.0))

    def test_successful_send_replay_does_not_resend(self):
        transport = RecordingTransport()
        self.send(transport)
        with self.assertRaises(DeliveryConflictError):
            self.send(transport)
        self.assertEqual(len(transport.calls), 1)

    def test_wrong_confirmation_destination_and_bot_rejected_without_send(self):
        cases = (
            ("confirmation", "send_to_goalvision_ai_lab"),
            ("configured_chat_id", "-1000000000000"),
            ("configured_bot", "@OtherBot"),
        )
        for key, value in cases:
            transport = RecordingTransport()
            kwargs = {key: value}
            with self.subTest(key=key), self.assertRaises(DeliveryConflictError):
                if key == "confirmation":
                    asyncio.run(self.service.send(
                        self.record.analysis_id, value, token="secret",
                        configured_chat_id=LAB_CHAT_ID,
                        configured_bot=LAB_BOT_USERNAME, transport=transport,
                    ))
                else:
                    self.send(transport, **kwargs)
            self.assertEqual(transport.calls, [])

    def test_confirmed_telegram_failure_can_retry(self):
        failed = self.send(RecordingTransport(error=BadRequest("no delivery")))
        self.assertEqual(failed.status, DeliveryStatus.FAILED)
        successful = self.send(RecordingTransport(), occurred_at=NOW + timedelta(seconds=1))
        self.assertEqual(successful.status, DeliveryStatus.SENT)
        self.assertEqual(successful.attempt_number, 2)

    def test_uncertain_delivery_never_automatically_duplicates(self):
        uncertain = self.send(RecordingTransport(error=RuntimeError("unknown")))
        self.assertEqual(uncertain.status, DeliveryStatus.INDETERMINATE)
        transport = RecordingTransport()
        with self.assertRaises(DeliveryConflictError):
            self.send(transport)
        self.assertEqual(transport.calls, [])

    def test_wrong_receipt_is_indeterminate(self):
        outcome = self.send(RecordingTransport(
            receipt=TelegramMessageReceipt(42, "-1000000000000")
        ))
        self.assertEqual(outcome.status, DeliveryStatus.INDETERMINATE)


if __name__ == "__main__":
    unittest.main()
