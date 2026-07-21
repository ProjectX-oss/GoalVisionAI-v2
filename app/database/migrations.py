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
    Migration(
        version=10,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS official_quality_gate_evaluations (
                evaluation_id TEXT PRIMARY KEY,
                prediction_id TEXT NOT NULL,
                input_fingerprint TEXT NOT NULL,
                final_decision TEXT NOT NULL,
                ordered_reason_codes TEXT NOT NULL,
                internal_explanations TEXT NOT NULL,
                findings TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                model_version TEXT NOT NULL,
                raw_probability TEXT NOT NULL,
                calibrated_probability TEXT,
                decimal_odds TEXT NOT NULL,
                supplied_expected_value TEXT,
                recomputed_expected_value TEXT,
                confidence TEXT NOT NULL,
                prediction_timestamp TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                evaluated_at TEXT NOT NULL,
                normalized_input TEXT NOT NULL,
                risk_result TEXT NOT NULL,
                exposure_result TEXT NOT NULL,
                UNIQUE (prediction_id, policy_version, input_fingerprint),
                CHECK (final_decision IN (
                    'APPROVED', 'REJECTED', 'REVIEW_REQUIRED'
                )),
                CHECK (confidence IN ('LOW', 'MEDIUM', 'HIGH', 'ELITE')),
                CHECK (risk_result IN (
                    'ELIGIBLE', 'REDUCED_STAKE',
                    'REVIEW_REQUIRED', 'INELIGIBLE'
                )),
                CHECK (exposure_result IN (
                    'CLEAR', 'WARNING', 'HARD_BREACH'
                ))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_quality_gate_prediction
            ON official_quality_gate_evaluations (
                prediction_id, evaluated_at, evaluation_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_quality_gate_decision
            ON official_quality_gate_evaluations (
                final_decision, evaluated_at, evaluation_id
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_quality_gate_no_update
            BEFORE UPDATE ON official_quality_gate_evaluations
            BEGIN
                SELECT RAISE(ABORT, 'Official Quality Gate history is immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_quality_gate_no_delete
            BEFORE DELETE ON official_quality_gate_evaluations
            BEGIN
                SELECT RAISE(ABORT, 'Official Quality Gate history is immutable');
            END
            """,
        ),
    ),
    Migration(
        version=11,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS official_prediction_orchestrations (
                orchestration_id TEXT PRIMARY KEY,
                prediction_id TEXT NOT NULL,
                candidate_fingerprint TEXT,
                gate_evaluation_id TEXT,
                final_status TEXT NOT NULL,
                ordered_reasons TEXT NOT NULL,
                internal_explanations TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                model_version TEXT NOT NULL,
                dry_run INTEGER NOT NULL,
                publisher_attempt_reference TEXT,
                normalized_input_snapshot TEXT NOT NULL,
                evaluated_timestamp TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (gate_evaluation_id)
                    REFERENCES official_quality_gate_evaluations(evaluation_id),
                CHECK (dry_run IN (0, 1)),
                CHECK (final_status IN (
                    'PUBLISHED', 'APPROVED_NOT_PUBLISHED', 'REJECTED',
                    'REVIEW_REQUIRED', 'DUPLICATE_BLOCKED',
                    'RETRYABLE_PUBLICATION_FAILURE',
                    'INDETERMINATE_PUBLICATION_FAILURE', 'ASSEMBLY_FAILED'
                ))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_orchestration_candidate
            ON official_prediction_orchestrations (
                prediction_id, candidate_fingerprint, dry_run,
                created_timestamp, orchestration_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_orchestration_status
            ON official_prediction_orchestrations (
                final_status, created_timestamp, orchestration_id
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_orchestration_no_update
            BEFORE UPDATE ON official_prediction_orchestrations
            BEGIN
                SELECT RAISE(ABORT, 'Official prediction orchestration history is immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_orchestration_no_delete
            BEFORE DELETE ON official_prediction_orchestrations
            BEGIN
                SELECT RAISE(ABORT, 'Official prediction orchestration history is immutable');
            END
            """,
        ),
    ),
    Migration(
        version=12,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS official_prediction_publication_events (
                event_id TEXT PRIMARY KEY,
                attempt_reference TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                event_sequence INTEGER NOT NULL,
                prediction_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                orchestration_id TEXT NOT NULL,
                gate_evaluation_id TEXT NOT NULL,
                candidate_fingerprint TEXT NOT NULL,
                message_fingerprint TEXT NOT NULL,
                destination_scope TEXT NOT NULL,
                status TEXT NOT NULL,
                telegram_message_id INTEGER,
                failure_reason TEXT,
                payload_snapshot TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY (gate_evaluation_id)
                    REFERENCES official_quality_gate_evaluations(evaluation_id),
                UNIQUE (prediction_id, destination_scope, attempt_number, event_sequence),
                UNIQUE (attempt_reference, status),
                CHECK (attempt_number > 0),
                CHECK (event_sequence IN (1, 2)),
                CHECK (destination_scope = 'OFFICIAL'),
                CHECK (status IN ('CLAIMED', 'PUBLISHED', 'FAILED', 'INDETERMINATE')),
                CHECK (
                    (status = 'CLAIMED' AND event_sequence = 1
                        AND failure_reason IS NULL
                        AND telegram_message_id IS NULL)
                    OR
                    (status = 'PUBLISHED' AND event_sequence = 2
                        AND failure_reason IS NULL)
                    OR
                    (status IN ('FAILED', 'INDETERMINATE')
                        AND event_sequence = 2
                        AND failure_reason IS NOT NULL)
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_prediction_publication_latest
            ON official_prediction_publication_events (
                prediction_id, destination_scope,
                attempt_number DESC, event_sequence DESC
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_prediction_message_fingerprint
            ON official_prediction_publication_events (
                message_fingerprint, status, occurred_at, event_id
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_publication_no_update
            BEFORE UPDATE ON official_prediction_publication_events
            BEGIN
                SELECT RAISE(ABORT, 'Official prediction publication events are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_publication_no_delete
            BEFORE DELETE ON official_prediction_publication_events
            BEGIN
                SELECT RAISE(ABORT, 'Official prediction publication events are immutable');
            END
            """,
        ),
    ),
    Migration(
        version=13,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS official_prediction_runs (
                run_event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                event_sequence INTEGER NOT NULL,
                run_fingerprint TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                run_status TEXT,
                policy_version TEXT NOT NULL,
                dry_run INTEGER NOT NULL,
                bankroll_scope TEXT NOT NULL,
                destination_scope TEXT NOT NULL,
                started_timestamp TEXT NOT NULL,
                completed_timestamp TEXT,
                discovered_count INTEGER,
                eligible_count INTEGER,
                processed_count INTEGER,
                published_count INTEGER,
                approved_not_published_count INTEGER,
                rejected_count INTEGER,
                review_required_count INTEGER,
                duplicate_blocked_count INTEGER,
                retryable_failure_count INTEGER,
                indeterminate_failure_count INTEGER,
                assembly_failure_count INTEGER,
                skipped_count INTEGER,
                internal_failure_count INTEGER,
                ordered_reasons TEXT NOT NULL,
                stop_reason TEXT,
                request_snapshot TEXT NOT NULL,
                summary_snapshot TEXT,
                UNIQUE (run_id, event_sequence),
                CHECK (event_sequence IN (1, 2)),
                CHECK (dry_run IN (0, 1)),
                CHECK (bankroll_scope = 'OFFICIAL'),
                CHECK (destination_scope = 'OFFICIAL'),
                CHECK (
                    run_status IS NULL OR run_status IN (
                        'COMPLETED', 'COMPLETED_WITH_FAILURES',
                        'DRY_RUN_COMPLETED', 'NO_ELIGIBLE_CANDIDATES',
                        'ABORTED', 'FAILED_TO_START', 'INDETERMINATE'
                    )
                ),
                CHECK (
                    (event_sequence = 1
                        AND run_status IS NULL
                        AND completed_timestamp IS NULL
                        AND discovered_count IS NULL
                        AND summary_snapshot IS NULL)
                    OR
                    (event_sequence = 2
                        AND run_status IS NOT NULL
                        AND completed_timestamp IS NOT NULL
                        AND discovered_count IS NOT NULL
                        AND eligible_count IS NOT NULL
                        AND processed_count IS NOT NULL
                        AND published_count IS NOT NULL
                        AND approved_not_published_count IS NOT NULL
                        AND rejected_count IS NOT NULL
                        AND review_required_count IS NOT NULL
                        AND duplicate_blocked_count IS NOT NULL
                        AND retryable_failure_count IS NOT NULL
                        AND indeterminate_failure_count IS NOT NULL
                        AND assembly_failure_count IS NOT NULL
                        AND skipped_count IS NOT NULL
                        AND internal_failure_count IS NOT NULL
                        AND discovered_count >= 0
                        AND eligible_count >= 0
                        AND processed_count >= 0
                        AND published_count >= 0
                        AND approved_not_published_count >= 0
                        AND rejected_count >= 0
                        AND review_required_count >= 0
                        AND duplicate_blocked_count >= 0
                        AND retryable_failure_count >= 0
                        AND indeterminate_failure_count >= 0
                        AND assembly_failure_count >= 0
                        AND skipped_count >= 0
                        AND internal_failure_count >= 0
                        AND discovered_count = processed_count + skipped_count
                        AND eligible_count = processed_count
                        AND processed_count =
                            published_count + approved_not_published_count
                            + rejected_count + review_required_count
                            + duplicate_blocked_count + retryable_failure_count
                            + indeterminate_failure_count + assembly_failure_count
                            + internal_failure_count
                        AND summary_snapshot IS NOT NULL)
                )
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_official_prediction_run_fingerprint
            ON official_prediction_runs (run_fingerprint)
            WHERE event_sequence = 1
            """,
            """
            CREATE TABLE IF NOT EXISTS official_prediction_run_items (
                run_item_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                run_event_sequence INTEGER NOT NULL DEFAULT 1,
                item_index INTEGER NOT NULL,
                prediction_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                candidate_fingerprint TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                discovery_status TEXT NOT NULL,
                item_status TEXT NOT NULL,
                was_eligible INTEGER NOT NULL,
                orchestration_id TEXT,
                publication_attempt_reference TEXT,
                started_timestamp TEXT NOT NULL,
                completed_timestamp TEXT NOT NULL,
                ordered_reasons TEXT NOT NULL,
                result_snapshot TEXT NOT NULL,
                FOREIGN KEY (run_id, run_event_sequence)
                    REFERENCES official_prediction_runs(run_id, event_sequence),
                UNIQUE (run_id, item_index),
                CHECK (run_event_sequence = 1),
                CHECK (item_index >= 0),
                CHECK (was_eligible IN (0, 1)),
                CHECK (discovery_status IN (
                    'READY', 'ALREADY_PUBLISHED', 'ACTIVE_DUPLICATE_CLAIM',
                    'RETRYABLE_CONFIRMED_FAILURE', 'INDETERMINATE',
                    'REJECTED_IMMUTABLE', 'REVIEW_REQUIRED_IMMUTABLE',
                    'EXPIRED', 'MALFORMED', 'NOT_YET_ELIGIBLE',
                    'NON_OFFICIAL'
                )),
                CHECK (item_status IN (
                    'PUBLISHED', 'APPROVED_NOT_PUBLISHED', 'REJECTED',
                    'REVIEW_REQUIRED', 'DUPLICATE_BLOCKED',
                    'RETRYABLE_PUBLICATION_FAILURE',
                    'INDETERMINATE_PUBLICATION_FAILURE', 'ASSEMBLY_FAILED',
                    'SKIPPED_ALREADY_PUBLISHED', 'SKIPPED_ACTIVE_CLAIM',
                    'SKIPPED_INDETERMINATE', 'SKIPPED_EXPIRED',
                    'SKIPPED_NOT_ELIGIBLE', 'SKIPPED_RETRY_LIMIT',
                    'SKIPPED_RETRY_COOLDOWN', 'INTERNAL_FAILURE'
                )),
                CHECK (
                    (was_eligible = 0 AND item_status IN (
                        'SKIPPED_ALREADY_PUBLISHED', 'SKIPPED_ACTIVE_CLAIM',
                        'SKIPPED_INDETERMINATE', 'SKIPPED_EXPIRED',
                        'SKIPPED_NOT_ELIGIBLE', 'SKIPPED_RETRY_LIMIT',
                        'SKIPPED_RETRY_COOLDOWN'
                    ))
                    OR
                    (was_eligible = 1 AND item_status NOT IN (
                        'SKIPPED_ALREADY_PUBLISHED', 'SKIPPED_ACTIVE_CLAIM',
                        'SKIPPED_INDETERMINATE', 'SKIPPED_EXPIRED',
                        'SKIPPED_NOT_ELIGIBLE', 'SKIPPED_RETRY_LIMIT',
                        'SKIPPED_RETRY_COOLDOWN'
                    ))
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_prediction_run_items_order
            ON official_prediction_run_items (run_id, item_index)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_prediction_run_items_candidate
            ON official_prediction_run_items (
                prediction_id, candidate_fingerprint,
                completed_timestamp, run_item_id
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_runs_no_update
            BEFORE UPDATE ON official_prediction_runs
            BEGIN
                SELECT RAISE(ABORT, 'Official prediction run history is immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_runs_no_delete
            BEFORE DELETE ON official_prediction_runs
            BEGIN
                SELECT RAISE(ABORT, 'Official prediction run history is immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_run_items_no_update
            BEFORE UPDATE ON official_prediction_run_items
            BEGIN
                SELECT RAISE(ABORT, 'Official prediction run items are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_run_items_no_delete
            BEFORE DELETE ON official_prediction_run_items
            BEGIN
                SELECT RAISE(ABORT, 'Official prediction run items are immutable');
            END
            """,
        ),
    ),
    Migration(
        version=14,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS official_prediction_candidate_versions (
                registry_candidate_id TEXT PRIMARY KEY,
                logical_identity_fingerprint TEXT NOT NULL,
                content_fingerprint TEXT NOT NULL UNIQUE,
                candidate_version INTEGER NOT NULL,
                prediction_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                competition_id TEXT,
                competition_display_name TEXT NOT NULL,
                competition_normalized_name TEXT NOT NULL,
                home_team_id TEXT,
                home_team_display_name TEXT NOT NULL,
                home_team_normalized_name TEXT NOT NULL,
                away_team_id TEXT,
                away_team_display_name TEXT NOT NULL,
                away_team_normalized_name TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                prediction_creation_timestamp TEXT NOT NULL,
                model_version TEXT NOT NULL,
                normalized_market TEXT NOT NULL,
                normalized_selection TEXT NOT NULL,
                market_line TEXT,
                raw_model_probability TEXT NOT NULL,
                supplied_expected_value TEXT NOT NULL,
                decimal_odds TEXT NOT NULL,
                odds_timestamp TEXT NOT NULL,
                odds_source_id TEXT NOT NULL,
                core_match_data_timestamp TEXT NOT NULL,
                lineup_status TEXT NOT NULL,
                lineup_data_timestamp TEXT,
                injury_suspension_status TEXT NOT NULL,
                injury_suspension_data_timestamp TEXT,
                confidence_level TEXT NOT NULL,
                supporting_data_status TEXT NOT NULL,
                market_availability TEXT NOT NULL,
                reasoning_snapshot TEXT NOT NULL,
                source_data_version TEXT NOT NULL,
                bankroll_scope TEXT NOT NULL,
                destination_scope TEXT NOT NULL,
                lifecycle_state_at_creation TEXT NOT NULL,
                registration_timestamp TEXT NOT NULL,
                normalized_snapshot TEXT NOT NULL,
                candidate_snapshot TEXT NOT NULL,
                UNIQUE (logical_identity_fingerprint, candidate_version),
                CHECK (candidate_version > 0),
                CHECK (normalized_market IN (
                    'MATCH_WINNER', 'DOUBLE_CHANCE', 'TOTALS', 'BTTS'
                )),
                CHECK (
                    (normalized_market = 'TOTALS' AND market_line IS NOT NULL)
                    OR
                    (normalized_market <> 'TOTALS' AND market_line IS NULL)
                ),
                CHECK (lineup_status IN (
                    'CONFIRMED', 'UNCONFIRMED', 'MISSING', 'NOT_APPLICABLE'
                )),
                CHECK (injury_suspension_status IN (
                    'AVAILABLE', 'PARTIAL', 'MISSING'
                )),
                CHECK (confidence_level IN ('LOW', 'MEDIUM', 'HIGH', 'ELITE')),
                CHECK (supporting_data_status IN (
                    'AVAILABLE', 'PARTIAL', 'MISSING'
                )),
                CHECK (market_availability IN (
                    'AVAILABLE', 'LIMITED', 'UNAVAILABLE'
                )),
                CHECK (bankroll_scope = 'OFFICIAL'),
                CHECK (destination_scope = 'OFFICIAL'),
                CHECK (lifecycle_state_at_creation = 'READY')
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_candidate_identity_versions
            ON official_prediction_candidate_versions (
                logical_identity_fingerprint, candidate_version,
                registry_candidate_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_candidate_discovery
            ON official_prediction_candidate_versions (
                kickoff_timestamp, prediction_creation_timestamp,
                prediction_id, candidate_version
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS official_prediction_candidate_lifecycle_events (
                event_id TEXT PRIMARY KEY,
                registry_candidate_id TEXT NOT NULL,
                event_sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                previous_candidate_id TEXT,
                event_timestamp TEXT NOT NULL,
                event_snapshot TEXT NOT NULL,
                FOREIGN KEY (registry_candidate_id)
                    REFERENCES official_prediction_candidate_versions(registry_candidate_id),
                FOREIGN KEY (previous_candidate_id)
                    REFERENCES official_prediction_candidate_versions(registry_candidate_id),
                UNIQUE (registry_candidate_id, event_sequence),
                CHECK (event_sequence > 0),
                CHECK (event_type IN (
                    'READY', 'SUPERSEDED', 'WITHDRAWN', 'INVALIDATED'
                ))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_candidate_lifecycle_latest
            ON official_prediction_candidate_lifecycle_events (
                registry_candidate_id, event_sequence DESC, event_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_official_candidate_lifecycle_state
            ON official_prediction_candidate_lifecycle_events (
                event_type, event_timestamp, registry_candidate_id
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_candidate_versions_no_update
            BEFORE UPDATE ON official_prediction_candidate_versions
            BEGIN
                SELECT RAISE(ABORT, 'Official candidate versions are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_candidate_versions_no_delete
            BEFORE DELETE ON official_prediction_candidate_versions
            BEGIN
                SELECT RAISE(ABORT, 'Official candidate versions are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_candidate_lifecycle_no_update
            BEFORE UPDATE ON official_prediction_candidate_lifecycle_events
            BEGIN
                SELECT RAISE(ABORT, 'Official candidate lifecycle is immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_prediction_candidate_lifecycle_no_delete
            BEFORE DELETE ON official_prediction_candidate_lifecycle_events
            BEGIN
                SELECT RAISE(ABORT, 'Official candidate lifecycle is immutable');
            END
            """,
        ),
    ),
    Migration(
        version=15,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS match_data_snapshot_versions (
                snapshot_id TEXT PRIMARY KEY,
                logical_identity_fingerprint TEXT NOT NULL,
                content_fingerprint TEXT NOT NULL UNIQUE,
                snapshot_version INTEGER NOT NULL,
                match_id TEXT NOT NULL,
                source_provider TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                source_snapshot_id TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                effective_timestamp TEXT NOT NULL,
                source_updated_timestamp TEXT NOT NULL,
                registration_timestamp TEXT NOT NULL,
                lifecycle_state_at_creation TEXT NOT NULL,
                deterministic_snapshot TEXT NOT NULL,
                UNIQUE (logical_identity_fingerprint, snapshot_version),
                CHECK (snapshot_version > 0),
                CHECK (lifecycle_state_at_creation = 'ACTIVE')
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_match_snapshot_match
            ON match_data_snapshot_versions (match_id, snapshot_version)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_match_snapshot_kickoff
            ON match_data_snapshot_versions (kickoff_timestamp, snapshot_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_match_snapshot_source
            ON match_data_snapshot_versions (
                source_provider, source_event_id, source_snapshot_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_match_snapshot_effective
            ON match_data_snapshot_versions (effective_timestamp, snapshot_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS match_data_snapshot_lifecycle_events (
                event_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                event_sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                previous_snapshot_id TEXT,
                event_timestamp TEXT NOT NULL,
                event_snapshot TEXT NOT NULL,
                FOREIGN KEY (snapshot_id)
                    REFERENCES match_data_snapshot_versions(snapshot_id),
                FOREIGN KEY (previous_snapshot_id)
                    REFERENCES match_data_snapshot_versions(snapshot_id),
                UNIQUE (snapshot_id, event_sequence),
                CHECK (event_sequence > 0),
                CHECK (event_type IN (
                    'ACTIVE', 'SUPERSEDED', 'WITHDRAWN', 'INVALIDATED'
                ))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_match_snapshot_lifecycle_latest
            ON match_data_snapshot_lifecycle_events (
                snapshot_id, event_sequence DESC, event_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_match_snapshot_active
            ON match_data_snapshot_lifecycle_events (
                event_type, event_timestamp, snapshot_id
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS match_feature_sets (
                feature_set_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                schema_name TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                model_compatibility_version TEXT NOT NULL,
                source_snapshot_fingerprint TEXT NOT NULL,
                feature_fingerprint TEXT NOT NULL UNIQUE,
                deterministic_feature_snapshot TEXT NOT NULL,
                missingness_snapshot TEXT NOT NULL,
                data_quality_snapshot TEXT NOT NULL,
                feature_timestamp TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (snapshot_id)
                    REFERENCES match_data_snapshot_versions(snapshot_id),
                UNIQUE (
                    snapshot_id, schema_name, schema_version,
                    model_compatibility_version
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_match_feature_match
            ON match_feature_sets (match_id, feature_timestamp, feature_set_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_match_feature_snapshot
            ON match_feature_sets (snapshot_id, schema_name, schema_version)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_match_feature_schema
            ON match_feature_sets (
                schema_name, schema_version, model_compatibility_version,
                feature_timestamp
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS match_data_snapshot_versions_no_update
            BEFORE UPDATE ON match_data_snapshot_versions
            BEGIN
                SELECT RAISE(ABORT, 'Match data snapshot versions are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS match_data_snapshot_versions_no_delete
            BEFORE DELETE ON match_data_snapshot_versions
            BEGIN
                SELECT RAISE(ABORT, 'Match data snapshot versions are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS match_data_snapshot_lifecycle_no_update
            BEFORE UPDATE ON match_data_snapshot_lifecycle_events
            BEGIN
                SELECT RAISE(ABORT, 'Match data snapshot lifecycle is immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS match_data_snapshot_lifecycle_no_delete
            BEFORE DELETE ON match_data_snapshot_lifecycle_events
            BEGIN
                SELECT RAISE(ABORT, 'Match data snapshot lifecycle is immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS match_feature_sets_no_update
            BEFORE UPDATE ON match_feature_sets
            BEGIN
                SELECT RAISE(ABORT, 'Match feature sets are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS match_feature_sets_no_delete
            BEFORE DELETE ON match_feature_sets
            BEGIN
                SELECT RAISE(ABORT, 'Match feature sets are immutable');
            END
            """,
        ),
    ),
    Migration(
        version=16,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS model_input_vectors (
                model_input_id TEXT PRIMARY KEY,
                feature_set_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                schema_name TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                compatibility_version TEXT NOT NULL,
                feature_fingerprint TEXT NOT NULL,
                source_snapshot_fingerprint TEXT NOT NULL,
                source_feature_fingerprint TEXT NOT NULL,
                model_input_fingerprint TEXT NOT NULL UNIQUE,
                ordered_feature_names TEXT NOT NULL,
                ordered_feature_values TEXT NOT NULL,
                missingness_mask TEXT NOT NULL,
                missing_feature_names TEXT NOT NULL,
                feature_metadata TEXT NOT NULL,
                completeness_score TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (feature_set_id)
                    REFERENCES match_feature_sets(feature_set_id),
                UNIQUE (
                    feature_set_id, schema_name, schema_version,
                    compatibility_version
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_model_input_feature_set
            ON model_input_vectors (
                feature_set_id, schema_name, schema_version,
                compatibility_version
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_model_input_match
            ON model_input_vectors (
                match_id, created_timestamp, model_input_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_model_input_snapshot
            ON model_input_vectors (snapshot_id, model_input_id)
            """,
            """
            CREATE TRIGGER IF NOT EXISTS model_input_vectors_no_update
            BEFORE UPDATE ON model_input_vectors
            BEGIN
                SELECT RAISE(ABORT, 'Model input vectors are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS model_input_vectors_no_delete
            BEFORE DELETE ON model_input_vectors
            BEGIN
                SELECT RAISE(ABORT, 'Model input vectors are immutable');
            END
            """,
        ),
    ),
    Migration(
        version=17,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS prediction_inference_results (
                inference_id TEXT PRIMARY KEY,
                model_input_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                feature_set_id TEXT NOT NULL,
                model_artifact_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                model_version TEXT NOT NULL,
                model_family TEXT NOT NULL,
                input_schema_name TEXT NOT NULL,
                input_schema_version TEXT NOT NULL,
                compatibility_version TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                model_input_fingerprint TEXT NOT NULL,
                inference_fingerprint TEXT NOT NULL UNIQUE,
                ordered_raw_probability_snapshot TEXT NOT NULL,
                validation_snapshot TEXT NOT NULL,
                inference_timestamp TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (model_input_id)
                    REFERENCES model_input_vectors(model_input_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_prediction_inference_match
            ON prediction_inference_results (
                match_id, inference_timestamp, inference_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_prediction_inference_model_input
            ON prediction_inference_results (
                model_input_id, inference_timestamp, inference_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_prediction_inference_artifact
            ON prediction_inference_results (
                model_artifact_id, inference_timestamp, inference_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_prediction_inference_model_version
            ON prediction_inference_results (
                model_name, model_version, inference_timestamp, inference_id
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_prediction_inference_timestamp
            ON prediction_inference_results (inference_timestamp, inference_id)
            """,
            """
            CREATE TRIGGER IF NOT EXISTS prediction_inference_results_no_update
            BEFORE UPDATE ON prediction_inference_results
            BEGIN
                SELECT RAISE(ABORT, 'Prediction inference results are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS prediction_inference_results_no_delete
            BEFORE DELETE ON prediction_inference_results
            BEGIN
                SELECT RAISE(ABORT, 'Prediction inference results are immutable');
            END
            """,
        ),
    ),
    Migration(
        version=18,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS probability_calibration_sets (
                calibration_set_id TEXT PRIMARY KEY,
                set_name TEXT NOT NULL,
                set_version TEXT NOT NULL,
                source_model_artifact_id TEXT NOT NULL,
                source_model_versions TEXT NOT NULL,
                target_mapping_snapshot TEXT NOT NULL,
                calibration_set_fingerprint TEXT NOT NULL UNIQUE,
                policy_version TEXT NOT NULL,
                active INTEGER NOT NULL,
                effective_timestamp TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                CHECK (active IN (0, 1))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS calibrated_market_probability_assemblies (
                calibrated_assembly_id TEXT PRIMARY KEY,
                inference_id TEXT NOT NULL,
                model_input_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                feature_set_id TEXT NOT NULL,
                source_model_artifact_id TEXT NOT NULL,
                source_model_name TEXT NOT NULL,
                source_model_version TEXT NOT NULL,
                raw_inference_fingerprint TEXT NOT NULL,
                calibration_set_id TEXT,
                calibration_set_fingerprint TEXT NOT NULL,
                assembly_policy_version TEXT NOT NULL,
                calibrated_assembly_fingerprint TEXT NOT NULL UNIQUE,
                validation_snapshot TEXT NOT NULL,
                calibration_effective_timestamp TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (inference_id)
                    REFERENCES prediction_inference_results(inference_id),
                FOREIGN KEY (calibration_set_id)
                    REFERENCES probability_calibration_sets(calibration_set_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS calibrated_market_probability_targets (
                calibrated_target_result_id TEXT PRIMARY KEY,
                calibrated_assembly_id TEXT NOT NULL,
                target_order INTEGER NOT NULL,
                target TEXT NOT NULL,
                raw_probability TEXT NOT NULL,
                calibrated_probability TEXT NOT NULL,
                calibration_artifact_id TEXT NOT NULL,
                calibration_method TEXT NOT NULL,
                calibration_model_version TEXT NOT NULL,
                calibration_policy_version TEXT NOT NULL,
                calibration_report_fingerprint TEXT NOT NULL,
                quality_metadata_reference TEXT,
                clamping_indicator INTEGER,
                diagnostics_snapshot TEXT NOT NULL,
                target_result_fingerprint TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (calibrated_assembly_id)
                    REFERENCES calibrated_market_probability_assemblies(calibrated_assembly_id),
                UNIQUE (calibrated_assembly_id, target),
                UNIQUE (calibrated_assembly_id, target_order),
                CHECK (target_order >= 0),
                CHECK (clamping_indicator IS NULL OR clamping_indicator IN (0, 1))
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_calibration_set_model ON probability_calibration_sets (source_model_artifact_id, active, effective_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_calibrated_assembly_match ON calibrated_market_probability_assemblies (match_id, calibration_effective_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_calibrated_assembly_inference ON calibrated_market_probability_assemblies (inference_id, calibration_effective_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_calibrated_assembly_model ON calibrated_market_probability_assemblies (source_model_artifact_id, source_model_version, calibration_effective_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_calibrated_assembly_set ON calibrated_market_probability_assemblies (calibration_set_id, calibration_effective_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_calibrated_target_target ON calibrated_market_probability_targets (target, calibration_artifact_id)""",
            """
            CREATE TRIGGER IF NOT EXISTS probability_calibration_sets_no_update BEFORE UPDATE ON probability_calibration_sets
            BEGIN SELECT RAISE(ABORT, 'Probability calibration sets are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS probability_calibration_sets_no_delete BEFORE DELETE ON probability_calibration_sets
            BEGIN SELECT RAISE(ABORT, 'Probability calibration sets are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS calibrated_market_probability_assemblies_no_update BEFORE UPDATE ON calibrated_market_probability_assemblies
            BEGIN SELECT RAISE(ABORT, 'Calibrated market probability assemblies are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS calibrated_market_probability_assemblies_no_delete BEFORE DELETE ON calibrated_market_probability_assemblies
            BEGIN SELECT RAISE(ABORT, 'Calibrated market probability assemblies are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS calibrated_market_probability_targets_no_update BEFORE UPDATE ON calibrated_market_probability_targets
            BEGIN SELECT RAISE(ABORT, 'Calibrated market probability targets are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS calibrated_market_probability_targets_no_delete BEFORE DELETE ON calibrated_market_probability_targets
            BEGIN SELECT RAISE(ABORT, 'Calibrated market probability targets are immutable'); END
            """,
        ),
    ),
    Migration(
        version=19,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS market_odds_snapshots (
                odds_record_id TEXT PRIMARY KEY,
                supplied_snapshot_id TEXT NOT NULL,
                odds_fingerprint TEXT NOT NULL UNIQUE,
                source_provider TEXT NOT NULL,
                bookmaker_id TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                market_type TEXT NOT NULL,
                selection TEXT NOT NULL,
                market_line TEXT,
                original_market TEXT NOT NULL,
                original_selection TEXT NOT NULL,
                decimal_odds TEXT NOT NULL,
                odds_effective_timestamp TEXT NOT NULL,
                source_updated_timestamp TEXT NOT NULL,
                registration_timestamp TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                market_status TEXT NOT NULL,
                suspended INTEGER NOT NULL,
                available INTEGER NOT NULL,
                minimum_stake TEXT,
                maximum_stake TEXT,
                currency TEXT,
                source_data_version TEXT NOT NULL,
                metadata_version TEXT NOT NULL,
                deterministic_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                CHECK (suspended IN (0, 1)),
                CHECK (available IN (0, 1))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS market_value_assessments (
                value_assessment_id TEXT PRIMARY KEY,
                calibrated_assembly_id TEXT NOT NULL,
                inference_id TEXT NOT NULL,
                model_input_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                source_snapshot_id TEXT NOT NULL,
                feature_set_id TEXT NOT NULL,
                source_model_artifact_id TEXT NOT NULL,
                source_model_version TEXT NOT NULL,
                calibration_set_id TEXT,
                calibration_set_fingerprint TEXT NOT NULL,
                odds_record_id TEXT NOT NULL,
                odds_fingerprint TEXT NOT NULL,
                source_provider TEXT NOT NULL,
                bookmaker_id TEXT NOT NULL,
                market_type TEXT NOT NULL,
                selection TEXT NOT NULL,
                market_line TEXT,
                source_calibrated_targets TEXT NOT NULL,
                probability_derivation_type TEXT NOT NULL,
                derivation_version TEXT NOT NULL,
                fair_probability TEXT NOT NULL,
                fair_decimal_odds TEXT NOT NULL,
                bookmaker_decimal_odds TEXT NOT NULL,
                implied_probability TEXT NOT NULL,
                break_even_probability TEXT NOT NULL,
                absolute_probability_edge TEXT NOT NULL,
                relative_probability_edge TEXT NOT NULL,
                expected_value TEXT NOT NULL,
                expected_return TEXT NOT NULL,
                potential_profit TEXT NOT NULL,
                odds_age_seconds INTEGER NOT NULL,
                calibrated_age_seconds INTEGER NOT NULL,
                time_to_kickoff_seconds INTEGER NOT NULL,
                value_classification TEXT NOT NULL,
                odds_freshness TEXT NOT NULL,
                calibrated_freshness TEXT NOT NULL,
                overall_freshness TEXT NOT NULL,
                actionability_status TEXT NOT NULL,
                assessment_timestamp TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                value_policy_version TEXT NOT NULL,
                calibrated_assembly_fingerprint TEXT NOT NULL,
                assessment_fingerprint TEXT NOT NULL UNIQUE,
                reason_code_snapshot TEXT NOT NULL,
                validation_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (calibrated_assembly_id)
                    REFERENCES calibrated_market_probability_assemblies(calibrated_assembly_id),
                FOREIGN KEY (odds_record_id)
                    REFERENCES market_odds_snapshots(odds_record_id),
                CHECK (odds_age_seconds >= 0),
                CHECK (calibrated_age_seconds >= 0),
                CHECK (time_to_kickoff_seconds > 0)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_market_odds_match
                ON market_odds_snapshots (match_id, odds_effective_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_market_odds_bookmaker
                ON market_odds_snapshots (bookmaker_id, odds_effective_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_market_odds_identity
                ON market_odds_snapshots (market_type, selection, market_line, odds_effective_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_market_odds_effective
                ON market_odds_snapshots (odds_effective_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_market_value_match
                ON market_value_assessments (match_id, assessment_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_market_value_identity
                ON market_value_assessments (bookmaker_id, market_type, selection, market_line, assessment_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_market_value_assessed_at
                ON market_value_assessments (assessment_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_market_value_classification
                ON market_value_assessments (value_classification, assessment_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_market_value_actionability
                ON market_value_assessments (actionability_status, assessment_timestamp)""",
            """
            CREATE TRIGGER IF NOT EXISTS market_odds_snapshots_no_update
            BEFORE UPDATE ON market_odds_snapshots
            BEGIN SELECT RAISE(ABORT, 'Market odds snapshots are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS market_odds_snapshots_no_delete
            BEFORE DELETE ON market_odds_snapshots
            BEGIN SELECT RAISE(ABORT, 'Market odds snapshots are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS market_value_assessments_no_update
            BEFORE UPDATE ON market_value_assessments
            BEGIN SELECT RAISE(ABORT, 'Market value assessments are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS market_value_assessments_no_delete
            BEFORE DELETE ON market_value_assessments
            BEGIN SELECT RAISE(ABORT, 'Market value assessments are immutable'); END
            """,
        ),
    ),
    Migration(
        version=20,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS official_prediction_selection_decisions (
                selection_decision_id TEXT PRIMARY KEY,
                selection_request_identity TEXT NOT NULL UNIQUE,
                selection_request_fingerprint TEXT NOT NULL,
                match_id TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                selection_timestamp TEXT NOT NULL,
                final_outcome_status TEXT NOT NULL,
                selected_value_assessment_id TEXT,
                selected_assessment_fingerprint TEXT,
                selected_market_identity TEXT,
                selected_odds TEXT,
                selected_fair_probability TEXT,
                selected_expected_value TEXT,
                eligible_assessment_count INTEGER NOT NULL,
                rejected_assessment_count INTEGER NOT NULL,
                selection_policy_version TEXT NOT NULL,
                ranking_policy_version TEXT NOT NULL,
                decision_fingerprint TEXT NOT NULL UNIQUE,
                final_reason_code_snapshot TEXT NOT NULL,
                deterministic_decision_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (selected_value_assessment_id)
                    REFERENCES market_value_assessments(value_assessment_id),
                UNIQUE (selection_request_identity, selection_request_fingerprint),
                CHECK (final_outcome_status IN ('SELECTED', 'NO_SELECTION')),
                CHECK (eligible_assessment_count >= 0),
                CHECK (rejected_assessment_count >= 0),
                CHECK (
                    (final_outcome_status = 'SELECTED'
                     AND selected_value_assessment_id IS NOT NULL
                     AND selected_assessment_fingerprint IS NOT NULL
                     AND selected_market_identity IS NOT NULL
                     AND selected_odds IS NOT NULL
                     AND selected_fair_probability IS NOT NULL
                     AND selected_expected_value IS NOT NULL)
                    OR
                    (final_outcome_status = 'NO_SELECTION'
                     AND selected_value_assessment_id IS NULL
                     AND selected_assessment_fingerprint IS NULL
                     AND selected_market_identity IS NULL
                     AND selected_odds IS NULL
                     AND selected_fair_probability IS NULL
                     AND selected_expected_value IS NULL)
                )
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS official_prediction_selection_evaluations (
                evaluation_id TEXT PRIMARY KEY,
                selection_decision_id TEXT NOT NULL,
                value_assessment_id TEXT NOT NULL,
                assessment_fingerprint TEXT NOT NULL,
                deterministic_input_order INTEGER NOT NULL,
                eligibility_status TEXT NOT NULL,
                logical_market_identity TEXT NOT NULL,
                verified_odds TEXT NOT NULL,
                verified_fair_probability TEXT NOT NULL,
                verified_expected_value TEXT NOT NULL,
                freshness_snapshot TEXT NOT NULL,
                ordered_rejection_reasons TEXT NOT NULL,
                evaluation_fingerprint TEXT NOT NULL,
                deterministic_evaluation_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (selection_decision_id)
                    REFERENCES official_prediction_selection_decisions(selection_decision_id),
                FOREIGN KEY (value_assessment_id)
                    REFERENCES market_value_assessments(value_assessment_id),
                UNIQUE (selection_decision_id, value_assessment_id),
                UNIQUE (selection_decision_id, deterministic_input_order),
                UNIQUE (selection_decision_id, evaluation_fingerprint),
                CHECK (deterministic_input_order >= 0),
                CHECK (eligibility_status IN ('ELIGIBLE', 'REJECTED', 'DEDUPLICATED'))
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_official_selection_match
                ON official_prediction_selection_decisions (match_id, selection_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_official_selection_timestamp
                ON official_prediction_selection_decisions (selection_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_official_selection_selected_assessment
                ON official_prediction_selection_decisions (selected_value_assessment_id)""",
            """CREATE INDEX IF NOT EXISTS idx_official_selection_status
                ON official_prediction_selection_decisions (final_outcome_status, selection_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_official_selection_market
                ON official_prediction_selection_decisions (selected_market_identity, selection_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_official_selection_policy
                ON official_prediction_selection_decisions (selection_policy_version, ranking_policy_version)""",
            """
            CREATE TRIGGER IF NOT EXISTS official_selection_decisions_no_update
            BEFORE UPDATE ON official_prediction_selection_decisions
            BEGIN SELECT RAISE(ABORT, 'Official selection decisions are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_selection_decisions_no_delete
            BEFORE DELETE ON official_prediction_selection_decisions
            BEGIN SELECT RAISE(ABORT, 'Official selection decisions are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_selection_evaluations_no_update
            BEFORE UPDATE ON official_prediction_selection_evaluations
            BEGIN SELECT RAISE(ABORT, 'Official selection evaluations are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_selection_evaluations_no_delete
            BEFORE DELETE ON official_prediction_selection_evaluations
            BEGIN SELECT RAISE(ABORT, 'Official selection evaluations are immutable'); END
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
