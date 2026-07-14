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
