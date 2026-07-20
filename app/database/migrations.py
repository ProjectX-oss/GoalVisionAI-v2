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
    Migration(
        version=5,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS odds_sources (
                source_id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                source_type TEXT NOT NULL,
                priority INTEGER NOT NULL,
                reliability_status TEXT NOT NULL,
                commission_applies INTEGER NOT NULL,
                default_commission TEXT,
                enabled INTEGER NOT NULL,
                CHECK (priority >= 0),
                CHECK (source_type IN (
                    'BOOKMAKER', 'EXCHANGE', 'AGGREGATOR', 'INTERNAL', 'TEST'
                )),
                CHECK (reliability_status IN (
                    'RELIABLE', 'UNVERIFIED', 'DEGRADED'
                )),
                CHECK (commission_applies IN (0, 1)),
                CHECK (enabled IN (0, 1))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS odds_observations (
                observation_id TEXT PRIMARY KEY,
                fixture_id TEXT NOT NULL,
                competition TEXT NOT NULL,
                kickoff_time TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                bookmaker_or_exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                selection_id TEXT NOT NULL,
                selection_name TEXT NOT NULL,
                selection_line TEXT,
                decimal_odds TEXT NOT NULL,
                available_limit TEXT,
                currency TEXT,
                is_exchange INTEGER NOT NULL,
                commission_rate TEXT,
                raw_provider_reference TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (source_name)
                    REFERENCES odds_sources(source_name),
                UNIQUE (
                    fixture_id, source_name, market, selection_id,
                    observed_at, decimal_odds
                ),
                CHECK (fixture_id <> ''),
                CHECK (market <> ''),
                CHECK (selection_id <> ''),
                CHECK (is_exchange IN (0, 1))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_odds_fixture_market_time
            ON odds_observations (
                fixture_id, market, selection_id, observed_at
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_odds_source_time
            ON odds_observations (source_name, observed_at)
            """,
            """
            CREATE TABLE IF NOT EXISTS closing_odds (
                closing_id TEXT PRIMARY KEY,
                fixture_id TEXT NOT NULL,
                market TEXT NOT NULL,
                selection_id TEXT NOT NULL,
                selection_name TEXT NOT NULL,
                selection_line TEXT,
                kickoff_time TEXT NOT NULL,
                selected_at TEXT NOT NULL,
                closing_observed_at TEXT NOT NULL,
                decimal_odds TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                selection_path TEXT NOT NULL,
                source_count INTEGER NOT NULL,
                cutoff TEXT NOT NULL,
                observation_id TEXT,
                UNIQUE (fixture_id, market, selection_id),
                FOREIGN KEY (observation_id)
                    REFERENCES odds_observations(observation_id),
                CHECK (source_count > 0),
                CHECK (selection_path IN (
                    'PREFERRED_EXCHANGE', 'WEIGHTED_CONSENSUS',
                    'PRIORITY_BOOKMAKER', 'UNAVAILABLE'
                ))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_closing_odds_lookup
            ON closing_odds (fixture_id, market, selection_id, cutoff)
            """,
        ),
    ),
    Migration(
        version=6,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS availability_sources (
                source_id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                priority INTEGER NOT NULL,
                reliability_status TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                CHECK (priority >= 0),
                CHECK (reliability_status IN (
                    'RELIABLE', 'UNVERIFIED', 'DEGRADED'
                )),
                CHECK (enabled IN (0, 1))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS player_availability_observations (
                observation_id TEXT PRIMARY KEY,
                fixture_id TEXT NOT NULL,
                competition TEXT NOT NULL,
                team_id TEXT NOT NULL,
                team_name TEXT NOT NULL,
                player_id TEXT,
                player_name TEXT NOT NULL,
                player_identity_key TEXT NOT NULL,
                fixture_team_side TEXT NOT NULL,
                availability_status TEXT NOT NULL,
                reason TEXT NOT NULL,
                provider_reason_text TEXT,
                observed_at TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                expected_return_at TEXT,
                confidence TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (source_name)
                    REFERENCES availability_sources(source_name),
                UNIQUE (
                    fixture_id, team_id, player_identity_key,
                    availability_status, reason, observed_at, source_name
                ),
                CHECK (fixture_id <> ''),
                CHECK (team_id <> ''),
                CHECK (player_identity_key <> ''),
                CHECK (fixture_team_side IN ('HOME', 'AWAY')),
                CHECK (availability_status IN (
                    'AVAILABLE', 'UNAVAILABLE', 'DOUBTFUL', 'SUSPENDED',
                    'INJURED', 'ILL', 'RESTED', 'NOT_SELECTED', 'UNKNOWN'
                ))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_availability_fixture_team_time
            ON player_availability_observations (
                fixture_id, team_id, observed_at, player_identity_key
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_availability_player_time
            ON player_availability_observations (
                player_identity_key, observed_at
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS lineup_observations (
                lineup_observation_id TEXT PRIMARY KEY,
                fixture_id TEXT NOT NULL,
                competition TEXT NOT NULL,
                team_id TEXT NOT NULL,
                team_name TEXT NOT NULL,
                fixture_team_side TEXT NOT NULL,
                lineup_status TEXT NOT NULL,
                lineup_type TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                formation TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (source_name)
                    REFERENCES availability_sources(source_name),
                UNIQUE (
                    fixture_id, team_id, lineup_type, observed_at, source_name
                ),
                CHECK (fixture_team_side IN ('HOME', 'AWAY')),
                CHECK (lineup_status IN (
                    'NOT_AVAILABLE', 'PREDICTED', 'PARTIAL', 'CONFIRMED'
                )),
                CHECK (lineup_type IN ('STARTING', 'SUBSTITUTE', 'SQUAD'))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_lineup_fixture_team_status_time
            ON lineup_observations (
                fixture_id, team_id, lineup_status, observed_at
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS lineup_players (
                lineup_observation_id TEXT NOT NULL,
                player_identity_key TEXT NOT NULL,
                player_id TEXT,
                player_name TEXT NOT NULL,
                role TEXT NOT NULL,
                position TEXT NOT NULL,
                shirt_number INTEGER,
                is_starting INTEGER NOT NULL,
                is_captain INTEGER,
                is_goalkeeper INTEGER NOT NULL,
                source_order INTEGER NOT NULL,
                PRIMARY KEY (lineup_observation_id, player_identity_key),
                FOREIGN KEY (lineup_observation_id)
                    REFERENCES lineup_observations(lineup_observation_id),
                CHECK (shirt_number IS NULL OR shirt_number > 0),
                CHECK (is_starting IN (0, 1)),
                CHECK (is_captain IS NULL OR is_captain IN (0, 1)),
                CHECK (is_goalkeeper IN (0, 1)),
                CHECK (source_order >= 0)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_lineup_players_identity
            ON lineup_players (player_identity_key, lineup_observation_id)
            """,
        ),
    ),
    Migration(
        version=7,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS form_feature_sources (
                source_id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                enabled INTEGER NOT NULL,
                CHECK (enabled IN (0, 1))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_match_observations (
                observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id TEXT NOT NULL,
                competition TEXT NOT NULL,
                kickoff_time TEXT NOT NULL,
                home_team_id TEXT NOT NULL,
                away_team_id TEXT NOT NULL,
                home_goals INTEGER NOT NULL,
                away_goals INTEGER NOT NULL,
                match_status TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                home_xg TEXT,
                away_xg TEXT,
                home_shots INTEGER,
                away_shots INTEGER,
                home_red_cards INTEGER,
                away_red_cards INTEGER,
                penalties INTEGER,
                source_name TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (source_name)
                    REFERENCES form_feature_sources(source_name),
                UNIQUE (fixture_id, source_name, observed_at),
                CHECK (fixture_id <> ''),
                CHECK (home_team_id <> ''),
                CHECK (away_team_id <> ''),
                CHECK (home_team_id <> away_team_id),
                CHECK (home_goals >= 0),
                CHECK (away_goals >= 0)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_form_fixture
            ON historical_match_observations (fixture_id, observed_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_form_home_history
            ON historical_match_observations (
                home_team_id, kickoff_time, observed_at
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_form_away_history
            ON historical_match_observations (
                away_team_id, kickoff_time, observed_at
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_form_competition_history
            ON historical_match_observations (
                competition, match_status, kickoff_time
            )
            """,
        ),
    ),
    Migration(
        version=8,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS calibration_artifacts (
                artifact_id TEXT PRIMARY KEY,
                method TEXT NOT NULL,
                method_version TEXT NOT NULL,
                serialized_calibrator TEXT NOT NULL,
                serialized_parameters_fingerprint TEXT NOT NULL,
                configuration_fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                fitted_at TEXT NOT NULL,
                training_window_start TEXT NOT NULL,
                training_window_end TEXT NOT NULL,
                training_cutoff TEXT NOT NULL,
                observation_count INTEGER NOT NULL,
                positive_count INTEGER NOT NULL,
                negative_count INTEGER NOT NULL,
                competition_scope TEXT,
                market_scope TEXT,
                odds_band_scope TEXT,
                model_version_scope TEXT,
                calibration_scope TEXT NOT NULL,
                fit_version TEXT NOT NULL,
                fitting_diagnostics TEXT NOT NULL,
                training_metrics TEXT NOT NULL,
                validation_metrics TEXT,
                status TEXT NOT NULL,
                status_reason TEXT NOT NULL,
                parent_artifact_id TEXT,
                FOREIGN KEY (parent_artifact_id)
                    REFERENCES calibration_artifacts(artifact_id),
                UNIQUE (
                    method, method_version, configuration_fingerprint,
                    competition_scope, market_scope, odds_band_scope,
                    model_version_scope, calibration_scope, training_cutoff,
                    serialized_parameters_fingerprint
                ),
                CHECK (observation_count >= 0),
                CHECK (positive_count >= 0),
                CHECK (negative_count >= 0),
                CHECK (positive_count + negative_count = observation_count),
                CHECK (status IN (
                    'CANDIDATE', 'VALIDATED', 'SHADOW', 'RETIRED', 'REJECTED'
                ))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_calibration_artifacts_scope
            ON calibration_artifacts (
                competition_scope, market_scope, odds_band_scope,
                calibration_scope, training_cutoff, artifact_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_calibration_artifacts_method_model
            ON calibration_artifacts (
                method, model_version_scope, fitted_at, artifact_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_calibration_artifacts_status
            ON calibration_artifacts (status, fitted_at, artifact_id)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_calibration_artifacts_equivalent
            ON calibration_artifacts (
                method,
                method_version,
                configuration_fingerprint,
                IFNULL(competition_scope, ''),
                IFNULL(market_scope, ''),
                IFNULL(odds_band_scope, ''),
                IFNULL(model_version_scope, ''),
                calibration_scope,
                training_cutoff,
                serialized_parameters_fingerprint
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS calibration_artifacts_no_update
            BEFORE UPDATE ON calibration_artifacts
            BEGIN
                SELECT RAISE(ABORT, 'calibration artifacts are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS calibration_artifacts_no_delete
            BEFORE DELETE ON calibration_artifacts
            BEGIN
                SELECT RAISE(ABORT, 'calibration artifacts are immutable');
            END
            """,
            """
            CREATE TABLE IF NOT EXISTS calibration_artifact_status_history (
                transition_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                reason TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                actor_source TEXT NOT NULL,
                FOREIGN KEY (artifact_id)
                    REFERENCES calibration_artifacts(artifact_id),
                UNIQUE (
                    artifact_id, previous_status, new_status,
                    reason, changed_at, actor_source
                ),
                CHECK (previous_status IN (
                    'CANDIDATE', 'VALIDATED', 'SHADOW', 'RETIRED', 'REJECTED'
                )),
                CHECK (new_status IN (
                    'CANDIDATE', 'VALIDATED', 'SHADOW', 'RETIRED', 'REJECTED'
                ))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_calibration_status_history
            ON calibration_artifact_status_history (
                artifact_id, changed_at, transition_id
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS calibration_status_history_no_update
            BEFORE UPDATE ON calibration_artifact_status_history
            BEGIN
                SELECT RAISE(ABORT, 'calibration status history is immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS calibration_status_history_no_delete
            BEFORE DELETE ON calibration_artifact_status_history
            BEGIN
                SELECT RAISE(ABORT, 'calibration status history is immutable');
            END
            """,
            """
            CREATE TABLE IF NOT EXISTS model_monitoring_runs (
                run_id TEXT PRIMARY KEY,
                policy_version TEXT NOT NULL,
                baseline_window TEXT NOT NULL,
                current_window TEXT NOT NULL,
                scope TEXT NOT NULL,
                artifact_id TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                baseline_observation_count INTEGER NOT NULL,
                current_observation_count INTEGER NOT NULL,
                report_snapshot TEXT NOT NULL,
                findings TEXT NOT NULL,
                run_status TEXT NOT NULL,
                safe_error_type TEXT,
                safe_error_message TEXT,
                FOREIGN KEY (artifact_id)
                    REFERENCES calibration_artifacts(artifact_id),
                CHECK (baseline_observation_count >= 0),
                CHECK (current_observation_count >= 0),
                CHECK (run_status IN (
                    'COMPLETED', 'INSUFFICIENT_DATA', 'FAILED'
                ))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_model_monitoring_runs_scope
            ON model_monitoring_runs (
                scope, artifact_id, completed_at, run_id
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS model_monitoring_runs_no_update
            BEFORE UPDATE ON model_monitoring_runs
            BEGIN
                SELECT RAISE(ABORT, 'model monitoring runs are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS model_monitoring_runs_no_delete
            BEFORE DELETE ON model_monitoring_runs
            BEGIN
                SELECT RAISE(ABORT, 'model monitoring runs are immutable');
            END
            """,
            """
            CREATE TABLE IF NOT EXISTS model_monitoring_alerts (
                alert_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                finding_type TEXT NOT NULL,
                metric TEXT NOT NULL,
                threshold_version TEXT NOT NULL,
                severity TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                finding_snapshot TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES model_monitoring_runs(run_id),
                UNIQUE (
                    run_id, scope, finding_type, metric, threshold_version
                ),
                CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL'))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_model_monitoring_alerts_run
            ON model_monitoring_alerts (run_id, severity, alert_id)
            """,
            """
            CREATE TRIGGER IF NOT EXISTS model_monitoring_alerts_no_update
            BEFORE UPDATE ON model_monitoring_alerts
            BEGIN
                SELECT RAISE(ABORT, 'model monitoring alerts are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS model_monitoring_alerts_no_delete
            BEFORE DELETE ON model_monitoring_alerts
            BEGIN
                SELECT RAISE(ABORT, 'model monitoring alerts are immutable');
            END
            """,
        ),
    ),
    Migration(
        version=9,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS probability_calibration_history (
                calibration_run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                model_version TEXT NOT NULL,
                calibration_version TEXT NOT NULL,
                calibration_method TEXT NOT NULL,
                raw_probability TEXT NOT NULL,
                calibrated_probability TEXT NOT NULL,
                delta TEXT NOT NULL,
                observation_count INTEGER NOT NULL,
                brier_score TEXT NOT NULL,
                log_loss TEXT NOT NULL,
                expected_calibration_error TEXT NOT NULL,
                maximum_calibration_error TEXT NOT NULL,
                reliability_bins TEXT NOT NULL,
                confidence_histogram TEXT NOT NULL,
                CHECK (calibration_method IN ('identity', 'platt', 'isotonic')),
                CHECK (observation_count >= 0)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_probability_calibration_model_history
            ON probability_calibration_history (
                model_version, created_at, calibration_run_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_probability_calibration_method_history
            ON probability_calibration_history (
                calibration_method, created_at, calibration_run_id
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS probability_calibration_history_no_update
            BEFORE UPDATE ON probability_calibration_history
            BEGIN
                SELECT RAISE(ABORT, 'probability calibration history is immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS probability_calibration_history_no_delete
            BEFORE DELETE ON probability_calibration_history
            BEGIN
                SELECT RAISE(ABORT, 'probability calibration history is immutable');
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
