import asyncio
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.bankroll import (
    DEFAULT_OFFICIAL_BANKROLL_CONFIG,
    BankrollProduct,
    BankrollTransaction,
    StakeTier,
)
from app.database import (
    Database,
    SQLiteOfficialBankrollRepository,
    SQLitePredictionResultRepository,
    SQLiteResultPublicationRepository,
)
from app.presentation import DEFAULT_PRESENTATION_CONFIG, TelegramPredictionPresenter
from app.result_publication import (
    InMemoryResultPresentationMetadataProvider,
    OfficialResultPublicationService,
    ResultPresentationMetadata,
    ResultPublicationFailureReason,
    ResultPublicationStatus,
)
from app.results import (
    PublishedPredictionReference,
    ResolvedPredictionResult,
    ResolutionStatus,
    SettlementReasonCode,
)


NOW = datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc)
DESTINATION = "@goalvision_official"


class FakeTelegram:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[tuple[str, str, str | None]] = []

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str | None = None,
    ) -> int | None:
        self.calls.append((chat_id, text, parse_mode))
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("Telegram unavailable")
        return 700 + len(self.calls)


class HistoryOverrideRepository:
    def __init__(self, repository: SQLitePredictionResultRepository, history) -> None:
        self._repository = repository
        self._history = tuple(history)

    def load_history(self):
        return self._history

    def get_published(self, prediction_id):
        return self._repository.get_published(prediction_id)


class FailingPublicationRepository:
    def get(self, prediction_id, product_id, destination):
        raise ValueError("database unavailable")

    def begin_attempt(self, *args, **kwargs):
        raise ValueError("database unavailable")

    def mark_published(self, *args, **kwargs):
        raise ValueError("database unavailable")

    def mark_failed(self, *args, **kwargs):
        raise ValueError("database unavailable")


class FailingPublishedWriteRepository:
    def __init__(self, repository: SQLiteResultPublicationRepository) -> None:
        self._repository = repository

    def get(self, prediction_id, product_id, destination):
        return self._repository.get(prediction_id, product_id, destination)

    def begin_attempt(self, *args, **kwargs):
        return self._repository.begin_attempt(*args, **kwargs)

    def mark_published(self, *args, **kwargs):
        raise ValueError("published state unavailable")

    def mark_failed(self, *args, **kwargs):
        return self._repository.mark_failed(*args, **kwargs)


class OfficialResultPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(__file__).with_name(f"publication-{uuid4().hex}.db")
        self.database = Database(self.path)
        self.results = SQLitePredictionResultRepository(self.database)
        self.bankroll = SQLiteOfficialBankrollRepository(
            self.database,
            DEFAULT_OFFICIAL_BANKROLL_CONFIG,
            clock=lambda: NOW,
        )
        self.publications = SQLiteResultPublicationRepository(self.database)
        self.telegram = FakeTelegram()
        self.metadata = InMemoryResultPresentationMetadataProvider()

    def tearDown(self) -> None:
        self.database.close()
        for suffix in ("", "-shm", "-wal", "-journal"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                candidate.unlink()

    def service(
        self,
        telegram: FakeTelegram | None = None,
        results=None,
        publications=None,
    ) -> OfficialResultPublicationService:
        return OfficialResultPublicationService(
            results=results or self.results,
            bankroll=self.bankroll,
            publications=publications or self.publications,
            metadata=self.metadata,
            presenter=TelegramPredictionPresenter(DEFAULT_PRESENTATION_CONFIG),
            telegram=telegram or self.telegram,
            bankroll_config=DEFAULT_OFFICIAL_BANKROLL_CONFIG,
            destination=DESTINATION,
            clock=lambda: NOW,
        )

    def add_settled(
        self,
        prediction_id: str,
        fixture_id: int,
        status: ResolutionStatus,
        metadata: ResultPresentationMetadata | None = None,
        market: str = "Match Winner",
        pick: str = "Home",
        odds: Decimal = Decimal("2.00"),
        with_transaction: bool = True,
        tier: StakeTier = StakeTier.STRONG,
    ) -> ResolvedPredictionResult:
        prediction = PublishedPredictionReference(
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            market=market,
            selection=pick,
            odds=float(odds),
            published_at=NOW,
        )
        self.results.save_published(prediction)
        result = ResolvedPredictionResult(
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            status=status,
            resolved_at=NOW,
            home_score=(None if status is ResolutionStatus.VOID else 2),
            away_score=(None if status is ResolutionStatus.VOID else 1),
            settlement_rule_version="match-winner-v1",
            reason_codes=(SettlementReasonCode.MATCH_RESULT_SETTLED,),
        )
        self.results.store_if_absent(result)
        if with_transaction:
            account = self.bankroll.load_account(BankrollProduct.OFFICIAL)
            stake = Decimal("200.00")
            if status is ResolutionStatus.WON:
                gross_return = (stake * odds).quantize(Decimal("0.01"))
                profit_loss = (gross_return - stake).quantize(Decimal("0.01"))
            elif status is ResolutionStatus.LOST:
                gross_return = Decimal("0.00")
                profit_loss = -stake
            else:
                gross_return = stake
                profit_loss = Decimal("0.00")
            self.bankroll.store_transaction(BankrollTransaction(
                product_id=BankrollProduct.OFFICIAL,
                prediction_id=prediction_id,
                fixture_id=fixture_id,
                opening_balance=account.balance,
                stake=stake,
                odds=odds,
                gross_return=gross_return,
                profit_loss=profit_loss,
                closing_balance=account.balance + profit_loss,
                settlement_status=status,
                stake_tier=tier,
                settled_at=NOW,
                currency="EUR",
                rule_version="official-bankroll-v1",
            ))
        if metadata is not None:
            self.metadata._values[prediction_id] = metadata
        return result

    def publish(self, service=None):
        return asyncio.run((service or self.service()).publish_resolved())

    @staticmethod
    def context() -> ResultPresentationMetadata:
        return ResultPresentationMetadata(
            league="Premier League",
            home_team="Home FC",
            away_team="Away FC",
        )

    def test_won_message(self):
        self.add_settled("won", 1, ResolutionStatus.WON, self.context())

        report = self.publish()

        text = self.telegram.calls[0][1]
        self.assertEqual(report.won_count, 1)
        self.assertIn("<b>WON</b>", text)
        self.assertIn("Final score: 2-1", text)
        self.assertIn("Profit/Loss: +EUR 200.00", text)
        self.assertIn("Official bankroll: EUR 10200.00", text)

    def test_migration_creates_persistent_publication_tracking(self):
        columns = {
            row["name"]
            for row in self.database.connection.execute(
                "PRAGMA table_info(result_publications)"
            )
        }
        versions = tuple(
            row["version"]
            for row in self.database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )

        self.assertTrue({
            "prediction_id",
            "product_id",
            "telegram_destination",
            "publication_status",
            "telegram_message_id",
            "attempted_at",
            "published_at",
            "failure_reason",
            "format_version",
            "attempt_count",
        }.issubset(columns))
        self.assertEqual(versions, (1, 2, 3, 4))

    def test_lost_message(self):
        self.add_settled("lost", 2, ResolutionStatus.LOST, self.context())

        report = self.publish()

        text = self.telegram.calls[0][1]
        self.assertEqual(report.lost_count, 1)
        self.assertIn("<b>LOST</b>", text)
        self.assertIn("Profit/Loss: -EUR 200.00", text)

    def test_void_message(self):
        self.add_settled("void", 3, ResolutionStatus.VOID, self.context())

        report = self.publish()

        text = self.telegram.calls[0][1]
        self.assertEqual(report.void_count, 1)
        self.assertIn("<b>VOID</b>", text)
        self.assertIn("Profit/Loss: EUR 0.00", text)
        self.assertNotIn("Final score:", text)

    def test_pending_result_is_skipped(self):
        prediction = PublishedPredictionReference(
            prediction_id="pending",
            fixture_id=4,
            market="Match Winner",
            selection="Home",
            odds=2.0,
            published_at=NOW,
        )
        self.results.save_published(prediction)
        pending = ResolvedPredictionResult(
            prediction_id="pending",
            fixture_id=4,
            status=ResolutionStatus.PENDING,
            resolved_at=None,
            home_score=None,
            away_score=None,
            settlement_rule_version="match-winner-v1",
            reason_codes=(SettlementReasonCode.MATCH_PENDING,),
        )
        wrapped = HistoryOverrideRepository(self.results, (pending,))

        report = self.publish(self.service(results=wrapped))

        self.assertEqual(report.skipped_count, 1)
        self.assertEqual(report.outcomes[0].reasons, (
            ResultPublicationFailureReason.NON_TERMINAL_RESULT,
        ))
        self.assertEqual(self.telegram.calls, [])

    def test_duplicate_publication_is_prevented(self):
        self.add_settled("duplicate", 5, ResolutionStatus.WON, self.context())

        first = self.publish()
        second = self.publish()

        self.assertEqual(first.published_count, 1)
        self.assertEqual(second.skipped_count, 1)
        self.assertEqual(len(self.telegram.calls), 1)

    def test_retry_after_telegram_failure(self):
        self.add_settled("retry", 6, ResolutionStatus.WON, self.context())
        telegram = FakeTelegram(failures=1)
        service = self.service(telegram=telegram)
        balance_before = self.bankroll.load_account(
            BankrollProduct.OFFICIAL
        ).balance
        history_before = self.bankroll.transaction_history(
            BankrollProduct.OFFICIAL
        )

        first = self.publish(service)
        second = self.publish(service)

        self.assertEqual(first.failed_count, 1)
        self.assertEqual(second.published_count, 1)
        self.assertEqual(len(telegram.calls), 2)
        audit = self.publications.get(
            "retry", BankrollProduct.OFFICIAL, DESTINATION
        )
        self.assertEqual(audit.status, ResultPublicationStatus.PUBLISHED)
        self.assertEqual(audit.attempt_count, 2)
        self.assertEqual(
            self.bankroll.load_account(BankrollProduct.OFFICIAL).balance,
            balance_before,
        )
        self.assertEqual(
            self.bankroll.transaction_history(BankrollProduct.OFFICIAL),
            history_before,
        )

    def test_restart_idempotency(self):
        self.add_settled("restart", 7, ResolutionStatus.WON, self.context())
        self.publish()
        restarted = SQLiteResultPublicationRepository(self.database)
        restarted_telegram = FakeTelegram()

        report = self.publish(self.service(
            telegram=restarted_telegram,
            publications=restarted,
        ))

        self.assertEqual(report.skipped_count, 1)
        self.assertEqual(restarted_telegram.calls, [])

    def test_missing_bankroll_transaction_blocks_publication(self):
        self.add_settled(
            "missing-bank",
            8,
            ResolutionStatus.WON,
            self.context(),
            with_transaction=False,
        )

        report = self.publish()

        self.assertEqual(report.failed_count, 1)
        self.assertEqual(report.outcomes[0].reasons, (
            ResultPublicationFailureReason.BANKROLL_TRANSACTION_MISSING,
        ))
        self.assertEqual(self.telegram.calls, [])

    def test_missing_optional_presentation_metadata_is_omitted_safely(self):
        self.add_settled("missing-metadata", 81, ResolutionStatus.WON)

        report = self.publish()

        self.assertEqual(report.published_count, 1)
        self.assertEqual(report.outcomes[0].reasons, (
            ResultPublicationFailureReason.PRESENTATION_METADATA_MISSING,
        ))
        text = self.telegram.calls[0][1]
        self.assertNotIn("Premier League", text)
        self.assertIn("Match Winner", text)

    def test_database_failure_prevents_telegram_call(self):
        self.add_settled("db-failure", 9, ResolutionStatus.WON, self.context())

        report = self.publish(self.service(
            publications=FailingPublicationRepository(),
        ))

        self.assertEqual(report.failed_count, 1)
        self.assertEqual(report.outcomes[0].reasons, (
            ResultPublicationFailureReason.DATABASE_FAILED,
        ))
        self.assertEqual(self.telegram.calls, [])

    def test_database_failure_after_send_blocks_automatic_duplicate(self):
        self.add_settled("post-send-db", 91, ResolutionStatus.WON, self.context())
        repository = FailingPublishedWriteRepository(self.publications)
        service = self.service(publications=repository)

        first = self.publish(service)
        second = self.publish(service)

        self.assertEqual(first.failed_count, 1)
        self.assertEqual(second.skipped_count, 1)
        self.assertEqual(len(self.telegram.calls), 1)
        audit = self.publications.get(
            "post-send-db", BankrollProduct.OFFICIAL, DESTINATION
        )
        self.assertEqual(audit.status, ResultPublicationStatus.ATTEMPTING)

    def test_only_first_delivery_claim_is_acquired(self):
        self.add_settled("claim", 92, ResolutionStatus.WON, self.context())

        first = self.publications.begin_attempt(
            "claim",
            BankrollProduct.OFFICIAL,
            DESTINATION,
            NOW,
            "official-result-v1",
        )
        second = self.publications.begin_attempt(
            "claim",
            BankrollProduct.OFFICIAL,
            DESTINATION,
            NOW,
            "official-result-v1",
        )

        self.assertTrue(first.acquired)
        self.assertFalse(second.acquired)

    def test_star_rating_is_shown_without_percentage(self):
        self.add_settled(
            "stars",
            10,
            ResolutionStatus.WON,
            self.context(),
            tier=StakeTier.ELITE,
        )

        self.publish()

        text = self.telegram.calls[0][1]
        self.assertIn("Stake: ★★★★★ · EUR 200.00", text)
        self.assertNotIn("%", text)
        self.assertNotIn("0.03", text)

    def test_decimal_money_formatting(self):
        self.add_settled(
            "decimal",
            11,
            ResolutionStatus.WON,
            self.context(),
            odds=Decimal("1.6665"),
        )

        self.publish()

        text = self.telegram.calls[0][1]
        self.assertIn("Stake: ★★★★ · EUR 200.00", text)
        self.assertIn("Profit/Loss: +EUR 133.30", text)
        self.assertIn("Official bankroll: EUR 10133.30", text)

    def test_html_escaping(self):
        self.add_settled(
            "escape",
            12,
            ResolutionStatus.WON,
            ResultPresentationMetadata("A & B", "<Home>", "Away >"),
            market="Winner <90>",
            pick="A & B",
        )

        self.publish()

        text = self.telegram.calls[0][1]
        self.assertIn("A &amp; B", text)
        self.assertIn("&lt;Home&gt;", text)
        self.assertIn("Winner &lt;90&gt;", text)
        self.assertNotIn("<Home>", text)

    def test_mixed_batch_and_duplicate_candidates(self):
        first = self.add_settled("mixed-won", 13, ResolutionStatus.WON, self.context())
        self.add_settled(
            "mixed-missing",
            14,
            ResolutionStatus.LOST,
            self.context(),
            with_transaction=False,
        )
        history = self.results.load_history() + (first,)
        wrapped = HistoryOverrideRepository(self.results, history)

        report = self.publish(self.service(results=wrapped))

        self.assertEqual(report.published_count, 1)
        self.assertEqual(report.failed_count, 1)
        self.assertEqual(report.skipped_count, 1)
        self.assertEqual(len(self.telegram.calls), 1)

    def test_no_real_network_or_telegram_calls(self):
        self.add_settled("isolated", 15, ResolutionStatus.WON, self.context())

        with patch("httpx.AsyncClient.post") as network_post:
            report = self.publish()

        self.assertEqual(report.published_count, 1)
        network_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
