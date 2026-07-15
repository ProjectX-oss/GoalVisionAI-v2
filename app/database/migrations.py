import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    statements: tuple[str, ...]


MIGRATIONS = (
    Migration(
        version=1,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS published_predictions (
                prediction_id TEXT PRIMARY KEY,
                fixture_id INTEGER NOT NULL,
                market TEXT NOT NULL,
                pick TEXT NOT NULL,
                odds REAL,
                stake REAL,
                published_at TEXT NOT NULL,
                settlement_status TEXT NOT NULL DEFAULT 'PENDING',
                home_score INTEGER,
                away_score INTEGER,
                settlement_reason_codes TEXT NOT NULL DEFAULT '[]',
                settlement_rule_version TEXT,
                resolved_at TEXT,
                CHECK (fixture_id > 0),
                CHECK (odds IS NULL OR odds > 0),
                CHECK (stake IS NULL OR stake >= 0),
                CHECK (home_score IS NULL OR home_score >= 0),
                CHECK (away_score IS NULL OR away_score >= 0),
                CHECK (
                    settlement_status IN (
                        'WON', 'LOST', 'VOID', 'PENDING', 'UNRESOLVED'
                    )
                ),
                CHECK (
                    (settlement_status IN ('WON', 'LOST', 'VOID')
                        AND resolved_at IS NOT NULL
                        AND settlement_rule_version IS NOT NULL
                        AND settlement_reason_codes <> '[]'
                        AND (
                            settlement_status = 'VOID'
                            OR (home_score IS NOT NULL AND away_score IS NOT NULL)
                        ))
                    OR
                    (settlement_status IN ('PENDING', 'UNRESOLVED')
                        AND resolved_at IS NULL)
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_published_predictions_pending
            ON published_predictions (settlement_status, fixture_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_published_predictions_resolved
            ON published_predictions (resolved_at, prediction_id)
            """,
        ),
    ),
    Migration(
        version=2,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS bankroll_accounts (
                product_id TEXT PRIMARY KEY,
                currency TEXT NOT NULL,
                starting_balance TEXT NOT NULL,
                current_balance TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                rule_version TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS bankroll_transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                prediction_id TEXT NOT NULL,
                fixture_id INTEGER NOT NULL,
                stake_tier TEXT NOT NULL,
                public_star_rating INTEGER NOT NULL,
                opening_balance TEXT NOT NULL,
                stake_amount TEXT NOT NULL,
                decimal_odds TEXT NOT NULL,
                gross_return TEXT NOT NULL,
                profit_loss TEXT NOT NULL,
                closing_balance TEXT NOT NULL,
                settlement_status TEXT NOT NULL,
                settled_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES bankroll_accounts(product_id),
                UNIQUE (product_id, prediction_id),
                CHECK (fixture_id > 0),
                CHECK (stake_tier IN ('STANDARD', 'STRONG', 'ELITE')),
                CHECK (public_star_rating IN (3, 4, 5)),
                CHECK (settlement_status IN ('WON', 'LOST', 'VOID'))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_bankroll_transactions_history
            ON bankroll_transactions (product_id, settled_at, transaction_id)
            """,
            """
            CREATE TRIGGER IF NOT EXISTS bankroll_transactions_no_update
            BEFORE UPDATE ON bankroll_transactions
            BEGIN
                SELECT RAISE(ABORT, 'bankroll transactions are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS bankroll_transactions_no_delete
            BEFORE DELETE ON bankroll_transactions
            BEGIN
                SELECT RAISE(ABORT, 'bankroll transactions are immutable');
            END
            """,
        ),
    ),
    Migration(
        version=3,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS result_publications (
                prediction_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                telegram_destination TEXT NOT NULL,
                publication_status TEXT NOT NULL,
                telegram_message_id INTEGER,
                attempted_at TEXT NOT NULL,
                published_at TEXT,
                failure_reason TEXT,
                format_version TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (
                    prediction_id,
                    product_id,
                    telegram_destination
                ),
                FOREIGN KEY (prediction_id)
                    REFERENCES published_predictions(prediction_id),
                CHECK (product_id = 'OFFICIAL'),
                CHECK (
                    publication_status IN ('ATTEMPTING', 'PUBLISHED', 'FAILED')
                ),
                CHECK (attempt_count > 0),
                CHECK (
                    (publication_status = 'PUBLISHED'
                        AND published_at IS NOT NULL
                        AND failure_reason IS NULL)
                    OR
                    (publication_status = 'FAILED'
                        AND published_at IS NULL
                        AND failure_reason IS NOT NULL)
                    OR
                    (publication_status = 'ATTEMPTING'
                        AND published_at IS NULL
                        AND failure_reason IS NULL)
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_result_publications_status
            ON result_publications (
                product_id,
                telegram_destination,
                publication_status,
                attempted_at
            )
            """,
        ),
    ),
    Migration(
        version=4,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS quality_gate_shadow_evaluations (
                shadow_evaluation_id TEXT PRIMARY KEY,
                prediction_id TEXT NOT NULL,
                fixture_id INTEGER NOT NULL,
                product_scope TEXT NOT NULL,
                evaluation_stage TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                evaluation_timestamp TEXT NOT NULL,
                candidate_snapshot TEXT NOT NULL,
                context_snapshot TEXT NOT NULL,
                gate_status TEXT NOT NULL,
                check_results TEXT NOT NULL,
                rejection_reasons TEXT NOT NULL,
                review_reasons TEXT NOT NULL,
                evaluated_probability TEXT,
                probability_source TEXT,
                calculated_expected_value TEXT,
                market_disagreement TEXT,
                actually_published INTEGER NOT NULL,
                actual_publication_timestamp TEXT,
                actual_offered_odds TEXT,
                settlement_outcome TEXT,
                eventual_profit_loss_units TEXT,
                settled_at TEXT,
                created_at TEXT NOT NULL,
                UNIQUE (prediction_id, policy_version, evaluation_stage),
                CHECK (fixture_id > 0),
                CHECK (
                    evaluation_stage IN (
                        'INITIAL_CANDIDATE',
                        'PRE_PUBLICATION',
                        'FINAL_PRE_KICKOFF'
                    )
                ),
                CHECK (gate_status IN ('APPROVED', 'REJECTED', 'REVIEW_REQUIRED')),
                CHECK (actually_published IN (0, 1)),
                CHECK (
                    (actually_published = 1
                        AND actual_publication_timestamp IS NOT NULL)
                    OR
                    (actually_published = 0
                        AND actual_publication_timestamp IS NULL)
                ),
                CHECK (
                    settlement_outcome IS NULL
                    OR settlement_outcome IN ('WON', 'LOST', 'VOID')
                ),
                CHECK (
                    (settlement_outcome IS NULL
                        AND eventual_profit_loss_units IS NULL
                        AND settled_at IS NULL)
                    OR
                    (settlement_outcome IS NOT NULL
                        AND eventual_profit_loss_units IS NOT NULL
                        AND settled_at IS NOT NULL)
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_quality_gate_shadow_prediction
            ON quality_gate_shadow_evaluations (prediction_id, evaluation_timestamp)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_quality_gate_shadow_fixture
            ON quality_gate_shadow_evaluations (fixture_id, evaluation_timestamp)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_quality_gate_shadow_reports
            ON quality_gate_shadow_evaluations (
                policy_version,
                evaluation_timestamp,
                gate_status,
                actually_published
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS quality_gate_shadow_errors (
                shadow_evaluation_id TEXT PRIMARY KEY,
                prediction_id TEXT NOT NULL,
                evaluation_stage TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                error_type TEXT NOT NULL,
                safe_message TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                UNIQUE (prediction_id, policy_version, evaluation_stage),
                CHECK (
                    evaluation_stage IN (
                        'INITIAL_CANDIDATE',
                        'PRE_PUBLICATION',
                        'FINAL_PRE_KICKOFF'
                    )
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_quality_gate_shadow_errors_report
            ON quality_gate_shadow_errors (policy_version, occurred_at)
            """,
        ),
    ),
)


class MigrationManager:
    """Applies additive SQLite schema migrations exactly once."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def migrate(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                row[0]
                for row in self._connection.execute(
                    "SELECT version FROM schema_migrations"
                )
            }
            for migration in MIGRATIONS:
                if migration.version in applied:
                    continue
                for statement in migration.statements:
                    self._connection.execute(statement)
                self._connection.execute(
                    """
                    INSERT INTO schema_migrations (version, applied_at)
                    VALUES (?, datetime('now'))
                    """,
                    (migration.version,),
                )
