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
    Migration(
        version=21,
        statements=(
            """ALTER TABLE official_prediction_candidate_versions
                ADD COLUMN provenance_snapshot TEXT NOT NULL DEFAULT '[]'""",
            """
            CREATE TABLE IF NOT EXISTS official_candidate_preparation_executions (
                integration_execution_id TEXT PRIMARY KEY,
                integration_request_identity TEXT NOT NULL UNIQUE,
                preparation_request_fingerprint TEXT NOT NULL UNIQUE,
                integration_fingerprint TEXT NOT NULL UNIQUE,
                selection_decision_id TEXT NOT NULL,
                selected_value_assessment_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                risk_assessment_timestamp TEXT NOT NULL,
                candidate_preparation_timestamp TEXT NOT NULL,
                bankroll_snapshot_identity TEXT NOT NULL,
                bankroll_fingerprint TEXT NOT NULL,
                exposure_snapshot_identity TEXT NOT NULL,
                exposure_fingerprint TEXT NOT NULL,
                risk_handoff_fingerprint TEXT,
                risk_outcome TEXT,
                risk_assessment_id TEXT,
                risk_fingerprint TEXT,
                candidate_mapping_fingerprint TEXT,
                candidate_registry_outcome TEXT,
                registry_candidate_id TEXT,
                candidate_version INTEGER,
                candidate_fingerprint TEXT,
                previous_candidate_id TEXT,
                final_status TEXT NOT NULL,
                integration_policy_version TEXT NOT NULL,
                ordered_reason_code_snapshot TEXT NOT NULL,
                explanation_snapshot TEXT NOT NULL,
                deterministic_execution_summary TEXT NOT NULL,
                deterministic_execution_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (selection_decision_id)
                    REFERENCES official_prediction_selection_decisions(selection_decision_id),
                FOREIGN KEY (selected_value_assessment_id)
                    REFERENCES market_value_assessments(value_assessment_id),
                FOREIGN KEY (registry_candidate_id)
                    REFERENCES official_prediction_candidate_versions(registry_candidate_id),
                FOREIGN KEY (previous_candidate_id)
                    REFERENCES official_prediction_candidate_versions(registry_candidate_id),
                CHECK (risk_outcome IS NULL OR risk_outcome IN (
                    'ELIGIBLE', 'REDUCED_STAKE', 'REVIEW_REQUIRED', 'INELIGIBLE'
                )),
                CHECK (candidate_version IS NULL OR candidate_version > 0),
                CHECK (final_status IN (
                    'CANDIDATE_REGISTERED', 'IDEMPOTENT_EXISTING',
                    'NO_REGISTRATION_INELIGIBLE',
                    'NO_REGISTRATION_REVIEW_REQUIRED',
                    'REJECTED_INVALID_REQUEST', 'REJECTED_PROVENANCE',
                    'REJECTED_SCOPE', 'REJECTED_INVALID_RISK_RESULT',
                    'RISK_EXECUTION_FAILED', 'CANDIDATE_REGISTRATION_REJECTED',
                    'ALREADY_PUBLISHED', 'CORRECTION_REQUIRED', 'CONFLICT',
                    'PERSISTENCE_FAILURE'
                ))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS official_candidate_preparation_risk_snapshots (
                risk_snapshot_id TEXT PRIMARY KEY,
                integration_execution_id TEXT NOT NULL UNIQUE,
                risk_assessment_id TEXT NOT NULL,
                risk_handoff_fingerprint TEXT NOT NULL,
                risk_fingerprint TEXT NOT NULL,
                risk_outcome TEXT NOT NULL,
                risk_policy_version TEXT NOT NULL,
                stake_amount TEXT,
                stake_currency TEXT,
                internal_stake_percentage TEXT,
                bankroll_amount_used TEXT NOT NULL,
                available_bankroll TEXT NOT NULL,
                bankroll_snapshot_identity TEXT NOT NULL,
                bankroll_fingerprint TEXT NOT NULL,
                exposure_snapshot_identity TEXT NOT NULL,
                exposure_fingerprint TEXT NOT NULL,
                exposure_summary TEXT NOT NULL,
                ordered_reason_code_snapshot TEXT NOT NULL,
                deterministic_risk_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (integration_execution_id)
                    REFERENCES official_candidate_preparation_executions(integration_execution_id),
                UNIQUE (integration_execution_id, risk_assessment_id),
                CHECK (risk_outcome IN (
                    'ELIGIBLE', 'REDUCED_STAKE', 'REVIEW_REQUIRED', 'INELIGIBLE'
                ))
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_candidate_preparation_match
                ON official_candidate_preparation_executions
                (match_id, candidate_preparation_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_candidate_preparation_selection
                ON official_candidate_preparation_executions
                (selection_decision_id, candidate_preparation_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_candidate_preparation_risk_outcome
                ON official_candidate_preparation_executions
                (risk_outcome, candidate_preparation_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_candidate_preparation_final_status
                ON official_candidate_preparation_executions
                (final_status, candidate_preparation_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_candidate_preparation_candidate
                ON official_candidate_preparation_executions
                (registry_candidate_id, candidate_preparation_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_candidate_preparation_timestamp
                ON official_candidate_preparation_executions
                (candidate_preparation_timestamp)""",
            """
            CREATE TRIGGER IF NOT EXISTS candidate_preparation_executions_no_update
            BEFORE UPDATE ON official_candidate_preparation_executions
            BEGIN SELECT RAISE(ABORT, 'Candidate preparation executions are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS candidate_preparation_executions_no_delete
            BEFORE DELETE ON official_candidate_preparation_executions
            BEGIN SELECT RAISE(ABORT, 'Candidate preparation executions are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS candidate_preparation_risk_no_update
            BEFORE UPDATE ON official_candidate_preparation_risk_snapshots
            BEGIN SELECT RAISE(ABORT, 'Candidate preparation risk snapshots are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS candidate_preparation_risk_no_delete
            BEFORE DELETE ON official_candidate_preparation_risk_snapshots
            BEGIN SELECT RAISE(ABORT, 'Candidate preparation risk snapshots are immutable'); END
            """,
        ),
    ),
    Migration(
        version=22,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS official_prediction_pipeline_executions (
                pipeline_execution_id TEXT PRIMARY KEY,
                pipeline_request_identity TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL,
                pipeline_fingerprint TEXT NOT NULL UNIQUE,
                manual_run_identity TEXT,
                candidate_id TEXT NOT NULL,
                candidate_version INTEGER NOT NULL,
                candidate_fingerprint TEXT NOT NULL,
                match_id TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                quality_gate_evaluation_timestamp TEXT NOT NULL,
                pipeline_execution_timestamp TEXT NOT NULL,
                publication_effective_timestamp TEXT,
                dry_run INTEGER NOT NULL,
                retry INTEGER NOT NULL,
                candidate_state_result TEXT,
                publication_state_result TEXT,
                quality_gate_evaluation_id TEXT,
                quality_gate_status TEXT,
                quality_gate_fingerprint TEXT,
                orchestration_id TEXT,
                orchestration_status TEXT,
                orchestration_fingerprint TEXT,
                publication_event_id TEXT,
                publication_status TEXT,
                publication_fingerprint TEXT,
                publication_claim_identity TEXT,
                message_fingerprint TEXT,
                telegram_message_reference TEXT,
                final_pipeline_status TEXT NOT NULL,
                pipeline_policy_version TEXT NOT NULL,
                ordered_reason_code_snapshot TEXT NOT NULL,
                explanation_snapshot TEXT NOT NULL,
                deterministic_execution_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (candidate_id)
                    REFERENCES official_prediction_candidate_versions(registry_candidate_id),
                FOREIGN KEY (quality_gate_evaluation_id)
                    REFERENCES official_quality_gate_evaluations(evaluation_id),
                FOREIGN KEY (orchestration_id)
                    REFERENCES official_prediction_orchestrations(orchestration_id),
                FOREIGN KEY (publication_event_id)
                    REFERENCES official_prediction_publication_events(event_id),
                UNIQUE (pipeline_request_identity, request_fingerprint),
                CHECK (candidate_version > 0),
                CHECK (dry_run IN (0, 1)),
                CHECK (retry IN (0, 1)),
                CHECK (final_pipeline_status IN (
                    'PUBLISHED', 'IDEMPOTENT_EXISTING', 'DRY_RUN_COMPLETED',
                    'NO_PUBLICATION_QUALITY_GATE_REJECTED',
                    'NO_PUBLICATION_REVIEW_REQUIRED', 'PUBLICATION_IN_PROGRESS',
                    'RETRY_REQUIRED', 'REJECTED_INVALID_REQUEST',
                    'REJECTED_CANDIDATE_STATE', 'REJECTED_PROVENANCE',
                    'REJECTED_SCOPE', 'REJECTED_INVALID_GATE_RESULT',
                    'QUALITY_GATE_EXECUTION_FAILED', 'ORCHESTRATION_REJECTED',
                    'ORCHESTRATION_FAILED', 'PUBLICATION_CLAIM_FAILED',
                    'PUBLICATION_SEND_FAILED', 'PUBLICATION_FINALIZATION_FAILED',
                    'ALREADY_PUBLISHED_CONFLICT', 'CONFLICT', 'PERSISTENCE_FAILURE'
                )),
                CHECK (final_pipeline_status <> 'PUBLISHED' OR
                    (publication_event_id IS NOT NULL AND publication_status = 'PUBLISHED'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS official_prediction_pipeline_stage_events (
                stage_event_id TEXT PRIMARY KEY,
                pipeline_execution_id TEXT NOT NULL,
                stage_order INTEGER NOT NULL,
                stage_name TEXT NOT NULL,
                stage_status TEXT NOT NULL,
                referenced_domain_record_id TEXT,
                referenced_fingerprint TEXT,
                ordered_reason_codes TEXT NOT NULL,
                deterministic_stage_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (pipeline_execution_id)
                    REFERENCES official_prediction_pipeline_executions(pipeline_execution_id),
                UNIQUE (pipeline_execution_id, stage_order),
                CHECK (stage_order BETWEEN 1 AND 9),
                CHECK (stage_name IN (
                    'REQUEST_VALIDATION', 'CANDIDATE_STATE_VERIFICATION',
                    'PUBLICATION_STATE_VERIFICATION', 'QUALITY_GATE',
                    'ORCHESTRATION', 'MESSAGE_ASSEMBLY', 'PUBLICATION_CLAIM',
                    'TELEGRAM_SEND', 'PUBLICATION_FINALIZATION'
                ))
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_official_pipeline_candidate
                ON official_prediction_pipeline_executions (candidate_id, pipeline_execution_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_official_pipeline_match
                ON official_prediction_pipeline_executions (match_id, pipeline_execution_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_official_pipeline_status
                ON official_prediction_pipeline_executions (final_pipeline_status, pipeline_execution_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_official_pipeline_gate
                ON official_prediction_pipeline_executions (quality_gate_status, pipeline_execution_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_official_pipeline_orchestration
                ON official_prediction_pipeline_executions (orchestration_status, pipeline_execution_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_official_pipeline_publication
                ON official_prediction_pipeline_executions (publication_status, pipeline_execution_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_official_pipeline_manual_run
                ON official_prediction_pipeline_executions (manual_run_identity, pipeline_execution_timestamp)""",
            """
            CREATE TRIGGER IF NOT EXISTS official_pipeline_executions_no_update
            BEFORE UPDATE ON official_prediction_pipeline_executions
            BEGIN SELECT RAISE(ABORT, 'Official pipeline executions are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_pipeline_executions_no_delete
            BEFORE DELETE ON official_prediction_pipeline_executions
            BEGIN SELECT RAISE(ABORT, 'Official pipeline executions are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_pipeline_stage_events_no_update
            BEFORE UPDATE ON official_prediction_pipeline_stage_events
            BEGIN SELECT RAISE(ABORT, 'Official pipeline stage events are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS official_pipeline_stage_events_no_delete
            BEFORE DELETE ON official_prediction_pipeline_stage_events
            BEGIN SELECT RAISE(ABORT, 'Official pipeline stage events are immutable'); END
            """,
        ),
    ),
    Migration(
        version=23,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS historical_match_imports (
                import_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                provider_identity TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                dataset_version TEXT NOT NULL,
                dataset_schema_version TEXT NOT NULL,
                dataset_fingerprint TEXT NOT NULL UNIQUE,
                dataset_content_fingerprint TEXT NOT NULL,
                supplied_match_count INTEGER NOT NULL,
                inserted_match_count INTEGER NOT NULL,
                reused_match_count INTEGER NOT NULL,
                match_fingerprint_snapshot TEXT NOT NULL,
                import_timestamp TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                metadata_version TEXT NOT NULL,
                deterministic_import_snapshot TEXT NOT NULL,
                UNIQUE (provider_identity, dataset_id, dataset_version),
                CHECK (supplied_match_count > 0),
                CHECK (inserted_match_count >= 0),
                CHECK (reused_match_count >= 0),
                CHECK (inserted_match_count + reused_match_count = supplied_match_count),
                CHECK (dataset_schema_version = 'goalvision_historical_dataset_v1'),
                CHECK (metadata_version = 'v1'),
                CHECK (substr(import_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_matches (
                historical_match_id TEXT PRIMARY KEY,
                import_id TEXT NOT NULL,
                logical_identity_fingerprint TEXT NOT NULL,
                natural_identity_fingerprint TEXT NOT NULL,
                match_fingerprint TEXT NOT NULL UNIQUE,
                match_version INTEGER NOT NULL,
                source_provider TEXT NOT NULL,
                source_match_id TEXT NOT NULL,
                competition TEXT NOT NULL,
                competition_identity TEXT NOT NULL,
                season TEXT NOT NULL,
                competition_round TEXT NOT NULL,
                kickoff_utc TEXT NOT NULL,
                home_team TEXT NOT NULL,
                home_team_identity TEXT NOT NULL,
                away_team TEXT NOT NULL,
                away_team_identity TEXT NOT NULL,
                full_time_home_score INTEGER NOT NULL,
                full_time_away_score INTEGER NOT NULL,
                half_time_home_score INTEGER,
                half_time_away_score INTEGER,
                full_time_result TEXT NOT NULL,
                venue TEXT NOT NULL,
                referee TEXT,
                attendance INTEGER,
                normalized_match_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (import_id) REFERENCES historical_match_imports(import_id),
                UNIQUE (logical_identity_fingerprint, match_version),
                CHECK (match_version > 0),
                CHECK (full_time_home_score BETWEEN 0 AND 30),
                CHECK (full_time_away_score BETWEEN 0 AND 30),
                CHECK (half_time_home_score IS NULL OR half_time_home_score BETWEEN 0 AND full_time_home_score),
                CHECK (half_time_away_score IS NULL OR half_time_away_score BETWEEN 0 AND full_time_away_score),
                CHECK ((half_time_home_score IS NULL) = (half_time_away_score IS NULL)),
                CHECK (full_time_result IN ('HOME_WIN', 'DRAW', 'AWAY_WIN')),
                CHECK (home_team_identity <> away_team_identity),
                CHECK (attendance IS NULL OR attendance >= 0),
                CHECK (substr(kickoff_utc, -1) = 'Z'),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_match_statistics (
                statistics_id TEXT PRIMARY KEY,
                historical_match_id TEXT NOT NULL,
                team_side TEXT NOT NULL,
                possession TEXT,
                shots INTEGER,
                shots_on_target INTEGER,
                expected_goals TEXT,
                corners INTEGER,
                yellow_cards INTEGER,
                red_cards INTEGER,
                fouls INTEGER,
                offsides INTEGER,
                statistics_fingerprint TEXT NOT NULL UNIQUE,
                normalized_statistics_snapshot TEXT NOT NULL,
                FOREIGN KEY (historical_match_id) REFERENCES historical_matches(historical_match_id),
                UNIQUE (historical_match_id, team_side),
                CHECK (team_side IN ('HOME', 'AWAY')),
                CHECK (possession IS NULL OR CAST(possession AS REAL) BETWEEN 0 AND 100),
                CHECK (shots IS NULL OR shots BETWEEN 0 AND 200),
                CHECK (shots_on_target IS NULL OR shots_on_target BETWEEN 0 AND 100),
                CHECK (shots IS NULL OR shots_on_target IS NULL OR shots_on_target <= shots),
                CHECK (expected_goals IS NULL OR CAST(expected_goals AS REAL) BETWEEN 0 AND 20),
                CHECK (corners IS NULL OR corners BETWEEN 0 AND 50),
                CHECK (yellow_cards IS NULL OR yellow_cards BETWEEN 0 AND 20),
                CHECK (red_cards IS NULL OR red_cards BETWEEN 0 AND 5),
                CHECK (fouls IS NULL OR fouls BETWEEN 0 AND 100),
                CHECK (offsides IS NULL OR offsides BETWEEN 0 AND 30)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_lineups (
                lineup_id TEXT PRIMARY KEY,
                historical_match_id TEXT NOT NULL,
                team_side TEXT NOT NULL,
                formation TEXT,
                starting_xi_snapshot TEXT NOT NULL,
                substitutes_snapshot TEXT NOT NULL,
                starting_xi_count INTEGER NOT NULL,
                substitute_count INTEGER NOT NULL,
                lineup_fingerprint TEXT NOT NULL UNIQUE,
                normalized_lineup_snapshot TEXT NOT NULL,
                FOREIGN KEY (historical_match_id) REFERENCES historical_matches(historical_match_id),
                UNIQUE (historical_match_id, team_side),
                CHECK (team_side IN ('HOME', 'AWAY')),
                CHECK (starting_xi_count = 11),
                CHECK (substitute_count BETWEEN 0 AND 20)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_historical_import_dataset
                ON historical_match_imports (provider_identity, dataset_id, dataset_version)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_match_kickoff
                ON historical_matches (kickoff_utc, historical_match_id)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_match_competition
                ON historical_matches (competition_identity, season, kickoff_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_match_home_team
                ON historical_matches (home_team_identity, kickoff_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_match_away_team
                ON historical_matches (away_team_identity, kickoff_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_match_logical_identity
                ON historical_matches (logical_identity_fingerprint, match_version)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_match_natural_identity
                ON historical_matches (natural_identity_fingerprint, match_version)""",
            """
            CREATE TRIGGER IF NOT EXISTS historical_match_imports_no_update
            BEFORE UPDATE ON historical_match_imports
            BEGIN SELECT RAISE(ABORT, 'Historical match imports are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_match_imports_no_delete
            BEFORE DELETE ON historical_match_imports
            BEGIN SELECT RAISE(ABORT, 'Historical match imports are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_matches_no_update
            BEFORE UPDATE ON historical_matches
            BEGIN SELECT RAISE(ABORT, 'Historical matches are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_matches_no_delete
            BEFORE DELETE ON historical_matches
            BEGIN SELECT RAISE(ABORT, 'Historical matches are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_match_statistics_no_update
            BEFORE UPDATE ON historical_match_statistics
            BEGIN SELECT RAISE(ABORT, 'Historical match statistics are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_match_statistics_no_delete
            BEFORE DELETE ON historical_match_statistics
            BEGIN SELECT RAISE(ABORT, 'Historical match statistics are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_lineups_no_update
            BEFORE UPDATE ON historical_lineups
            BEGIN SELECT RAISE(ABORT, 'Historical lineups are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_lineups_no_delete
            BEFORE DELETE ON historical_lineups
            BEGIN SELECT RAISE(ABORT, 'Historical lineups are immutable'); END
            """,
        ),
    ),
    Migration(
        version=24,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS historical_training_dataset_builds (
                dataset_build_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL,
                dataset_fingerprint TEXT NOT NULL UNIQUE,
                dataset_name TEXT NOT NULL,
                source_import_ids_snapshot TEXT NOT NULL,
                filters_snapshot TEXT NOT NULL,
                cutoff_policy TEXT NOT NULL,
                feature_schema_version TEXT NOT NULL,
                label_schema_version TEXT NOT NULL,
                dataset_policy_version TEXT NOT NULL,
                source_match_count INTEGER NOT NULL,
                included_count INTEGER NOT NULL,
                excluded_insufficient_history_count INTEGER NOT NULL,
                excluded_invalid_provenance_count INTEGER NOT NULL,
                deterministic_build_snapshot TEXT NOT NULL,
                build_timestamp TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                UNIQUE (request_id, request_fingerprint),
                CHECK (cutoff_policy = 'STRICTLY_BEFORE_KICKOFF'),
                CHECK (source_match_count >= 0),
                CHECK (included_count >= 0),
                CHECK (excluded_insufficient_history_count >= 0),
                CHECK (excluded_invalid_provenance_count >= 0),
                CHECK (substr(build_timestamp, -1) = 'Z'),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_training_examples (
                training_example_id TEXT PRIMARY KEY,
                dataset_build_id TEXT NOT NULL,
                historical_match_id TEXT NOT NULL,
                historical_match_fingerprint TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                competition TEXT NOT NULL,
                season TEXT NOT NULL,
                home_team_id TEXT NOT NULL,
                away_team_id TEXT NOT NULL,
                ordered_feature_vector TEXT NOT NULL,
                missingness_mask TEXT NOT NULL,
                completeness_score TEXT NOT NULL,
                feature_provenance_snapshot TEXT NOT NULL,
                lookback_window_identity TEXT NOT NULL,
                cutoff_timestamp TEXT NOT NULL,
                historical_source_fingerprints_snapshot TEXT NOT NULL,
                labels_snapshot TEXT NOT NULL,
                feature_schema_version TEXT NOT NULL,
                label_schema_version TEXT NOT NULL,
                dataset_policy_version TEXT NOT NULL,
                example_fingerprint TEXT NOT NULL UNIQUE,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (dataset_build_id)
                    REFERENCES historical_training_dataset_builds(dataset_build_id),
                FOREIGN KEY (historical_match_id)
                    REFERENCES historical_matches(historical_match_id),
                UNIQUE (dataset_build_id, historical_match_id),
                CHECK (home_team_id <> away_team_id),
                CHECK (CAST(completeness_score AS REAL) BETWEEN 0 AND 1),
                CHECK (substr(kickoff_timestamp, -1) = 'Z'),
                CHECK (cutoff_timestamp = kickoff_timestamp),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_training_example_sources (
                source_row_id TEXT PRIMARY KEY,
                training_example_id TEXT NOT NULL,
                source_historical_match_id TEXT NOT NULL,
                source_match_fingerprint TEXT NOT NULL,
                source_kickoff TEXT NOT NULL,
                source_role TEXT NOT NULL,
                deterministic_order_index INTEGER NOT NULL,
                lookback_window_identity TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (training_example_id)
                    REFERENCES historical_training_examples(training_example_id),
                FOREIGN KEY (source_historical_match_id)
                    REFERENCES historical_matches(historical_match_id),
                UNIQUE (training_example_id, deterministic_order_index),
                UNIQUE (training_example_id, source_historical_match_id),
                CHECK (deterministic_order_index >= 0),
                CHECK (substr(source_kickoff, -1) = 'Z'),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_training_exclusions (
                exclusion_id TEXT PRIMARY KEY,
                dataset_build_id TEXT NOT NULL,
                historical_match_id TEXT NOT NULL,
                exclusion_reason TEXT NOT NULL,
                deterministic_detail_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (dataset_build_id)
                    REFERENCES historical_training_dataset_builds(dataset_build_id),
                FOREIGN KEY (historical_match_id)
                    REFERENCES historical_matches(historical_match_id),
                UNIQUE (dataset_build_id, historical_match_id),
                CHECK (exclusion_reason IN (
                    'EXCLUDED_INSUFFICIENT_HISTORY',
                    'EXCLUDED_INVALID_PROVENANCE'
                )),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_historical_training_build_name
                ON historical_training_dataset_builds (dataset_name, build_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_training_example_dataset
                ON historical_training_examples (dataset_build_id, kickoff_timestamp, competition, historical_match_id)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_training_example_match
                ON historical_training_examples (historical_match_id, dataset_build_id)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_training_example_competition
                ON historical_training_examples (competition, season, kickoff_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_training_source_example
                ON historical_training_example_sources (training_example_id, deterministic_order_index)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_training_source_match
                ON historical_training_example_sources (source_historical_match_id, source_kickoff)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_training_exclusion_dataset
                ON historical_training_exclusions (dataset_build_id, exclusion_reason, historical_match_id)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_training_exclusion_reason
                ON historical_training_exclusions (exclusion_reason, dataset_build_id)""",
            """
            CREATE TRIGGER IF NOT EXISTS historical_training_dataset_builds_no_update
            BEFORE UPDATE ON historical_training_dataset_builds
            BEGIN SELECT RAISE(ABORT, 'Historical training dataset builds are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_training_dataset_builds_no_delete
            BEFORE DELETE ON historical_training_dataset_builds
            BEGIN SELECT RAISE(ABORT, 'Historical training dataset builds are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_training_examples_no_update
            BEFORE UPDATE ON historical_training_examples
            BEGIN SELECT RAISE(ABORT, 'Historical training examples are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_training_examples_no_delete
            BEFORE DELETE ON historical_training_examples
            BEGIN SELECT RAISE(ABORT, 'Historical training examples are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_training_example_sources_no_update
            BEFORE UPDATE ON historical_training_example_sources
            BEGIN SELECT RAISE(ABORT, 'Historical training example sources are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_training_example_sources_no_delete
            BEFORE DELETE ON historical_training_example_sources
            BEGIN SELECT RAISE(ABORT, 'Historical training example sources are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_training_exclusions_no_update
            BEFORE UPDATE ON historical_training_exclusions
            BEGIN SELECT RAISE(ABORT, 'Historical training exclusions are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_training_exclusions_no_delete
            BEFORE DELETE ON historical_training_exclusions
            BEGIN SELECT RAISE(ABORT, 'Historical training exclusions are immutable'); END
            """,
        ),
    ),
    Migration(
        version=25,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS historical_dataset_splits (
                split_id TEXT PRIMARY KEY,
                split_request_id TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL,
                split_fingerprint TEXT NOT NULL UNIQUE,
                split_name TEXT NOT NULL,
                source_dataset_build_id TEXT NOT NULL,
                source_dataset_fingerprint TEXT NOT NULL,
                split_strategy TEXT NOT NULL,
                split_policy_version TEXT NOT NULL,
                feature_schema_version TEXT NOT NULL,
                label_schema_version TEXT NOT NULL,
                filter_snapshot TEXT NOT NULL,
                boundary_ratio_snapshot TEXT NOT NULL,
                gap_snapshot TEXT NOT NULL,
                minimum_size_snapshot TEXT NOT NULL,
                fold_count INTEGER NOT NULL,
                aggregate_counts TEXT NOT NULL,
                deterministic_split_snapshot TEXT NOT NULL,
                split_timestamp TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (source_dataset_build_id)
                    REFERENCES historical_training_dataset_builds(dataset_build_id),
                UNIQUE (split_request_id, request_fingerprint),
                CHECK (split_strategy IN (
                    'EXPLICIT_TIME_BOUNDARIES_V1',
                    'EXPANDING_WINDOW_V1',
                    'RATIO_BY_CHRONOLOGY_V1'
                )),
                CHECK (fold_count >= 0),
                CHECK (substr(split_timestamp, -1) = 'Z'),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_dataset_split_folds (
                fold_id TEXT PRIMARY KEY,
                split_id TEXT NOT NULL,
                fold_index INTEGER NOT NULL,
                fold_fingerprint TEXT NOT NULL UNIQUE,
                train_boundary_snapshot TEXT NOT NULL,
                validation_boundary_snapshot TEXT NOT NULL,
                test_boundary_snapshot TEXT NOT NULL,
                achieved_counts TEXT NOT NULL,
                achieved_ratios TEXT NOT NULL,
                earliest_latest_kickoffs_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (split_id) REFERENCES historical_dataset_splits(split_id),
                UNIQUE (split_id, fold_index),
                CHECK (fold_index >= 0),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_dataset_split_assignments (
                assignment_id TEXT PRIMARY KEY,
                split_id TEXT NOT NULL,
                fold_id TEXT NOT NULL,
                training_example_id TEXT NOT NULL,
                historical_match_id TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                competition TEXT NOT NULL,
                season TEXT NOT NULL,
                partition TEXT NOT NULL,
                assignment_order INTEGER NOT NULL,
                example_fingerprint TEXT NOT NULL,
                assignment_fingerprint TEXT NOT NULL UNIQUE,
                exclusion_reason TEXT,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (split_id) REFERENCES historical_dataset_splits(split_id),
                FOREIGN KEY (fold_id) REFERENCES historical_dataset_split_folds(fold_id),
                FOREIGN KEY (training_example_id) REFERENCES historical_training_examples(training_example_id),
                FOREIGN KEY (historical_match_id) REFERENCES historical_matches(historical_match_id),
                UNIQUE (fold_id, training_example_id),
                UNIQUE (fold_id, assignment_order),
                CHECK (partition IN (
                    'TRAIN', 'VALIDATION', 'TEST', 'EXCLUDED_GAP',
                    'EXCLUDED_FILTER', 'EXCLUDED_BOUNDARY_GROUP',
                    'EXCLUDED_INVALID_PROVENANCE'
                )),
                CHECK (assignment_order >= 0),
                CHECK (
                    (partition IN ('TRAIN', 'VALIDATION', 'TEST') AND exclusion_reason IS NULL)
                    OR
                    (partition NOT IN ('TRAIN', 'VALIDATION', 'TEST') AND exclusion_reason IS NOT NULL)
                ),
                CHECK (substr(kickoff_timestamp, -1) = 'Z'),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_historical_dataset_split_source
                ON historical_dataset_splits (source_dataset_build_id, split_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_dataset_split_strategy
                ON historical_dataset_splits (split_strategy, split_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_dataset_split_fold
                ON historical_dataset_split_folds (split_id, fold_index)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_dataset_assignment_partition
                ON historical_dataset_split_assignments (fold_id, partition, assignment_order)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_dataset_assignment_competition
                ON historical_dataset_split_assignments (competition, season, kickoff_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_dataset_assignment_kickoff
                ON historical_dataset_split_assignments (kickoff_timestamp, fold_id)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_dataset_assignment_example
                ON historical_dataset_split_assignments (training_example_id, split_id)""",
            """
            CREATE TRIGGER IF NOT EXISTS historical_dataset_splits_no_update
            BEFORE UPDATE ON historical_dataset_splits
            BEGIN SELECT RAISE(ABORT, 'Historical dataset splits are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_dataset_splits_no_delete
            BEFORE DELETE ON historical_dataset_splits
            BEGIN SELECT RAISE(ABORT, 'Historical dataset splits are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_dataset_split_folds_no_update
            BEFORE UPDATE ON historical_dataset_split_folds
            BEGIN SELECT RAISE(ABORT, 'Historical dataset split folds are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_dataset_split_folds_no_delete
            BEFORE DELETE ON historical_dataset_split_folds
            BEGIN SELECT RAISE(ABORT, 'Historical dataset split folds are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_dataset_split_assignments_no_update
            BEFORE UPDATE ON historical_dataset_split_assignments
            BEGIN SELECT RAISE(ABORT, 'Historical dataset split assignments are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_dataset_split_assignments_no_delete
            BEFORE DELETE ON historical_dataset_split_assignments
            BEGIN SELECT RAISE(ABORT, 'Historical dataset split assignments are immutable'); END
            """,
        ),
    ),
    Migration(
        version=26,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS historical_model_training_runs (
                training_run_id TEXT PRIMARY KEY,
                training_request_id TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL,
                training_run_fingerprint TEXT NOT NULL UNIQUE,
                source_split_id TEXT NOT NULL,
                source_split_fingerprint TEXT NOT NULL,
                fold_id TEXT NOT NULL,
                fold_fingerprint TEXT NOT NULL,
                model_family TEXT NOT NULL,
                policy_versions_snapshot TEXT NOT NULL,
                feature_schema_version TEXT NOT NULL,
                feature_schema_fingerprint TEXT NOT NULL,
                label_schema_version TEXT NOT NULL,
                target_schema_version TEXT NOT NULL,
                training_row_count INTEGER NOT NULL,
                validation_row_count INTEGER NOT NULL,
                target_count INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                reason_codes_snapshot TEXT NOT NULL,
                aggregate_metrics_snapshot TEXT NOT NULL,
                deterministic_run_snapshot TEXT NOT NULL,
                training_timestamp TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (source_split_id) REFERENCES historical_dataset_splits(split_id),
                FOREIGN KEY (fold_id) REFERENCES historical_dataset_split_folds(fold_id),
                UNIQUE (training_request_id, request_fingerprint),
                CHECK (training_row_count >= 0),
                CHECK (validation_row_count >= 0),
                CHECK (target_count = 11),
                CHECK (substr(training_timestamp, -1) = 'Z'),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_model_artifacts (
                artifact_id TEXT PRIMARY KEY,
                training_run_id TEXT NOT NULL UNIQUE,
                artifact_fingerprint TEXT NOT NULL UNIQUE,
                artifact_format_version TEXT NOT NULL,
                preprocessing_fingerprint TEXT NOT NULL,
                estimator_bundle_fingerprint TEXT NOT NULL,
                compatibility_snapshot TEXT NOT NULL,
                preprocessing_snapshot TEXT NOT NULL,
                estimator_snapshot TEXT NOT NULL,
                provenance_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (training_run_id) REFERENCES historical_model_training_runs(training_run_id),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_model_artifact_targets (
                target_artifact_row_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                target_identity TEXT NOT NULL,
                target_order INTEGER NOT NULL,
                estimator_fingerprint TEXT NOT NULL,
                model_type TEXT NOT NULL,
                class_order_snapshot TEXT NOT NULL,
                coefficients_snapshot TEXT NOT NULL,
                intercept_snapshot TEXT NOT NULL,
                convergence_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (artifact_id) REFERENCES historical_model_artifacts(artifact_id),
                UNIQUE (artifact_id, target_identity),
                UNIQUE (artifact_id, target_order),
                CHECK (target_order >= 0),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_model_preprocessing_features (
                preprocessing_row_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                original_feature_index INTEGER NOT NULL,
                transformed_feature_index INTEGER NOT NULL,
                imputation_value TEXT,
                missing_training_count INTEGER NOT NULL,
                scaling_mean TEXT NOT NULL,
                scaling_scale TEXT NOT NULL,
                zero_variance_flag INTEGER NOT NULL,
                preprocessing_row_fingerprint TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (artifact_id) REFERENCES historical_model_artifacts(artifact_id),
                UNIQUE (artifact_id, original_feature_index),
                UNIQUE (artifact_id, transformed_feature_index),
                CHECK (original_feature_index >= 0),
                CHECK (transformed_feature_index >= 0),
                CHECK (missing_training_count >= 0),
                CHECK (zero_variance_flag IN (0, 1)),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_model_training_examples (
                training_example_link_id TEXT PRIMARY KEY,
                training_run_id TEXT NOT NULL,
                training_example_id TEXT NOT NULL,
                example_fingerprint TEXT NOT NULL,
                partition TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (training_run_id) REFERENCES historical_model_training_runs(training_run_id),
                FOREIGN KEY (training_example_id) REFERENCES historical_training_examples(training_example_id),
                UNIQUE (training_run_id, training_example_id, partition),
                UNIQUE (training_run_id, partition, deterministic_order),
                CHECK (partition IN ('TRAIN', 'VALIDATION')),
                CHECK (deterministic_order >= 0),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_model_metrics (
                metric_row_id TEXT PRIMARY KEY,
                training_run_id TEXT NOT NULL,
                partition TEXT NOT NULL,
                target_identity TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value TEXT,
                metric_snapshot TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (training_run_id) REFERENCES historical_model_training_runs(training_run_id),
                UNIQUE (training_run_id, partition, target_identity, metric_name),
                UNIQUE (training_run_id, deterministic_order),
                CHECK (partition IN ('TRAIN', 'VALIDATION')),
                CHECK (deterministic_order >= 0),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_historical_model_run_split
                ON historical_model_training_runs (source_split_id, training_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_model_run_fold
                ON historical_model_training_runs (fold_id, training_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_model_run_family
                ON historical_model_training_runs (model_family, training_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_model_artifact_run
                ON historical_model_artifacts (training_run_id, artifact_fingerprint)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_model_target
                ON historical_model_artifact_targets (target_identity, artifact_id)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_model_example_partition
                ON historical_model_training_examples (training_run_id, partition, deterministic_order)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_model_metric_partition
                ON historical_model_metrics (training_run_id, partition, target_identity)""",
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_training_runs_no_update
            BEFORE UPDATE ON historical_model_training_runs
            BEGIN SELECT RAISE(ABORT, 'Historical model training runs are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_training_runs_no_delete
            BEFORE DELETE ON historical_model_training_runs
            BEGIN SELECT RAISE(ABORT, 'Historical model training runs are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_artifacts_no_update
            BEFORE UPDATE ON historical_model_artifacts
            BEGIN SELECT RAISE(ABORT, 'Historical model artifacts are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_artifacts_no_delete
            BEFORE DELETE ON historical_model_artifacts
            BEGIN SELECT RAISE(ABORT, 'Historical model artifacts are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_artifact_targets_no_update
            BEFORE UPDATE ON historical_model_artifact_targets
            BEGIN SELECT RAISE(ABORT, 'Historical model artifact targets are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_artifact_targets_no_delete
            BEFORE DELETE ON historical_model_artifact_targets
            BEGIN SELECT RAISE(ABORT, 'Historical model artifact targets are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_preprocessing_features_no_update
            BEFORE UPDATE ON historical_model_preprocessing_features
            BEGIN SELECT RAISE(ABORT, 'Historical model preprocessing features are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_preprocessing_features_no_delete
            BEFORE DELETE ON historical_model_preprocessing_features
            BEGIN SELECT RAISE(ABORT, 'Historical model preprocessing features are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_training_examples_no_update
            BEFORE UPDATE ON historical_model_training_examples
            BEGIN SELECT RAISE(ABORT, 'Historical model training example links are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_training_examples_no_delete
            BEFORE DELETE ON historical_model_training_examples
            BEGIN SELECT RAISE(ABORT, 'Historical model training example links are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_metrics_no_update
            BEFORE UPDATE ON historical_model_metrics
            BEGIN SELECT RAISE(ABORT, 'Historical model metrics are immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS historical_model_metrics_no_delete
            BEFORE DELETE ON historical_model_metrics
            BEGIN SELECT RAISE(ABORT, 'Historical model metrics are immutable'); END
            """,
        ),
    ),
    Migration(
        version=27,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS historical_probability_calibration_runs (
                calibration_run_id TEXT PRIMARY KEY,
                calibration_request_id TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL,
                calibration_run_fingerprint TEXT NOT NULL UNIQUE,
                source_training_run_id TEXT NOT NULL,
                source_training_run_fingerprint TEXT NOT NULL,
                source_artifact_id TEXT NOT NULL,
                source_artifact_fingerprint TEXT NOT NULL,
                source_split_id TEXT NOT NULL,
                source_split_fingerprint TEXT NOT NULL,
                fold_id TEXT NOT NULL,
                fold_fingerprint TEXT NOT NULL,
                validation_row_count INTEGER NOT NULL,
                fitted_target_count INTEGER NOT NULL,
                derived_target_count INTEGER NOT NULL,
                policy_versions_snapshot TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reason_codes_snapshot TEXT NOT NULL,
                aggregate_raw_metrics_snapshot TEXT NOT NULL,
                aggregate_calibrated_metrics_snapshot TEXT NOT NULL,
                monotonicity_summary TEXT NOT NULL,
                reconciliation_summary TEXT NOT NULL,
                deterministic_run_snapshot TEXT NOT NULL,
                calibration_timestamp TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (source_training_run_id) REFERENCES historical_model_training_runs(training_run_id),
                FOREIGN KEY (source_artifact_id) REFERENCES historical_model_artifacts(artifact_id),
                FOREIGN KEY (source_split_id) REFERENCES historical_dataset_splits(split_id),
                FOREIGN KEY (fold_id) REFERENCES historical_dataset_split_folds(fold_id),
                UNIQUE (calibration_request_id, request_fingerprint),
                CHECK (validation_row_count >= 0),
                CHECK (fitted_target_count = 7),
                CHECK (derived_target_count = 4),
                CHECK (substr(calibration_timestamp, -1) = 'Z'),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_probability_calibration_artifact_sets (
                artifact_set_id TEXT PRIMARY KEY,
                calibration_run_id TEXT NOT NULL UNIQUE,
                artifact_set_fingerprint TEXT NOT NULL UNIQUE,
                artifact_format_version TEXT NOT NULL,
                runtime_compatibility_version TEXT NOT NULL,
                target_schema_version TEXT NOT NULL,
                canonical_target_order_snapshot TEXT NOT NULL,
                clamp_policy_snapshot TEXT NOT NULL,
                monotonicity_policy_snapshot TEXT NOT NULL,
                reconciliation_policy_snapshot TEXT NOT NULL,
                compatibility_snapshot TEXT NOT NULL,
                provenance_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (calibration_run_id) REFERENCES historical_probability_calibration_runs(calibration_run_id),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_probability_calibration_targets (
                target_artifact_row_id TEXT PRIMARY KEY,
                artifact_set_id TEXT NOT NULL,
                target_identity TEXT NOT NULL,
                target_order INTEGER NOT NULL,
                calibration_method TEXT NOT NULL,
                target_artifact_fingerprint TEXT NOT NULL,
                fitted_parameters_snapshot TEXT NOT NULL,
                class_order_snapshot TEXT NOT NULL,
                support_snapshot TEXT NOT NULL,
                convergence_snapshot TEXT NOT NULL,
                derivation_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (artifact_set_id) REFERENCES historical_probability_calibration_artifact_sets(artifact_set_id),
                UNIQUE (artifact_set_id, target_identity),
                UNIQUE (artifact_set_id, target_order),
                CHECK (target_order >= 0),
                CHECK (calibration_method IN ('IDENTITY_V1','PLATT_SCALING_V1','ISOTONIC_REGRESSION_V1')),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_probability_calibration_predictions (
                prediction_row_id TEXT PRIMARY KEY,
                calibration_run_id TEXT NOT NULL,
                training_example_id TEXT NOT NULL,
                example_fingerprint TEXT NOT NULL,
                raw_prediction_fingerprint TEXT NOT NULL,
                raw_probabilities_snapshot TEXT NOT NULL,
                calibrated_probabilities_snapshot TEXT NOT NULL,
                monotonicity_adjustment_snapshot TEXT NOT NULL,
                reconciliation_snapshot TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (calibration_run_id) REFERENCES historical_probability_calibration_runs(calibration_run_id),
                FOREIGN KEY (training_example_id) REFERENCES historical_training_examples(training_example_id),
                UNIQUE (calibration_run_id, training_example_id),
                UNIQUE (calibration_run_id, deterministic_order),
                CHECK (deterministic_order >= 0),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_probability_calibration_metrics (
                metric_row_id TEXT PRIMARY KEY,
                calibration_run_id TEXT NOT NULL,
                target_identity TEXT NOT NULL,
                metric_phase TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value TEXT,
                metric_snapshot TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (calibration_run_id) REFERENCES historical_probability_calibration_runs(calibration_run_id),
                UNIQUE (calibration_run_id, target_identity, metric_phase, metric_name),
                UNIQUE (calibration_run_id, deterministic_order),
                CHECK (metric_phase IN ('RAW','CALIBRATED')),
                CHECK (deterministic_order >= 0),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_probability_calibration_reliability_bins (
                bin_row_id TEXT PRIMARY KEY,
                calibration_run_id TEXT NOT NULL,
                target_identity TEXT NOT NULL,
                metric_phase TEXT NOT NULL,
                bin_index INTEGER NOT NULL,
                lower_bound TEXT NOT NULL,
                upper_bound TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                mean_predicted_probability TEXT,
                observed_frequency TEXT,
                absolute_gap TEXT,
                bin_fingerprint TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (calibration_run_id) REFERENCES historical_probability_calibration_runs(calibration_run_id),
                UNIQUE (calibration_run_id, target_identity, metric_phase, bin_index),
                CHECK (metric_phase IN ('RAW','CALIBRATED')),
                CHECK (bin_index >= 0),
                CHECK (sample_count >= 0),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_historical_calibration_source_artifact
                ON historical_probability_calibration_runs (source_artifact_id, calibration_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_calibration_training_run
                ON historical_probability_calibration_runs (source_training_run_id, calibration_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_calibration_split_fold
                ON historical_probability_calibration_runs (source_split_id, fold_id, calibration_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_calibration_target_method
                ON historical_probability_calibration_targets (target_identity, calibration_method, artifact_set_id)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_calibration_prediction_run
                ON historical_probability_calibration_predictions (calibration_run_id, deterministic_order)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_calibration_metric_run
                ON historical_probability_calibration_metrics (calibration_run_id, target_identity, metric_phase)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_calibration_bin_run
                ON historical_probability_calibration_reliability_bins (calibration_run_id, target_identity, metric_phase)""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_runs_no_update BEFORE UPDATE ON historical_probability_calibration_runs BEGIN SELECT RAISE(ABORT, 'Historical calibration runs are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_runs_no_delete BEFORE DELETE ON historical_probability_calibration_runs BEGIN SELECT RAISE(ABORT, 'Historical calibration runs are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_artifact_sets_no_update BEFORE UPDATE ON historical_probability_calibration_artifact_sets BEGIN SELECT RAISE(ABORT, 'Historical calibration artifact sets are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_artifact_sets_no_delete BEFORE DELETE ON historical_probability_calibration_artifact_sets BEGIN SELECT RAISE(ABORT, 'Historical calibration artifact sets are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_targets_no_update BEFORE UPDATE ON historical_probability_calibration_targets BEGIN SELECT RAISE(ABORT, 'Historical calibration targets are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_targets_no_delete BEFORE DELETE ON historical_probability_calibration_targets BEGIN SELECT RAISE(ABORT, 'Historical calibration targets are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_predictions_no_update BEFORE UPDATE ON historical_probability_calibration_predictions BEGIN SELECT RAISE(ABORT, 'Historical calibration predictions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_predictions_no_delete BEFORE DELETE ON historical_probability_calibration_predictions BEGIN SELECT RAISE(ABORT, 'Historical calibration predictions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_metrics_no_update BEFORE UPDATE ON historical_probability_calibration_metrics BEGIN SELECT RAISE(ABORT, 'Historical calibration metrics are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_metrics_no_delete BEFORE DELETE ON historical_probability_calibration_metrics BEGIN SELECT RAISE(ABORT, 'Historical calibration metrics are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_reliability_bins_no_update BEFORE UPDATE ON historical_probability_calibration_reliability_bins BEGIN SELECT RAISE(ABORT, 'Historical calibration reliability bins are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_probability_calibration_reliability_bins_no_delete BEFORE DELETE ON historical_probability_calibration_reliability_bins BEGIN SELECT RAISE(ABORT, 'Historical calibration reliability bins are immutable'); END""",
        ),
    ),
    Migration(
        version=28,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS historical_backtest_runs (
                backtest_run_id TEXT PRIMARY KEY,
                backtest_request_id TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL UNIQUE,
                backtest_run_fingerprint TEXT NOT NULL UNIQUE,
                source_split_id TEXT NOT NULL,
                source_split_fingerprint TEXT NOT NULL,
                fold_id TEXT NOT NULL,
                fold_fingerprint TEXT NOT NULL,
                source_training_run_id TEXT NOT NULL,
                source_training_run_fingerprint TEXT NOT NULL,
                model_artifact_id TEXT NOT NULL,
                model_artifact_fingerprint TEXT NOT NULL,
                calibration_run_id TEXT NOT NULL,
                calibration_run_fingerprint TEXT NOT NULL,
                calibration_artifact_set_id TEXT NOT NULL,
                calibration_artifact_set_fingerprint TEXT NOT NULL,
                odds_dataset_id TEXT NOT NULL,
                odds_dataset_fingerprint TEXT NOT NULL,
                closing_odds_dataset_id TEXT,
                closing_odds_dataset_fingerprint TEXT,
                policy_versions_snapshot TEXT NOT NULL,
                test_example_count INTEGER NOT NULL,
                prediction_count INTEGER NOT NULL,
                assessed_market_count INTEGER NOT NULL,
                selected_bet_count INTEGER NOT NULL,
                settled_count INTEGER NOT NULL,
                win_count INTEGER NOT NULL,
                loss_count INTEGER NOT NULL,
                void_count INTEGER NOT NULL,
                initial_bankroll TEXT NOT NULL,
                final_bankroll TEXT NOT NULL,
                net_profit TEXT NOT NULL,
                roi TEXT,
                maximum_drawdown TEXT NOT NULL,
                aggregate_predictive_metrics_snapshot TEXT NOT NULL,
                aggregate_betting_metrics_snapshot TEXT NOT NULL,
                deterministic_run_snapshot TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reason_codes_snapshot TEXT NOT NULL,
                backtest_timestamp TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (source_split_id) REFERENCES historical_dataset_splits(split_id),
                FOREIGN KEY (fold_id) REFERENCES historical_dataset_split_folds(fold_id),
                FOREIGN KEY (source_training_run_id) REFERENCES historical_model_training_runs(training_run_id),
                FOREIGN KEY (model_artifact_id) REFERENCES historical_model_artifacts(artifact_id),
                FOREIGN KEY (calibration_run_id) REFERENCES historical_probability_calibration_runs(calibration_run_id),
                FOREIGN KEY (calibration_artifact_set_id) REFERENCES historical_probability_calibration_artifact_sets(artifact_set_id),
                CHECK (test_example_count >= 0 AND prediction_count >= 0),
                CHECK (assessed_market_count >= 0 AND selected_bet_count >= 0),
                CHECK (settled_count >= 0 AND win_count >= 0 AND loss_count >= 0 AND void_count >= 0),
                CHECK (substr(backtest_timestamp, -1) = 'Z'),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_backtest_predictions (
                prediction_row_id TEXT PRIMARY KEY,
                backtest_run_id TEXT NOT NULL,
                training_example_id TEXT NOT NULL,
                historical_match_id TEXT NOT NULL,
                example_fingerprint TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                raw_probabilities_snapshot TEXT NOT NULL,
                calibrated_probabilities_snapshot TEXT NOT NULL,
                raw_prediction_fingerprint TEXT NOT NULL,
                calibrated_prediction_fingerprint TEXT NOT NULL,
                label_snapshot TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (backtest_run_id) REFERENCES historical_backtest_runs(backtest_run_id),
                UNIQUE (backtest_run_id, training_example_id),
                UNIQUE (backtest_run_id, deterministic_order)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_backtest_odds_snapshots (
                stored_odds_row_id TEXT PRIMARY KEY,
                backtest_run_id TEXT NOT NULL,
                odds_snapshot_id TEXT NOT NULL,
                historical_match_id TEXT NOT NULL,
                competition TEXT NOT NULL,
                kickoff_timestamp TEXT NOT NULL,
                market_identity TEXT NOT NULL,
                selection_identity TEXT NOT NULL,
                snapshot_timestamp TEXT NOT NULL,
                decimal_odds TEXT NOT NULL,
                currency TEXT,
                bookmaker_identity TEXT NOT NULL,
                market_status TEXT NOT NULL,
                source_identity TEXT NOT NULL,
                source_version TEXT NOT NULL,
                source_record_identity TEXT NOT NULL,
                source_fingerprint TEXT NOT NULL,
                metadata_version TEXT NOT NULL,
                closing_flag INTEGER NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (backtest_run_id) REFERENCES historical_backtest_runs(backtest_run_id),
                UNIQUE (backtest_run_id, odds_snapshot_id, closing_flag)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_backtest_market_assessments (
                assessment_id TEXT PRIMARY KEY,
                backtest_run_id TEXT NOT NULL,
                prediction_row_id TEXT NOT NULL,
                odds_row_id TEXT,
                market_identity TEXT NOT NULL,
                calibrated_probability TEXT,
                fair_odds TEXT,
                decimal_odds TEXT,
                implied_probability TEXT,
                expected_value TEXT,
                edge TEXT,
                odds_age_seconds INTEGER,
                eligible_flag INTEGER NOT NULL,
                rejection_reasons_snapshot TEXT NOT NULL,
                assessment_fingerprint TEXT NOT NULL,
                deterministic_rank INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (backtest_run_id) REFERENCES historical_backtest_runs(backtest_run_id),
                FOREIGN KEY (prediction_row_id) REFERENCES historical_backtest_predictions(prediction_row_id),
                FOREIGN KEY (odds_row_id) REFERENCES historical_backtest_odds_snapshots(stored_odds_row_id),
                UNIQUE (backtest_run_id, prediction_row_id, market_identity, deterministic_rank)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_backtest_selections (
                selection_id TEXT PRIMARY KEY,
                backtest_run_id TEXT NOT NULL,
                historical_match_id TEXT NOT NULL,
                kickoff_group_id TEXT NOT NULL,
                selected_assessment_id TEXT NOT NULL,
                market_identity TEXT NOT NULL,
                decimal_odds TEXT NOT NULL,
                calibrated_probability TEXT NOT NULL,
                expected_value TEXT NOT NULL,
                bankroll_snapshot TEXT NOT NULL,
                stake_percentage TEXT NOT NULL,
                recommended_stake_amount TEXT NOT NULL,
                applied_stake_amount TEXT NOT NULL,
                stake_classification TEXT NOT NULL,
                reduction_reason TEXT,
                rejection_reason TEXT,
                selection_fingerprint TEXT NOT NULL,
                stake_fingerprint TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (backtest_run_id) REFERENCES historical_backtest_runs(backtest_run_id),
                FOREIGN KEY (selected_assessment_id) REFERENCES historical_backtest_market_assessments(assessment_id),
                UNIQUE (backtest_run_id, historical_match_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_backtest_settlements (
                settlement_id TEXT PRIMARY KEY,
                backtest_run_id TEXT NOT NULL,
                selection_id TEXT NOT NULL UNIQUE,
                final_home_score INTEGER,
                final_away_score INTEGER,
                settlement_status TEXT NOT NULL,
                gross_return TEXT NOT NULL,
                net_profit_loss TEXT NOT NULL,
                settlement_reason TEXT NOT NULL,
                settlement_fingerprint TEXT NOT NULL,
                settled_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (backtest_run_id) REFERENCES historical_backtest_runs(backtest_run_id),
                FOREIGN KEY (selection_id) REFERENCES historical_backtest_selections(selection_id),
                CHECK (settlement_status IN ('WON','LOST','VOID','PUSH','UNSETTLED','REJECTED'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_backtest_bankroll_ledger (
                ledger_entry_id TEXT PRIMARY KEY,
                backtest_run_id TEXT NOT NULL,
                selection_id TEXT NOT NULL UNIQUE,
                kickoff_group_id TEXT NOT NULL,
                bankroll_before TEXT NOT NULL,
                stake_reserved TEXT NOT NULL,
                gross_return TEXT NOT NULL,
                net_result TEXT NOT NULL,
                bankroll_after TEXT NOT NULL,
                cumulative_profit TEXT NOT NULL,
                cumulative_return TEXT NOT NULL,
                running_peak TEXT NOT NULL,
                absolute_drawdown TEXT NOT NULL,
                percentage_drawdown TEXT NOT NULL,
                ledger_fingerprint TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (backtest_run_id) REFERENCES historical_backtest_runs(backtest_run_id),
                FOREIGN KEY (selection_id) REFERENCES historical_backtest_selections(selection_id),
                UNIQUE (backtest_run_id, deterministic_order)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_backtest_metrics (
                metric_row_id TEXT PRIMARY KEY,
                backtest_run_id TEXT NOT NULL,
                metric_category TEXT NOT NULL,
                grouping_identity TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value TEXT,
                metric_snapshot TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (backtest_run_id) REFERENCES historical_backtest_runs(backtest_run_id),
                UNIQUE (backtest_run_id, deterministic_order)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_backtest_reliability_bins (
                bin_row_id TEXT PRIMARY KEY,
                backtest_run_id TEXT NOT NULL,
                target_identity TEXT NOT NULL,
                probability_phase TEXT NOT NULL,
                bin_index INTEGER NOT NULL,
                lower_bound TEXT NOT NULL,
                upper_bound TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                mean_predicted_probability TEXT,
                observed_frequency TEXT,
                absolute_gap TEXT,
                bin_fingerprint TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (backtest_run_id) REFERENCES historical_backtest_runs(backtest_run_id),
                UNIQUE (backtest_run_id, target_identity, probability_phase, bin_index),
                CHECK (probability_phase IN ('RAW','CALIBRATED'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_backtest_exclusions (
                exclusion_id TEXT PRIMARY KEY,
                backtest_run_id TEXT NOT NULL,
                historical_match_id TEXT,
                training_example_id TEXT,
                market_identity TEXT,
                exclusion_stage TEXT NOT NULL,
                exclusion_reason TEXT NOT NULL,
                detail_snapshot TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (backtest_run_id) REFERENCES historical_backtest_runs(backtest_run_id),
                UNIQUE (backtest_run_id, deterministic_order)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_historical_backtests_model ON historical_backtest_runs (model_artifact_id, backtest_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_backtests_calibration ON historical_backtest_runs (calibration_artifact_set_id, backtest_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_backtests_split_fold ON historical_backtest_runs (source_split_id, fold_id, backtest_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_backtest_predictions_match ON historical_backtest_predictions (historical_match_id, kickoff_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_backtest_odds_market ON historical_backtest_odds_snapshots (historical_match_id, market_identity, snapshot_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_backtest_assessments_market ON historical_backtest_market_assessments (market_identity, eligible_flag)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_backtest_settlements_status ON historical_backtest_settlements (settlement_status, settled_order)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_backtest_metrics_category ON historical_backtest_metrics (metric_category, grouping_identity)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_backtest_bins_target ON historical_backtest_reliability_bins (target_identity, probability_phase)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_backtest_exclusions_match ON historical_backtest_exclusions (historical_match_id, exclusion_stage)""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_runs_no_update BEFORE UPDATE ON historical_backtest_runs BEGIN SELECT RAISE(ABORT, 'Historical backtest runs are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_runs_no_delete BEFORE DELETE ON historical_backtest_runs BEGIN SELECT RAISE(ABORT, 'Historical backtest runs are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_predictions_no_update BEFORE UPDATE ON historical_backtest_predictions BEGIN SELECT RAISE(ABORT, 'Historical backtest predictions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_predictions_no_delete BEFORE DELETE ON historical_backtest_predictions BEGIN SELECT RAISE(ABORT, 'Historical backtest predictions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_odds_snapshots_no_update BEFORE UPDATE ON historical_backtest_odds_snapshots BEGIN SELECT RAISE(ABORT, 'Historical backtest odds are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_odds_snapshots_no_delete BEFORE DELETE ON historical_backtest_odds_snapshots BEGIN SELECT RAISE(ABORT, 'Historical backtest odds are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_market_assessments_no_update BEFORE UPDATE ON historical_backtest_market_assessments BEGIN SELECT RAISE(ABORT, 'Historical backtest assessments are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_market_assessments_no_delete BEFORE DELETE ON historical_backtest_market_assessments BEGIN SELECT RAISE(ABORT, 'Historical backtest assessments are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_selections_no_update BEFORE UPDATE ON historical_backtest_selections BEGIN SELECT RAISE(ABORT, 'Historical backtest selections are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_selections_no_delete BEFORE DELETE ON historical_backtest_selections BEGIN SELECT RAISE(ABORT, 'Historical backtest selections are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_settlements_no_update BEFORE UPDATE ON historical_backtest_settlements BEGIN SELECT RAISE(ABORT, 'Historical backtest settlements are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_settlements_no_delete BEFORE DELETE ON historical_backtest_settlements BEGIN SELECT RAISE(ABORT, 'Historical backtest settlements are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_bankroll_ledger_no_update BEFORE UPDATE ON historical_backtest_bankroll_ledger BEGIN SELECT RAISE(ABORT, 'Historical backtest ledger is immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_bankroll_ledger_no_delete BEFORE DELETE ON historical_backtest_bankroll_ledger BEGIN SELECT RAISE(ABORT, 'Historical backtest ledger is immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_metrics_no_update BEFORE UPDATE ON historical_backtest_metrics BEGIN SELECT RAISE(ABORT, 'Historical backtest metrics are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_metrics_no_delete BEFORE DELETE ON historical_backtest_metrics BEGIN SELECT RAISE(ABORT, 'Historical backtest metrics are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_reliability_bins_no_update BEFORE UPDATE ON historical_backtest_reliability_bins BEGIN SELECT RAISE(ABORT, 'Historical backtest reliability bins are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_reliability_bins_no_delete BEFORE DELETE ON historical_backtest_reliability_bins BEGIN SELECT RAISE(ABORT, 'Historical backtest reliability bins are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_exclusions_no_update BEFORE UPDATE ON historical_backtest_exclusions BEGIN SELECT RAISE(ABORT, 'Historical backtest exclusions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_backtest_exclusions_no_delete BEFORE DELETE ON historical_backtest_exclusions BEGIN SELECT RAISE(ABORT, 'Historical backtest exclusions are immutable'); END""",
        ),
    ),
    Migration(
        version=29,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS model_comparison_runs (
                comparison_run_id TEXT PRIMARY KEY,
                comparison_request_id TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL UNIQUE,
                comparison_run_fingerprint TEXT NOT NULL UNIQUE,
                champion_model_artifact_id TEXT NOT NULL,
                champion_model_artifact_fingerprint TEXT NOT NULL,
                champion_calibration_artifact_set_id TEXT NOT NULL,
                champion_calibration_artifact_set_fingerprint TEXT NOT NULL,
                champion_backtest_run_id TEXT NOT NULL,
                champion_backtest_run_fingerprint TEXT NOT NULL,
                comparison_scope_snapshot TEXT NOT NULL,
                policy_versions_snapshot TEXT NOT NULL,
                challenger_count INTEGER NOT NULL,
                valid_challenger_count INTEGER NOT NULL,
                final_recommended_challenger_id TEXT,
                final_recommendation TEXT NOT NULL,
                reason_codes_snapshot TEXT NOT NULL,
                deterministic_run_snapshot TEXT NOT NULL,
                outcome TEXT NOT NULL,
                comparison_timestamp TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (champion_model_artifact_id) REFERENCES historical_model_artifacts(artifact_id),
                FOREIGN KEY (champion_calibration_artifact_set_id) REFERENCES historical_probability_calibration_artifact_sets(artifact_set_id),
                FOREIGN KEY (champion_backtest_run_id) REFERENCES historical_backtest_runs(backtest_run_id),
                CHECK (challenger_count > 0),
                CHECK (valid_challenger_count > 0 AND valid_challenger_count <= challenger_count),
                CHECK (final_recommendation IN ('PROMOTE_CHALLENGER','KEEP_CHAMPION','REJECT_CHALLENGER','REVIEW_REQUIRED','INSUFFICIENT_EVIDENCE')),
                CHECK (outcome = 'COMPARISON_COMPLETED'),
                CHECK (substr(comparison_timestamp, -1) = 'Z'),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_comparison_candidates (
                candidate_row_id TEXT PRIMARY KEY,
                comparison_run_id TEXT NOT NULL,
                challenger_candidate_id TEXT NOT NULL,
                challenger_label TEXT,
                model_artifact_id TEXT NOT NULL,
                model_artifact_fingerprint TEXT NOT NULL,
                calibration_artifact_set_id TEXT NOT NULL,
                calibration_artifact_set_fingerprint TEXT NOT NULL,
                backtest_run_id TEXT NOT NULL,
                backtest_run_fingerprint TEXT NOT NULL,
                source_compatibility_fingerprint TEXT NOT NULL,
                evaluation_fingerprint TEXT NOT NULL,
                promotion_score TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                deterministic_rank INTEGER NOT NULL,
                reason_codes_snapshot TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (comparison_run_id) REFERENCES model_comparison_runs(comparison_run_id),
                FOREIGN KEY (model_artifact_id) REFERENCES historical_model_artifacts(artifact_id),
                FOREIGN KEY (calibration_artifact_set_id) REFERENCES historical_probability_calibration_artifact_sets(artifact_set_id),
                FOREIGN KEY (backtest_run_id) REFERENCES historical_backtest_runs(backtest_run_id),
                UNIQUE (comparison_run_id, challenger_candidate_id),
                UNIQUE (comparison_run_id, deterministic_rank),
                UNIQUE (comparison_run_id, model_artifact_id, backtest_run_id),
                CHECK (recommendation IN ('PROMOTE_CHALLENGER','KEEP_CHAMPION','REJECT_CHALLENGER','REVIEW_REQUIRED','INSUFFICIENT_EVIDENCE')),
                CHECK (deterministic_rank > 0),
                CHECK (substr(created_timestamp, -1) = 'Z')
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_comparison_source_evidence (
                evidence_row_id TEXT PRIMARY KEY,
                comparison_run_id TEXT NOT NULL,
                candidate_row_id TEXT NOT NULL,
                evidence_category TEXT NOT NULL,
                evidence_name TEXT NOT NULL,
                champion_value_snapshot TEXT NOT NULL,
                challenger_value_snapshot TEXT NOT NULL,
                compatibility_status TEXT NOT NULL,
                detail_snapshot TEXT NOT NULL,
                evidence_fingerprint TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (comparison_run_id) REFERENCES model_comparison_runs(comparison_run_id),
                FOREIGN KEY (candidate_row_id) REFERENCES model_comparison_candidates(candidate_row_id),
                UNIQUE (candidate_row_id, deterministic_order),
                CHECK (compatibility_status IN ('COMPATIBLE','NORMALIZED','REVIEW_REQUIRED','INCOMPATIBLE'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_comparison_metric_evaluations (
                metric_evaluation_id TEXT PRIMARY KEY,
                comparison_run_id TEXT NOT NULL,
                candidate_row_id TEXT NOT NULL,
                category TEXT NOT NULL,
                group_identity TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                direction TEXT NOT NULL,
                champion_value TEXT,
                challenger_value TEXT,
                absolute_delta TEXT,
                relative_delta TEXT,
                normalized_score TEXT NOT NULL,
                materiality TEXT NOT NULL,
                gate_status TEXT NOT NULL,
                reason_codes_snapshot TEXT NOT NULL,
                metric_fingerprint TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (comparison_run_id) REFERENCES model_comparison_runs(comparison_run_id),
                FOREIGN KEY (candidate_row_id) REFERENCES model_comparison_candidates(candidate_row_id),
                UNIQUE (candidate_row_id, deterministic_order),
                CHECK (direction IN ('LOWER_IS_BETTER','HIGHER_IS_BETTER')),
                CHECK (gate_status IN ('PASS','FAIL','REVIEW','INSUFFICIENT','NOT_APPLICABLE'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_comparison_stability_groups (
                stability_row_id TEXT PRIMARY KEY,
                comparison_run_id TEXT NOT NULL,
                candidate_row_id TEXT NOT NULL,
                group_category TEXT NOT NULL,
                group_identity TEXT NOT NULL,
                champion_sample_count INTEGER NOT NULL,
                challenger_sample_count INTEGER NOT NULL,
                champion_metric_snapshot TEXT NOT NULL,
                challenger_metric_snapshot TEXT NOT NULL,
                delta_snapshot TEXT NOT NULL,
                stability_status TEXT NOT NULL,
                concentration_evidence_snapshot TEXT NOT NULL,
                stability_fingerprint TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (comparison_run_id) REFERENCES model_comparison_runs(comparison_run_id),
                FOREIGN KEY (candidate_row_id) REFERENCES model_comparison_candidates(candidate_row_id),
                UNIQUE (candidate_row_id, deterministic_order),
                CHECK (stability_status IN ('IMPROVED','STABLE','DEGRADED','SEVERELY_DEGRADED','INSUFFICIENT_SAMPLE'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_comparison_statistical_evidence (
                statistical_row_id TEXT PRIMARY KEY,
                comparison_run_id TEXT NOT NULL,
                candidate_row_id TEXT NOT NULL,
                evidence_name TEXT NOT NULL,
                paired_sample_count INTEGER NOT NULL,
                deterministic_seed INTEGER NOT NULL,
                bootstrap_iterations INTEGER NOT NULL,
                effect_size TEXT,
                lower_confidence_bound TEXT,
                upper_confidence_bound TEXT,
                uncertainty_classification TEXT NOT NULL,
                detail_snapshot TEXT NOT NULL,
                evidence_fingerprint TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (comparison_run_id) REFERENCES model_comparison_runs(comparison_run_id),
                FOREIGN KEY (candidate_row_id) REFERENCES model_comparison_candidates(candidate_row_id),
                UNIQUE (candidate_row_id, deterministic_order),
                CHECK (uncertainty_classification IN ('STRONG_EVIDENCE','MODERATE_EVIDENCE','WEAK_EVIDENCE','INCONCLUSIVE'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_comparison_gate_evaluations (
                gate_evaluation_id TEXT PRIMARY KEY,
                comparison_run_id TEXT NOT NULL,
                candidate_row_id TEXT NOT NULL,
                gate_category TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                mandatory_flag INTEGER NOT NULL,
                status TEXT NOT NULL,
                champion_value_snapshot TEXT NOT NULL,
                challenger_value_snapshot TEXT NOT NULL,
                threshold_snapshot TEXT NOT NULL,
                reason_codes_snapshot TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (comparison_run_id) REFERENCES model_comparison_runs(comparison_run_id),
                FOREIGN KEY (candidate_row_id) REFERENCES model_comparison_candidates(candidate_row_id),
                UNIQUE (candidate_row_id, deterministic_order),
                CHECK (mandatory_flag IN (0,1)),
                CHECK (status IN ('PASS','FAIL','REVIEW','INSUFFICIENT','NOT_APPLICABLE'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_comparison_score_components (
                score_component_id TEXT PRIMARY KEY,
                comparison_run_id TEXT NOT NULL,
                candidate_row_id TEXT NOT NULL,
                score_category TEXT NOT NULL,
                raw_score TEXT NOT NULL,
                normalized_score TEXT NOT NULL,
                weight TEXT NOT NULL,
                weighted_contribution TEXT NOT NULL,
                gate_status TEXT NOT NULL,
                detail_snapshot TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (comparison_run_id) REFERENCES model_comparison_runs(comparison_run_id),
                FOREIGN KEY (candidate_row_id) REFERENCES model_comparison_candidates(candidate_row_id),
                UNIQUE (candidate_row_id, score_category),
                UNIQUE (candidate_row_id, deterministic_order)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_comparison_recommendations (
                recommendation_id TEXT PRIMARY KEY,
                comparison_run_id TEXT NOT NULL,
                candidate_row_id TEXT,
                recommendation_scope TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                promotion_rank INTEGER,
                promotion_score TEXT NOT NULL,
                evidence_classification TEXT NOT NULL,
                reason_codes_snapshot TEXT NOT NULL,
                recommendation_fingerprint TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (comparison_run_id) REFERENCES model_comparison_runs(comparison_run_id),
                FOREIGN KEY (candidate_row_id) REFERENCES model_comparison_candidates(candidate_row_id),
                UNIQUE (comparison_run_id, recommendation_scope, candidate_row_id),
                CHECK (recommendation IN ('PROMOTE_CHALLENGER','KEEP_CHAMPION','REJECT_CHALLENGER','REVIEW_REQUIRED','INSUFFICIENT_EVIDENCE'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_comparison_exclusions (
                exclusion_id TEXT PRIMARY KEY,
                comparison_run_id TEXT NOT NULL,
                challenger_candidate_id TEXT,
                exclusion_stage TEXT NOT NULL,
                exclusion_reason TEXT NOT NULL,
                detail_snapshot TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY (comparison_run_id) REFERENCES model_comparison_runs(comparison_run_id),
                UNIQUE (comparison_run_id, deterministic_order)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_model_comparison_champion_model ON model_comparison_runs (champion_model_artifact_id, comparison_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_model_comparison_champion_backtest ON model_comparison_runs (champion_backtest_run_id, comparison_timestamp)""",
            """CREATE INDEX IF NOT EXISTS idx_model_comparison_challenger_model ON model_comparison_candidates (model_artifact_id, deterministic_rank)""",
            """CREATE INDEX IF NOT EXISTS idx_model_comparison_challenger_backtest ON model_comparison_candidates (backtest_run_id, deterministic_rank)""",
            """CREATE INDEX IF NOT EXISTS idx_model_comparison_candidate_recommendation ON model_comparison_candidates (recommendation, deterministic_rank)""",
            """CREATE INDEX IF NOT EXISTS idx_model_comparison_metric_category ON model_comparison_metric_evaluations (category, metric_name)""",
            """CREATE INDEX IF NOT EXISTS idx_model_comparison_gate_status ON model_comparison_gate_evaluations (status, gate_category)""",
            """CREATE INDEX IF NOT EXISTS idx_model_comparison_stability_category ON model_comparison_stability_groups (group_category, stability_status)""",
            """CREATE INDEX IF NOT EXISTS idx_model_comparison_recommendation ON model_comparison_recommendations (recommendation, promotion_rank)""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_runs_no_update BEFORE UPDATE ON model_comparison_runs BEGIN SELECT RAISE(ABORT, 'Model comparison runs are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_runs_no_delete BEFORE DELETE ON model_comparison_runs BEGIN SELECT RAISE(ABORT, 'Model comparison runs are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_candidates_no_update BEFORE UPDATE ON model_comparison_candidates BEGIN SELECT RAISE(ABORT, 'Model comparison candidates are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_candidates_no_delete BEFORE DELETE ON model_comparison_candidates BEGIN SELECT RAISE(ABORT, 'Model comparison candidates are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_source_evidence_no_update BEFORE UPDATE ON model_comparison_source_evidence BEGIN SELECT RAISE(ABORT, 'Model comparison source evidence is immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_source_evidence_no_delete BEFORE DELETE ON model_comparison_source_evidence BEGIN SELECT RAISE(ABORT, 'Model comparison source evidence is immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_metric_evaluations_no_update BEFORE UPDATE ON model_comparison_metric_evaluations BEGIN SELECT RAISE(ABORT, 'Model comparison metrics are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_metric_evaluations_no_delete BEFORE DELETE ON model_comparison_metric_evaluations BEGIN SELECT RAISE(ABORT, 'Model comparison metrics are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_stability_groups_no_update BEFORE UPDATE ON model_comparison_stability_groups BEGIN SELECT RAISE(ABORT, 'Model comparison stability evidence is immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_stability_groups_no_delete BEFORE DELETE ON model_comparison_stability_groups BEGIN SELECT RAISE(ABORT, 'Model comparison stability evidence is immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_statistical_evidence_no_update BEFORE UPDATE ON model_comparison_statistical_evidence BEGIN SELECT RAISE(ABORT, 'Model comparison statistical evidence is immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_statistical_evidence_no_delete BEFORE DELETE ON model_comparison_statistical_evidence BEGIN SELECT RAISE(ABORT, 'Model comparison statistical evidence is immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_gate_evaluations_no_update BEFORE UPDATE ON model_comparison_gate_evaluations BEGIN SELECT RAISE(ABORT, 'Model comparison gates are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_gate_evaluations_no_delete BEFORE DELETE ON model_comparison_gate_evaluations BEGIN SELECT RAISE(ABORT, 'Model comparison gates are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_score_components_no_update BEFORE UPDATE ON model_comparison_score_components BEGIN SELECT RAISE(ABORT, 'Model comparison scores are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_score_components_no_delete BEFORE DELETE ON model_comparison_score_components BEGIN SELECT RAISE(ABORT, 'Model comparison scores are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_recommendations_no_update BEFORE UPDATE ON model_comparison_recommendations BEGIN SELECT RAISE(ABORT, 'Model comparison recommendations are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_recommendations_no_delete BEFORE DELETE ON model_comparison_recommendations BEGIN SELECT RAISE(ABORT, 'Model comparison recommendations are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_exclusions_no_update BEFORE UPDATE ON model_comparison_exclusions BEGIN SELECT RAISE(ABORT, 'Model comparison exclusions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_comparison_exclusions_no_delete BEFORE DELETE ON model_comparison_exclusions BEGIN SELECT RAISE(ABORT, 'Model comparison exclusions are immutable'); END""",
        ),
    ),
    Migration(
        version=30,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS shadow_evaluation_executions (
                shadow_execution_id TEXT PRIMARY KEY,
                shadow_request_id TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL,
                execution_fingerprint TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK (status='PRE_MATCH_EVALUATED'),
                comparison_run_id TEXT NOT NULL,
                challenger_candidate_id TEXT NOT NULL,
                champion_model_artifact_id TEXT NOT NULL,
                challenger_model_artifact_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                competition TEXT NOT NULL,
                kickoff_utc TEXT NOT NULL,
                evaluation_timestamp_utc TEXT NOT NULL,
                command_snapshot TEXT NOT NULL,
                deterministic_snapshot TEXT NOT NULL,
                FOREIGN KEY (comparison_run_id) REFERENCES model_comparison_runs(comparison_run_id),
                FOREIGN KEY (champion_model_artifact_id) REFERENCES historical_model_artifacts(artifact_id),
                FOREIGN KEY (challenger_model_artifact_id) REFERENCES historical_model_artifacts(artifact_id),
                CHECK (champion_model_artifact_id <> challenger_model_artifact_id),
                CHECK (evaluation_timestamp_utc < kickoff_utc)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shadow_evaluation_input_snapshots (
                input_snapshot_row_id TEXT PRIMARY KEY,
                input_snapshot_fingerprint TEXT NOT NULL,
                shadow_execution_id TEXT NOT NULL UNIQUE,
                model_input_vector_id TEXT NOT NULL,
                model_input_fingerprint TEXT NOT NULL,
                odds_snapshot_set_fingerprint TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                FOREIGN KEY (shadow_execution_id) REFERENCES shadow_evaluation_executions(shadow_execution_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shadow_evaluation_inferences (
                inference_id TEXT PRIMARY KEY,
                shadow_execution_id TEXT NOT NULL,
                model_role TEXT NOT NULL CHECK (model_role IN ('CHAMPION','CHALLENGER')),
                model_artifact_id TEXT NOT NULL,
                calibration_artifact_set_id TEXT NOT NULL,
                raw_inference_fingerprint TEXT NOT NULL,
                calibrated_inference_fingerprint TEXT NOT NULL,
                preprocessing_fingerprint TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                FOREIGN KEY (shadow_execution_id) REFERENCES shadow_evaluation_executions(shadow_execution_id),
                FOREIGN KEY (model_artifact_id) REFERENCES historical_model_artifacts(artifact_id),
                FOREIGN KEY (calibration_artifact_set_id) REFERENCES historical_probability_calibration_artifact_sets(artifact_set_id),
                UNIQUE (shadow_execution_id, model_role)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shadow_evaluation_market_assessments (
                assessment_id TEXT PRIMARY KEY,
                shadow_execution_id TEXT NOT NULL,
                model_role TEXT NOT NULL CHECK (model_role IN ('CHAMPION','CHALLENGER')),
                market_identity TEXT NOT NULL,
                odds_snapshot_id TEXT,
                eligible INTEGER NOT NULL CHECK (eligible IN (0,1)),
                deterministic_rank INTEGER NOT NULL,
                assessment_fingerprint TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                FOREIGN KEY (shadow_execution_id) REFERENCES shadow_evaluation_executions(shadow_execution_id),
                UNIQUE (shadow_execution_id, model_role, market_identity)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shadow_evaluation_selections (
                selection_id TEXT PRIMARY KEY,
                shadow_execution_id TEXT NOT NULL,
                model_role TEXT NOT NULL CHECK (model_role IN ('CHAMPION','CHALLENGER')),
                market_identity TEXT,
                outcome TEXT NOT NULL,
                selection_fingerprint TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                FOREIGN KEY (shadow_execution_id) REFERENCES shadow_evaluation_executions(shadow_execution_id),
                UNIQUE (shadow_execution_id, model_role)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shadow_evaluation_comparisons (
                comparison_id TEXT PRIMARY KEY,
                shadow_execution_id TEXT NOT NULL UNIQUE,
                disagreement_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                comparison_fingerprint TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                FOREIGN KEY (shadow_execution_id) REFERENCES shadow_evaluation_executions(shadow_execution_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shadow_evaluation_settlements (
                settlement_id TEXT PRIMARY KEY,
                settlement_request_id TEXT NOT NULL UNIQUE,
                shadow_execution_id TEXT NOT NULL UNIQUE,
                champion_outcome TEXT NOT NULL,
                challenger_outcome TEXT NOT NULL,
                champion_profit_per_unit TEXT NOT NULL,
                challenger_profit_per_unit TEXT NOT NULL,
                final_home_score INTEGER NOT NULL CHECK (final_home_score >= 0),
                final_away_score INTEGER NOT NULL CHECK (final_away_score >= 0),
                source_fingerprint TEXT NOT NULL,
                settlement_timestamp_utc TEXT NOT NULL,
                settlement_fingerprint TEXT NOT NULL UNIQUE,
                snapshot TEXT NOT NULL,
                FOREIGN KEY (shadow_execution_id) REFERENCES shadow_evaluation_executions(shadow_execution_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shadow_evaluation_metrics (
                metric_id TEXT PRIMARY KEY,
                shadow_execution_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                model_role TEXT,
                category TEXT NOT NULL,
                grouping_identity TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value TEXT,
                metric_fingerprint TEXT NOT NULL,
                metric_snapshot TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                FOREIGN KEY (shadow_execution_id) REFERENCES shadow_evaluation_executions(shadow_execution_id),
                UNIQUE (shadow_execution_id, phase, model_role, category, grouping_identity, metric_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shadow_evaluation_aggregate_snapshots (
                aggregate_snapshot_id TEXT PRIMARY KEY,
                shadow_execution_id TEXT NOT NULL,
                grouping_category TEXT NOT NULL,
                grouping_identity TEXT NOT NULL,
                sample_count INTEGER NOT NULL CHECK (sample_count >= 0),
                settled_count INTEGER NOT NULL CHECK (settled_count >= 0),
                aggregate_fingerprint TEXT NOT NULL,
                metric_snapshot TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                FOREIGN KEY (shadow_execution_id) REFERENCES shadow_evaluation_executions(shadow_execution_id),
                UNIQUE (shadow_execution_id, grouping_category, grouping_identity, aggregate_fingerprint)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shadow_evaluation_exclusions (
                exclusion_id TEXT PRIMARY KEY,
                shadow_execution_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                reason TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                detail_snapshot TEXT NOT NULL,
                FOREIGN KEY (shadow_execution_id) REFERENCES shadow_evaluation_executions(shadow_execution_id),
                UNIQUE (shadow_execution_id, deterministic_order)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_shadow_champion ON shadow_evaluation_executions (champion_model_artifact_id,evaluation_timestamp_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_shadow_challenger ON shadow_evaluation_executions (challenger_model_artifact_id,evaluation_timestamp_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_shadow_match ON shadow_evaluation_executions (match_id,kickoff_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_shadow_pair ON shadow_evaluation_executions (champion_model_artifact_id,challenger_model_artifact_id,evaluation_timestamp_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_shadow_disagreement ON shadow_evaluation_comparisons (disagreement_type,severity)""",
            """CREATE INDEX IF NOT EXISTS idx_shadow_metrics ON shadow_evaluation_metrics (category,metric_name,grouping_identity)""",
            """CREATE INDEX IF NOT EXISTS idx_shadow_settlement_time ON shadow_evaluation_settlements (settlement_timestamp_utc)""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_executions_no_update BEFORE UPDATE ON shadow_evaluation_executions BEGIN SELECT RAISE(ABORT,'Shadow executions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_executions_no_delete BEFORE DELETE ON shadow_evaluation_executions BEGIN SELECT RAISE(ABORT,'Shadow executions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_input_snapshots_no_update BEFORE UPDATE ON shadow_evaluation_input_snapshots BEGIN SELECT RAISE(ABORT,'Shadow input snapshots are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_input_snapshots_no_delete BEFORE DELETE ON shadow_evaluation_input_snapshots BEGIN SELECT RAISE(ABORT,'Shadow input snapshots are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_inferences_no_update BEFORE UPDATE ON shadow_evaluation_inferences BEGIN SELECT RAISE(ABORT,'Shadow inferences are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_inferences_no_delete BEFORE DELETE ON shadow_evaluation_inferences BEGIN SELECT RAISE(ABORT,'Shadow inferences are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_market_assessments_no_update BEFORE UPDATE ON shadow_evaluation_market_assessments BEGIN SELECT RAISE(ABORT,'Shadow assessments are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_market_assessments_no_delete BEFORE DELETE ON shadow_evaluation_market_assessments BEGIN SELECT RAISE(ABORT,'Shadow assessments are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_selections_no_update BEFORE UPDATE ON shadow_evaluation_selections BEGIN SELECT RAISE(ABORT,'Shadow selections are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_selections_no_delete BEFORE DELETE ON shadow_evaluation_selections BEGIN SELECT RAISE(ABORT,'Shadow selections are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_comparisons_no_update BEFORE UPDATE ON shadow_evaluation_comparisons BEGIN SELECT RAISE(ABORT,'Shadow comparisons are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_comparisons_no_delete BEFORE DELETE ON shadow_evaluation_comparisons BEGIN SELECT RAISE(ABORT,'Shadow comparisons are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_settlements_no_update BEFORE UPDATE ON shadow_evaluation_settlements BEGIN SELECT RAISE(ABORT,'Shadow settlements are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_settlements_no_delete BEFORE DELETE ON shadow_evaluation_settlements BEGIN SELECT RAISE(ABORT,'Shadow settlements are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_metrics_no_update BEFORE UPDATE ON shadow_evaluation_metrics BEGIN SELECT RAISE(ABORT,'Shadow metrics are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_metrics_no_delete BEFORE DELETE ON shadow_evaluation_metrics BEGIN SELECT RAISE(ABORT,'Shadow metrics are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_aggregate_snapshots_no_update BEFORE UPDATE ON shadow_evaluation_aggregate_snapshots BEGIN SELECT RAISE(ABORT,'Shadow aggregates are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_aggregate_snapshots_no_delete BEFORE DELETE ON shadow_evaluation_aggregate_snapshots BEGIN SELECT RAISE(ABORT,'Shadow aggregates are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_exclusions_no_update BEFORE UPDATE ON shadow_evaluation_exclusions BEGIN SELECT RAISE(ABORT,'Shadow exclusions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS shadow_evaluation_exclusions_no_delete BEFORE DELETE ON shadow_evaluation_exclusions BEGIN SELECT RAISE(ABORT,'Shadow exclusions are immutable'); END""",
        ),
    ),
    Migration(
        version=31,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS model_activation_requests (
                activation_request_id TEXT PRIMARY KEY,
                model_scope TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                activation_plan_id TEXT NOT NULL UNIQUE,
                requested_timestamp_utc TEXT NOT NULL,
                request_snapshot TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_activation_plans (
                activation_plan_id TEXT PRIMARY KEY,
                activation_request_id TEXT NOT NULL UNIQUE,
                activation_plan_fingerprint TEXT NOT NULL UNIQUE,
                expected_generation_number INTEGER NOT NULL CHECK(expected_generation_number > 0),
                expected_registry_fingerprint TEXT NOT NULL,
                prepared_timestamp_utc TEXT NOT NULL,
                policy_snapshot TEXT NOT NULL,
                evidence_snapshot TEXT NOT NULL,
                plan_snapshot TEXT NOT NULL,
                FOREIGN KEY (activation_request_id) REFERENCES model_activation_requests(activation_request_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_rollback_requests (
                rollback_request_id TEXT PRIMARY KEY,
                model_scope TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                rollback_plan_id TEXT NOT NULL UNIQUE,
                requested_timestamp_utc TEXT NOT NULL,
                request_snapshot TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_rollback_plans (
                rollback_plan_id TEXT PRIMARY KEY,
                rollback_request_id TEXT NOT NULL UNIQUE,
                rollback_plan_fingerprint TEXT NOT NULL UNIQUE,
                expected_generation_number INTEGER NOT NULL CHECK(expected_generation_number > 0),
                expected_registry_fingerprint TEXT NOT NULL,
                prepared_timestamp_utc TEXT NOT NULL,
                policy_snapshot TEXT NOT NULL,
                target_champion_generation_id TEXT NOT NULL,
                plan_snapshot TEXT NOT NULL,
                FOREIGN KEY (rollback_request_id) REFERENCES model_rollback_requests(rollback_request_id),
                FOREIGN KEY (target_champion_generation_id) REFERENCES model_champion_generations(champion_generation_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_activation_validations (
                validation_id TEXT PRIMARY KEY,
                activation_plan_id TEXT,
                rollback_plan_id TEXT,
                category TEXT NOT NULL,
                validation_name TEXT NOT NULL,
                validation_status TEXT NOT NULL CHECK(validation_status IN ('PASS','WARNING','FAIL')),
                detail_snapshot TEXT NOT NULL,
                validation_fingerprint TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                FOREIGN KEY (activation_plan_id) REFERENCES model_activation_plans(activation_plan_id),
                FOREIGN KEY (rollback_plan_id) REFERENCES model_rollback_plans(rollback_plan_id),
                CHECK ((activation_plan_id IS NOT NULL) <> (rollback_plan_id IS NOT NULL)),
                UNIQUE (activation_plan_id,deterministic_order),
                UNIQUE (rollback_plan_id,deterministic_order)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_champion_generations (
                champion_generation_id TEXT PRIMARY KEY,
                model_scope TEXT NOT NULL,
                generation_number INTEGER NOT NULL CHECK(generation_number > 0),
                model_artifact_id TEXT NOT NULL,
                calibration_artifact_set_id TEXT NOT NULL,
                previous_champion_generation_id TEXT,
                activation_plan_id TEXT,
                rollback_plan_id TEXT,
                activation_timestamp_utc TEXT NOT NULL,
                generation_fingerprint TEXT NOT NULL UNIQUE,
                generation_snapshot TEXT NOT NULL,
                FOREIGN KEY (model_artifact_id) REFERENCES historical_model_artifacts(artifact_id),
                FOREIGN KEY (calibration_artifact_set_id) REFERENCES historical_probability_calibration_artifact_sets(artifact_set_id),
                FOREIGN KEY (previous_champion_generation_id) REFERENCES model_champion_generations(champion_generation_id),
                FOREIGN KEY (activation_plan_id) REFERENCES model_activation_plans(activation_plan_id),
                FOREIGN KEY (rollback_plan_id) REFERENCES model_rollback_plans(rollback_plan_id),
                UNIQUE (model_scope,generation_number),
                CHECK (NOT (activation_plan_id IS NOT NULL AND rollback_plan_id IS NOT NULL))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_champion_registry_events (
                registry_event_id TEXT PRIMARY KEY,
                model_scope TEXT NOT NULL,
                champion_generation_id TEXT NOT NULL,
                generation_number INTEGER NOT NULL,
                event_type TEXT NOT NULL CHECK(event_type IN ('INITIAL_REGISTERED','CHAMPION_ACTIVATED','CHAMPION_ROLLED_BACK','RETIRED_BY_ACTIVATION','RETIRED_BY_ROLLBACK')),
                operator_identity TEXT NOT NULL,
                event_timestamp_utc TEXT NOT NULL,
                event_fingerprint TEXT NOT NULL UNIQUE,
                FOREIGN KEY (champion_generation_id) REFERENCES model_champion_generations(champion_generation_id),
                UNIQUE (champion_generation_id,event_type)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_activation_executions (
                activation_execution_id TEXT PRIMARY KEY,
                activation_execution_request_id TEXT NOT NULL UNIQUE,
                activation_plan_id TEXT NOT NULL UNIQUE,
                activation_plan_fingerprint TEXT NOT NULL,
                champion_generation_id TEXT NOT NULL UNIQUE,
                execution_timestamp_utc TEXT NOT NULL,
                execution_fingerprint TEXT NOT NULL UNIQUE,
                FOREIGN KEY (activation_plan_id) REFERENCES model_activation_plans(activation_plan_id),
                FOREIGN KEY (champion_generation_id) REFERENCES model_champion_generations(champion_generation_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_rollback_executions (
                rollback_execution_id TEXT PRIMARY KEY,
                rollback_execution_request_id TEXT NOT NULL UNIQUE,
                rollback_plan_id TEXT NOT NULL UNIQUE,
                rollback_plan_fingerprint TEXT NOT NULL,
                champion_generation_id TEXT NOT NULL UNIQUE,
                execution_timestamp_utc TEXT NOT NULL,
                execution_fingerprint TEXT NOT NULL UNIQUE,
                FOREIGN KEY (rollback_plan_id) REFERENCES model_rollback_plans(rollback_plan_id),
                FOREIGN KEY (champion_generation_id) REFERENCES model_champion_generations(champion_generation_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_activation_evidence_links (
                evidence_link_id TEXT PRIMARY KEY,
                activation_plan_id TEXT NOT NULL,
                shadow_execution_id TEXT NOT NULL,
                shadow_execution_fingerprint TEXT NOT NULL,
                shadow_settlement_fingerprint TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                evidence_link_fingerprint TEXT NOT NULL UNIQUE,
                FOREIGN KEY (activation_plan_id) REFERENCES model_activation_plans(activation_plan_id),
                FOREIGN KEY (shadow_execution_id) REFERENCES shadow_evaluation_executions(shadow_execution_id),
                UNIQUE (activation_plan_id,deterministic_order),
                UNIQUE (activation_plan_id,shadow_execution_id)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_champion_scope_generation ON model_champion_generations(model_scope,generation_number DESC)""",
            """CREATE INDEX IF NOT EXISTS idx_champion_model ON model_champion_generations(model_artifact_id,activation_timestamp_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_activation_request_scope ON model_activation_requests(model_scope,requested_timestamp_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_rollback_request_scope ON model_rollback_requests(model_scope,requested_timestamp_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_activation_evidence_shadow ON model_activation_evidence_links(shadow_execution_id)""",
            """CREATE TRIGGER IF NOT EXISTS model_activation_requests_no_update BEFORE UPDATE ON model_activation_requests BEGIN SELECT RAISE(ABORT,'Activation requests are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_activation_requests_no_delete BEFORE DELETE ON model_activation_requests BEGIN SELECT RAISE(ABORT,'Activation requests are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_activation_plans_no_update BEFORE UPDATE ON model_activation_plans BEGIN SELECT RAISE(ABORT,'Activation plans are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_activation_plans_no_delete BEFORE DELETE ON model_activation_plans BEGIN SELECT RAISE(ABORT,'Activation plans are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_activation_validations_no_update BEFORE UPDATE ON model_activation_validations BEGIN SELECT RAISE(ABORT,'Activation validations are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_activation_validations_no_delete BEFORE DELETE ON model_activation_validations BEGIN SELECT RAISE(ABORT,'Activation validations are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_champion_generations_no_update BEFORE UPDATE ON model_champion_generations BEGIN SELECT RAISE(ABORT,'Champion generations are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_champion_generations_no_delete BEFORE DELETE ON model_champion_generations BEGIN SELECT RAISE(ABORT,'Champion generations are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_champion_registry_events_no_update BEFORE UPDATE ON model_champion_registry_events BEGIN SELECT RAISE(ABORT,'Champion events are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_champion_registry_events_no_delete BEFORE DELETE ON model_champion_registry_events BEGIN SELECT RAISE(ABORT,'Champion events are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_activation_executions_no_update BEFORE UPDATE ON model_activation_executions BEGIN SELECT RAISE(ABORT,'Activation executions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_activation_executions_no_delete BEFORE DELETE ON model_activation_executions BEGIN SELECT RAISE(ABORT,'Activation executions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_rollback_requests_no_update BEFORE UPDATE ON model_rollback_requests BEGIN SELECT RAISE(ABORT,'Rollback requests are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_rollback_requests_no_delete BEFORE DELETE ON model_rollback_requests BEGIN SELECT RAISE(ABORT,'Rollback requests are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_rollback_plans_no_update BEFORE UPDATE ON model_rollback_plans BEGIN SELECT RAISE(ABORT,'Rollback plans are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_rollback_plans_no_delete BEFORE DELETE ON model_rollback_plans BEGIN SELECT RAISE(ABORT,'Rollback plans are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_rollback_executions_no_update BEFORE UPDATE ON model_rollback_executions BEGIN SELECT RAISE(ABORT,'Rollback executions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_rollback_executions_no_delete BEFORE DELETE ON model_rollback_executions BEGIN SELECT RAISE(ABORT,'Rollback executions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_activation_evidence_links_no_update BEFORE UPDATE ON model_activation_evidence_links BEGIN SELECT RAISE(ABORT,'Activation evidence links are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS model_activation_evidence_links_no_delete BEFORE DELETE ON model_activation_evidence_links BEGIN SELECT RAISE(ABORT,'Activation evidence links are immutable'); END""",
        ),
    ),
    Migration(
        version=32,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS real_match_lab_analyses (
                analysis_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL UNIQUE,
                result_fingerprint TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('COMPLETED','NO_SELECTION','REJECTED','CONFLICT')),
                match_id TEXT NOT NULL,
                kickoff_utc TEXT NOT NULL,
                environment TEXT NOT NULL CHECK(environment='LAB'),
                scope TEXT NOT NULL CHECK(scope='OFFICIAL_GLOBAL'),
                destination_chat_id TEXT NOT NULL CHECK(destination_chat_id='-1003510920417'),
                destination_bot TEXT NOT NULL CHECK(destination_bot='@GoalVision_AI_Lab_Bot'),
                selected_market TEXT,
                message_html TEXT,
                message_fingerprint TEXT,
                request_snapshot TEXT NOT NULL,
                result_snapshot TEXT NOT NULL,
                created_at TEXT NOT NULL,
                CHECK ((status='COMPLETED')=(selected_market IS NOT NULL)),
                CHECK ((message_html IS NULL)=(message_fingerprint IS NULL))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS real_match_lab_market_evaluations (
                evaluation_id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                market TEXT NOT NULL,
                selected INTEGER NOT NULL CHECK(selected IN (0,1)),
                evaluation_fingerprint TEXT NOT NULL UNIQUE,
                evaluation_snapshot TEXT NOT NULL,
                FOREIGN KEY(analysis_id) REFERENCES real_match_lab_analyses(analysis_id),
                UNIQUE(analysis_id,deterministic_order),
                UNIQUE(analysis_id,market)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS real_match_lab_stage_events (
                event_id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                reason_code TEXT,
                event_fingerprint TEXT NOT NULL UNIQUE,
                event_snapshot TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(analysis_id) REFERENCES real_match_lab_analyses(analysis_id),
                UNIQUE(analysis_id,deterministic_order)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS real_match_lab_deliveries (
                delivery_id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL CHECK(attempt_number>0),
                event_sequence INTEGER NOT NULL CHECK(event_sequence IN (1,2)),
                status TEXT NOT NULL CHECK(status IN ('CLAIMED','SENT','FAILED','INDETERMINATE')),
                destination_chat_id TEXT NOT NULL CHECK(destination_chat_id='-1003510920417'),
                message_fingerprint TEXT NOT NULL,
                telegram_message_id INTEGER,
                reason_code TEXT,
                delivery_fingerprint TEXT NOT NULL UNIQUE,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(analysis_id) REFERENCES real_match_lab_analyses(analysis_id),
                UNIQUE(analysis_id,attempt_number,event_sequence),
                CHECK ((status='SENT')=(telegram_message_id IS NOT NULL))
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_real_match_lab_match ON real_match_lab_analyses(match_id,kickoff_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_real_match_lab_delivery ON real_match_lab_deliveries(analysis_id,attempt_number,event_sequence)""",
            """CREATE TRIGGER IF NOT EXISTS real_match_lab_analyses_no_update BEFORE UPDATE ON real_match_lab_analyses BEGIN SELECT RAISE(ABORT,'Real Match Lab analyses are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS real_match_lab_analyses_no_delete BEFORE DELETE ON real_match_lab_analyses BEGIN SELECT RAISE(ABORT,'Real Match Lab analyses are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS real_match_lab_market_evaluations_no_update BEFORE UPDATE ON real_match_lab_market_evaluations BEGIN SELECT RAISE(ABORT,'Real Match Lab evaluations are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS real_match_lab_market_evaluations_no_delete BEFORE DELETE ON real_match_lab_market_evaluations BEGIN SELECT RAISE(ABORT,'Real Match Lab evaluations are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS real_match_lab_stage_events_no_update BEFORE UPDATE ON real_match_lab_stage_events BEGIN SELECT RAISE(ABORT,'Real Match Lab events are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS real_match_lab_stage_events_no_delete BEFORE DELETE ON real_match_lab_stage_events BEGIN SELECT RAISE(ABORT,'Real Match Lab events are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS real_match_lab_deliveries_no_update BEFORE UPDATE ON real_match_lab_deliveries BEGIN SELECT RAISE(ABORT,'Real Match Lab deliveries are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS real_match_lab_deliveries_no_delete BEFORE DELETE ON real_match_lab_deliveries BEGIN SELECT RAISE(ABORT,'Real Match Lab deliveries are immutable'); END""",
        ),
    ),
    Migration(
        version=33,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS historical_source_reviews (
                source_review_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL UNIQUE,
                approval_status TEXT NOT NULL CHECK(approval_status IN (
                    'APPROVED_FOR_CONTROLLED_RESEARCH','APPROVED_FOR_INTERNAL_DERIVED_DATA',
                    'REVIEW_REQUIRED','REJECTED','ACCESS_UNAVAILABLE','TERMS_UNCLEAR'
                )),
                review_timestamp_utc TEXT NOT NULL,
                review_fingerprint TEXT NOT NULL UNIQUE,
                review_snapshot TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_source_manifests (
                source_manifest_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                source_version TEXT NOT NULL,
                acquisition_timestamp_utc TEXT NOT NULL,
                manifest_fingerprint TEXT NOT NULL UNIQUE,
                manifest_snapshot TEXT NOT NULL,
                FOREIGN KEY(source_id) REFERENCES historical_source_reviews(source_id),
                UNIQUE(source_id,source_version)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_source_files (
                source_file_id TEXT PRIMARY KEY,
                source_manifest_id TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL CHECK(deterministic_order>=0),
                file_name TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                byte_count INTEGER NOT NULL CHECK(byte_count>=0),
                row_count INTEGER NOT NULL CHECK(row_count>=0),
                file_snapshot TEXT NOT NULL,
                FOREIGN KEY(source_manifest_id) REFERENCES historical_source_manifests(source_manifest_id),
                UNIQUE(source_manifest_id,deterministic_order),
                UNIQUE(source_manifest_id,file_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_team_aliases (
                team_alias_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                source_team_id TEXT NOT NULL,
                competition TEXT NOT NULL,
                season TEXT NOT NULL,
                canonical_team_id TEXT NOT NULL,
                alias_fingerprint TEXT NOT NULL UNIQUE,
                alias_snapshot TEXT NOT NULL,
                FOREIGN KEY(source_id) REFERENCES historical_source_reviews(source_id),
                UNIQUE(source_id,source_team_id,competition,season)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_feature_coverage_reports (
                feature_coverage_report_id TEXT PRIMARY KEY,
                dataset_build_id TEXT NOT NULL,
                report_fingerprint TEXT NOT NULL UNIQUE,
                report_snapshot TEXT NOT NULL,
                created_timestamp_utc TEXT NOT NULL,
                FOREIGN KEY(dataset_build_id) REFERENCES historical_training_dataset_builds(dataset_build_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_data_quality_reports (
                data_quality_report_id TEXT PRIMARY KEY,
                source_manifest_id TEXT NOT NULL,
                report_fingerprint TEXT NOT NULL UNIQUE,
                report_snapshot TEXT NOT NULL,
                created_timestamp_utc TEXT NOT NULL,
                FOREIGN KEY(source_manifest_id) REFERENCES historical_source_manifests(source_manifest_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_leakage_audit_reports (
                leakage_audit_report_id TEXT PRIMARY KEY,
                dataset_build_id TEXT NOT NULL,
                audit_status TEXT NOT NULL CHECK(audit_status IN ('LEAKAGE_AUDIT_PASSED','LEAKAGE_AUDIT_BLOCKED')),
                report_fingerprint TEXT NOT NULL UNIQUE,
                report_snapshot TEXT NOT NULL,
                audit_timestamp_utc TEXT NOT NULL,
                FOREIGN KEY(dataset_build_id) REFERENCES historical_training_dataset_builds(dataset_build_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_evidence_tiers (
                evidence_tier_record_id TEXT PRIMARY KEY,
                artifact_type TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                evidence_tier TEXT NOT NULL CHECK(evidence_tier IN ('CONTROLLED_SYNTHETIC','REVIEWED_REAL_HISTORICAL','PRODUCTION_AUTHORIZED')),
                publication_eligible INTEGER NOT NULL CHECK(publication_eligible IN (0,1)),
                authorization_reference TEXT,
                tier_fingerprint TEXT NOT NULL UNIQUE,
                tier_snapshot TEXT NOT NULL,
                created_timestamp_utc TEXT NOT NULL,
                UNIQUE(artifact_type,artifact_id),
                CHECK(evidence_tier='PRODUCTION_AUTHORIZED' OR publication_eligible=0),
                CHECK(evidence_tier!='PRODUCTION_AUTHORIZED' OR authorization_reference IS NOT NULL)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_source_manifest_source ON historical_source_manifests(source_id,source_version)""",
            """CREATE INDEX IF NOT EXISTS idx_team_alias_source ON historical_team_aliases(source_id,source_team_id,competition,season)""",
            """CREATE TRIGGER IF NOT EXISTS historical_source_reviews_no_update BEFORE UPDATE ON historical_source_reviews BEGIN SELECT RAISE(ABORT,'Historical source reviews are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_source_reviews_no_delete BEFORE DELETE ON historical_source_reviews BEGIN SELECT RAISE(ABORT,'Historical source reviews are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_source_manifests_no_update BEFORE UPDATE ON historical_source_manifests BEGIN SELECT RAISE(ABORT,'Historical source manifests are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_source_manifests_no_delete BEFORE DELETE ON historical_source_manifests BEGIN SELECT RAISE(ABORT,'Historical source manifests are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_source_files_no_update BEFORE UPDATE ON historical_source_files BEGIN SELECT RAISE(ABORT,'Historical source files are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_source_files_no_delete BEFORE DELETE ON historical_source_files BEGIN SELECT RAISE(ABORT,'Historical source files are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_team_aliases_no_update BEFORE UPDATE ON historical_team_aliases BEGIN SELECT RAISE(ABORT,'Historical team aliases are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_team_aliases_no_delete BEFORE DELETE ON historical_team_aliases BEGIN SELECT RAISE(ABORT,'Historical team aliases are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_feature_coverage_reports_no_update BEFORE UPDATE ON historical_feature_coverage_reports BEGIN SELECT RAISE(ABORT,'Historical feature coverage reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_feature_coverage_reports_no_delete BEFORE DELETE ON historical_feature_coverage_reports BEGIN SELECT RAISE(ABORT,'Historical feature coverage reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_data_quality_reports_no_update BEFORE UPDATE ON historical_data_quality_reports BEGIN SELECT RAISE(ABORT,'Historical data quality reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_data_quality_reports_no_delete BEFORE DELETE ON historical_data_quality_reports BEGIN SELECT RAISE(ABORT,'Historical data quality reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_leakage_audit_reports_no_update BEFORE UPDATE ON historical_leakage_audit_reports BEGIN SELECT RAISE(ABORT,'Historical leakage audit reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_leakage_audit_reports_no_delete BEFORE DELETE ON historical_leakage_audit_reports BEGIN SELECT RAISE(ABORT,'Historical leakage audit reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_evidence_tiers_no_update BEFORE UPDATE ON historical_evidence_tiers BEGIN SELECT RAISE(ABORT,'Historical evidence tiers are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_evidence_tiers_no_delete BEFORE DELETE ON historical_evidence_tiers BEGIN SELECT RAISE(ABORT,'Historical evidence tiers are immutable'); END""",
        ),
    ),
    Migration(
        version=34,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS historical_odds_source_reviews (
                odds_source_review_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL UNIQUE,
                approval_status TEXT NOT NULL CHECK(approval_status IN (
                    'APPROVED_FOR_CONTROLLED_RESEARCH','APPROVED_FOR_INTERNAL_DERIVED_DATA',
                    'REVIEW_REQUIRED','REJECTED','ACCESS_UNAVAILABLE','TERMS_UNCLEAR'
                )),
                review_timestamp_utc TEXT NOT NULL,
                review_fingerprint TEXT NOT NULL UNIQUE,
                review_snapshot TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_odds_source_manifests (
                odds_manifest_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                source_version TEXT NOT NULL,
                acquisition_timestamp_utc TEXT NOT NULL,
                manifest_fingerprint TEXT NOT NULL UNIQUE,
                manifest_snapshot TEXT NOT NULL,
                FOREIGN KEY(source_id) REFERENCES historical_odds_source_reviews(source_id),
                UNIQUE(source_id,source_version)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_odds_source_files (
                odds_source_file_id TEXT PRIMARY KEY,
                odds_manifest_id TEXT NOT NULL,
                deterministic_order INTEGER NOT NULL CHECK(deterministic_order>=0),
                file_name TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                byte_count INTEGER NOT NULL CHECK(byte_count>=0),
                raw_row_count INTEGER NOT NULL CHECK(raw_row_count>=0),
                file_snapshot TEXT NOT NULL,
                FOREIGN KEY(odds_manifest_id) REFERENCES historical_odds_source_manifests(odds_manifest_id),
                UNIQUE(odds_manifest_id,deterministic_order),
                UNIQUE(odds_manifest_id,file_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_odds_event_links (
                event_link_id TEXT PRIMARY KEY,
                odds_manifest_id TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                historical_match_id TEXT,
                link_status TEXT NOT NULL CHECK(link_status IN (
                    'EXACT_MATCH','REVIEWED_ALIAS_MATCH','TIMESTAMP_TOLERANCE_MATCH',
                    'AMBIGUOUS_MATCH','NO_MATCH','CONFLICTING_MATCH'
                )),
                link_fingerprint TEXT NOT NULL UNIQUE,
                link_snapshot TEXT NOT NULL,
                FOREIGN KEY(odds_manifest_id) REFERENCES historical_odds_source_manifests(odds_manifest_id),
                FOREIGN KEY(historical_match_id) REFERENCES historical_matches(historical_match_id),
                UNIQUE(odds_manifest_id,source_event_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_odds_quotes (
                quote_id TEXT PRIMARY KEY,
                odds_manifest_id TEXT NOT NULL,
                event_link_id TEXT NOT NULL,
                historical_match_id TEXT NOT NULL,
                source_quote_id TEXT NOT NULL,
                canonical_market TEXT NOT NULL,
                decimal_odds TEXT NOT NULL,
                captured_at_utc TEXT NOT NULL,
                kickoff_utc TEXT NOT NULL,
                quote_fingerprint TEXT NOT NULL UNIQUE,
                quote_snapshot TEXT NOT NULL,
                FOREIGN KEY(odds_manifest_id) REFERENCES historical_odds_source_manifests(odds_manifest_id),
                FOREIGN KEY(event_link_id) REFERENCES historical_odds_event_links(event_link_id),
                FOREIGN KEY(historical_match_id) REFERENCES historical_matches(historical_match_id),
                UNIQUE(odds_manifest_id,source_quote_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_odds_quote_selections (
                quote_selection_id TEXT PRIMARY KEY,
                odds_manifest_id TEXT NOT NULL,
                historical_match_id TEXT NOT NULL,
                canonical_market TEXT NOT NULL,
                selected_quote_id TEXT NOT NULL,
                cutoff_timestamp_utc TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                selection_fingerprint TEXT NOT NULL UNIQUE,
                selection_snapshot TEXT NOT NULL,
                FOREIGN KEY(odds_manifest_id) REFERENCES historical_odds_source_manifests(odds_manifest_id),
                FOREIGN KEY(historical_match_id) REFERENCES historical_matches(historical_match_id),
                FOREIGN KEY(selected_quote_id) REFERENCES historical_odds_quotes(quote_id),
                UNIQUE(odds_manifest_id,historical_match_id,canonical_market,policy_version)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_odds_coverage_reports (
                coverage_report_id TEXT PRIMARY KEY,
                odds_manifest_id TEXT NOT NULL,
                report_fingerprint TEXT NOT NULL UNIQUE,
                report_snapshot TEXT NOT NULL,
                created_timestamp_utc TEXT NOT NULL,
                FOREIGN KEY(odds_manifest_id) REFERENCES historical_odds_source_manifests(odds_manifest_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS reviewed_odds_backtest_integrity_reports (
                integrity_report_id TEXT PRIMARY KEY,
                odds_manifest_id TEXT NOT NULL,
                integrity_status TEXT NOT NULL CHECK(integrity_status IN ('BACKTEST_INTEGRITY_PASSED','BACKTEST_INTEGRITY_BLOCKED')),
                report_fingerprint TEXT NOT NULL UNIQUE,
                report_snapshot TEXT NOT NULL,
                created_timestamp_utc TEXT NOT NULL,
                FOREIGN KEY(odds_manifest_id) REFERENCES historical_odds_source_manifests(odds_manifest_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_betting_evidence_summaries (
                betting_evidence_id TEXT PRIMARY KEY,
                odds_manifest_id TEXT NOT NULL,
                evidence_status TEXT NOT NULL,
                evidence_fingerprint TEXT NOT NULL UNIQUE,
                evidence_snapshot TEXT NOT NULL,
                created_timestamp_utc TEXT NOT NULL,
                FOREIGN KEY(odds_manifest_id) REFERENCES historical_odds_source_manifests(odds_manifest_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_odds_shadow_summaries (
                shadow_summary_id TEXT PRIMARY KEY,
                odds_manifest_id TEXT NOT NULL,
                shadow_status TEXT NOT NULL,
                summary_fingerprint TEXT NOT NULL UNIQUE,
                summary_snapshot TEXT NOT NULL,
                created_timestamp_utc TEXT NOT NULL,
                FOREIGN KEY(odds_manifest_id) REFERENCES historical_odds_source_manifests(odds_manifest_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_odds_audit_reports (
                odds_audit_id TEXT PRIMARY KEY,
                odds_manifest_id TEXT NOT NULL,
                audit_status TEXT NOT NULL CHECK(audit_status IN ('AUDIT_PASSED','AUDIT_BLOCKED')),
                audit_fingerprint TEXT NOT NULL UNIQUE,
                audit_snapshot TEXT NOT NULL,
                created_timestamp_utc TEXT NOT NULL,
                FOREIGN KEY(odds_manifest_id) REFERENCES historical_odds_source_manifests(odds_manifest_id)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_historical_odds_quotes_match ON historical_odds_quotes(historical_match_id,canonical_market,captured_at_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_historical_odds_links_source ON historical_odds_event_links(odds_manifest_id,source_event_id)""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_source_reviews_no_update BEFORE UPDATE ON historical_odds_source_reviews BEGIN SELECT RAISE(ABORT,'Historical odds source reviews are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_source_reviews_no_delete BEFORE DELETE ON historical_odds_source_reviews BEGIN SELECT RAISE(ABORT,'Historical odds source reviews are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_source_manifests_no_update BEFORE UPDATE ON historical_odds_source_manifests BEGIN SELECT RAISE(ABORT,'Historical odds source manifests are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_source_manifests_no_delete BEFORE DELETE ON historical_odds_source_manifests BEGIN SELECT RAISE(ABORT,'Historical odds source manifests are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_source_files_no_update BEFORE UPDATE ON historical_odds_source_files BEGIN SELECT RAISE(ABORT,'Historical odds source files are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_source_files_no_delete BEFORE DELETE ON historical_odds_source_files BEGIN SELECT RAISE(ABORT,'Historical odds source files are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_event_links_no_update BEFORE UPDATE ON historical_odds_event_links BEGIN SELECT RAISE(ABORT,'Historical odds event links are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_event_links_no_delete BEFORE DELETE ON historical_odds_event_links BEGIN SELECT RAISE(ABORT,'Historical odds event links are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_quotes_no_update BEFORE UPDATE ON historical_odds_quotes BEGIN SELECT RAISE(ABORT,'Historical odds quotes are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_quotes_no_delete BEFORE DELETE ON historical_odds_quotes BEGIN SELECT RAISE(ABORT,'Historical odds quotes are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_quote_selections_no_update BEFORE UPDATE ON historical_odds_quote_selections BEGIN SELECT RAISE(ABORT,'Historical odds quote selections are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_quote_selections_no_delete BEFORE DELETE ON historical_odds_quote_selections BEGIN SELECT RAISE(ABORT,'Historical odds quote selections are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_coverage_reports_no_update BEFORE UPDATE ON historical_odds_coverage_reports BEGIN SELECT RAISE(ABORT,'Historical odds coverage reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_coverage_reports_no_delete BEFORE DELETE ON historical_odds_coverage_reports BEGIN SELECT RAISE(ABORT,'Historical odds coverage reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS reviewed_odds_backtest_integrity_reports_no_update BEFORE UPDATE ON reviewed_odds_backtest_integrity_reports BEGIN SELECT RAISE(ABORT,'Historical backtest integrity reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS reviewed_odds_backtest_integrity_reports_no_delete BEFORE DELETE ON reviewed_odds_backtest_integrity_reports BEGIN SELECT RAISE(ABORT,'Historical backtest integrity reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_betting_evidence_summaries_no_update BEFORE UPDATE ON historical_betting_evidence_summaries BEGIN SELECT RAISE(ABORT,'Historical betting evidence summaries are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_betting_evidence_summaries_no_delete BEFORE DELETE ON historical_betting_evidence_summaries BEGIN SELECT RAISE(ABORT,'Historical betting evidence summaries are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_shadow_summaries_no_update BEFORE UPDATE ON historical_odds_shadow_summaries BEGIN SELECT RAISE(ABORT,'Historical odds shadow summaries are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_shadow_summaries_no_delete BEFORE DELETE ON historical_odds_shadow_summaries BEGIN SELECT RAISE(ABORT,'Historical odds shadow summaries are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_audit_reports_no_update BEFORE UPDATE ON historical_odds_audit_reports BEGIN SELECT RAISE(ABORT,'Historical odds audit reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_audit_reports_no_delete BEFORE DELETE ON historical_odds_audit_reports BEGIN SELECT RAISE(ABORT,'Historical odds audit reports are immutable'); END""",
        ),
    ),
    Migration(
        version=35,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS historical_odds_source_review_versions (
                odds_source_review_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                approval_status TEXT NOT NULL CHECK(approval_status IN (
                    'APPROVED_FOR_CONTROLLED_RESEARCH','APPROVED_FOR_INTERNAL_DERIVED_DATA',
                    'REVIEW_REQUIRED','REJECTED','ACCESS_UNAVAILABLE','TERMS_UNCLEAR'
                )),
                review_timestamp_utc TEXT NOT NULL,
                review_fingerprint TEXT NOT NULL UNIQUE,
                supersedes_review_id TEXT,
                review_snapshot TEXT NOT NULL,
                FOREIGN KEY(supersedes_review_id)
                    REFERENCES historical_odds_source_review_versions(odds_source_review_id),
                UNIQUE(source_id,review_timestamp_utc)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_odds_acquisition_windows (
                acquisition_window_id TEXT PRIMARY KEY,
                split_id TEXT NOT NULL,
                split_fingerprint TEXT NOT NULL,
                equal_kickoff_grouping_policy TEXT NOT NULL,
                train_start_utc TEXT NOT NULL,
                train_end_utc TEXT NOT NULL,
                validation_start_utc TEXT NOT NULL,
                validation_end_utc TEXT NOT NULL,
                test_start_utc TEXT NOT NULL,
                test_end_utc TEXT NOT NULL,
                train_match_count INTEGER NOT NULL CHECK(train_match_count>=0),
                validation_match_count INTEGER NOT NULL CHECK(validation_match_count>=0),
                test_match_count INTEGER NOT NULL CHECK(test_match_count>=0),
                temporal_gap_count INTEGER NOT NULL CHECK(temporal_gap_count>=0),
                window_fingerprint TEXT NOT NULL UNIQUE,
                window_snapshot TEXT NOT NULL,
                created_timestamp_utc TEXT NOT NULL,
                UNIQUE(split_id,split_fingerprint)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS historical_odds_partition_coverage_reports (
                partition_coverage_report_id TEXT PRIMARY KEY,
                acquisition_window_id TEXT NOT NULL,
                odds_manifest_id TEXT,
                coverage_status TEXT NOT NULL CHECK(coverage_status IN (
                    'SUFFICIENT_TEST_ODDS_COVERAGE','INSUFFICIENT_TEST_ODDS_COVERAGE',
                    'REVIEWED_TEST_ODDS_COVERAGE_UNAVAILABLE'
                )),
                validation_matches_with_odds INTEGER NOT NULL CHECK(validation_matches_with_odds>=0),
                test_matches_with_odds INTEGER NOT NULL CHECK(test_matches_with_odds>=0),
                test_candidate_market_count INTEGER NOT NULL CHECK(test_candidate_market_count>=0),
                ambiguous_event_count INTEGER NOT NULL CHECK(ambiguous_event_count>=0),
                post_kickoff_exclusion_count INTEGER NOT NULL CHECK(post_kickoff_exclusion_count>=0),
                report_fingerprint TEXT NOT NULL UNIQUE,
                report_snapshot TEXT NOT NULL,
                created_timestamp_utc TEXT NOT NULL,
                FOREIGN KEY(acquisition_window_id)
                    REFERENCES historical_odds_acquisition_windows(acquisition_window_id),
                FOREIGN KEY(odds_manifest_id)
                    REFERENCES historical_odds_source_manifests(odds_manifest_id)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_odds_review_versions_source ON historical_odds_source_review_versions(source_id,review_timestamp_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_odds_partition_coverage_window ON historical_odds_partition_coverage_reports(acquisition_window_id,created_timestamp_utc)""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_source_review_versions_no_update BEFORE UPDATE ON historical_odds_source_review_versions BEGIN SELECT RAISE(ABORT,'Historical odds source review versions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_source_review_versions_no_delete BEFORE DELETE ON historical_odds_source_review_versions BEGIN SELECT RAISE(ABORT,'Historical odds source review versions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_acquisition_windows_no_update BEFORE UPDATE ON historical_odds_acquisition_windows BEGIN SELECT RAISE(ABORT,'Historical odds acquisition windows are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_acquisition_windows_no_delete BEFORE DELETE ON historical_odds_acquisition_windows BEGIN SELECT RAISE(ABORT,'Historical odds acquisition windows are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_partition_coverage_reports_no_update BEFORE UPDATE ON historical_odds_partition_coverage_reports BEGIN SELECT RAISE(ABORT,'Historical odds partition coverage reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS historical_odds_partition_coverage_reports_no_delete BEFORE DELETE ON historical_odds_partition_coverage_reports BEGIN SELECT RAISE(ABORT,'Historical odds partition coverage reports are immutable'); END""",
        ),
    ),
    Migration(
        version=36,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS forward_test_odds_snapshots (
                odds_snapshot_id TEXT PRIMARY KEY,
                canonical_fixture_id TEXT NOT NULL,
                kickoff_utc TEXT NOT NULL,
                provider_source_id TEXT NOT NULL,
                provider_type TEXT NOT NULL,
                bookmaker_name TEXT NOT NULL,
                source_selected_at_utc TEXT NOT NULL,
                captured_at_utc TEXT NOT NULL,
                sealed_at_utc TEXT NOT NULL,
                freshness_status TEXT NOT NULL CHECK(freshness_status IN ('FRESH','AGING')),
                snapshot_fingerprint TEXT NOT NULL UNIQUE,
                snapshot_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_observations (
                observation_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL UNIQUE,
                analysis_id TEXT NOT NULL UNIQUE,
                odds_snapshot_id TEXT NOT NULL,
                canonical_fixture_id TEXT NOT NULL,
                evidence_tier TEXT NOT NULL CHECK(evidence_tier='FORWARD_TEST_REAL_TIME'),
                status TEXT NOT NULL CHECK(status IN ('ANALYSIS_COMPLETED','NO_SELECTION','BLOCKED')),
                actionable INTEGER NOT NULL CHECK(actionable IN (0,1)),
                preview_available INTEGER NOT NULL CHECK(preview_available IN (0,1)),
                lab_send_eligible INTEGER NOT NULL CHECK(lab_send_eligible=0),
                official_eligible INTEGER NOT NULL CHECK(official_eligible=0),
                observation_fingerprint TEXT NOT NULL UNIQUE,
                observation_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY(analysis_id) REFERENCES real_match_lab_analyses(analysis_id),
                FOREIGN KEY(odds_snapshot_id) REFERENCES forward_test_odds_snapshots(odds_snapshot_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_results (
                result_id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL UNIQUE,
                canonical_fixture_id TEXT NOT NULL,
                final_home_score INTEGER NOT NULL CHECK(final_home_score BETWEEN 0 AND 30),
                final_away_score INTEGER NOT NULL CHECK(final_away_score BETWEEN 0 AND 30),
                final_status TEXT NOT NULL,
                result_retrieval_timestamp_utc TEXT NOT NULL,
                result_fingerprint TEXT NOT NULL UNIQUE,
                result_json TEXT NOT NULL,
                FOREIGN KEY(observation_id) REFERENCES forward_test_observations(observation_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_settlements (
                settlement_id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL UNIQUE,
                result_id TEXT NOT NULL UNIQUE,
                outcome TEXT NOT NULL CHECK(outcome IN ('WON','LOST','VOID','UNSETTLED','NOT_APPLICABLE')),
                market TEXT,
                settlement_fingerprint TEXT NOT NULL UNIQUE,
                settlement_json TEXT NOT NULL,
                settled_at_utc TEXT NOT NULL,
                FOREIGN KEY(observation_id) REFERENCES forward_test_observations(observation_id),
                FOREIGN KEY(result_id) REFERENCES forward_test_results(result_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_events (
                event_id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL,
                event_sequence INTEGER NOT NULL CHECK(event_sequence>=0),
                event_type TEXT NOT NULL,
                event_fingerprint TEXT NOT NULL UNIQUE,
                event_json TEXT NOT NULL,
                occurred_at_utc TEXT NOT NULL,
                FOREIGN KEY(observation_id) REFERENCES forward_test_observations(observation_id),
                UNIQUE(observation_id,event_sequence)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_rejections (
                rejection_id TEXT PRIMARY KEY,
                request_fingerprint TEXT NOT NULL,
                stage TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                rejection_fingerprint TEXT NOT NULL UNIQUE,
                rejection_json TEXT NOT NULL,
                occurred_at_utc TEXT NOT NULL,
                UNIQUE(request_fingerprint,stage,reason_code)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_forward_test_fixture ON forward_test_observations(canonical_fixture_id,created_at_utc)""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_odds_snapshots_no_update BEFORE UPDATE ON forward_test_odds_snapshots BEGIN SELECT RAISE(ABORT,'Forward-test odds snapshots are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_odds_snapshots_no_delete BEFORE DELETE ON forward_test_odds_snapshots BEGIN SELECT RAISE(ABORT,'Forward-test odds snapshots are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_observations_no_update BEFORE UPDATE ON forward_test_observations BEGIN SELECT RAISE(ABORT,'Forward-test observations are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_observations_no_delete BEFORE DELETE ON forward_test_observations BEGIN SELECT RAISE(ABORT,'Forward-test observations are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_results_no_update BEFORE UPDATE ON forward_test_results BEGIN SELECT RAISE(ABORT,'Forward-test results are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_results_no_delete BEFORE DELETE ON forward_test_results BEGIN SELECT RAISE(ABORT,'Forward-test results are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_settlements_no_update BEFORE UPDATE ON forward_test_settlements BEGIN SELECT RAISE(ABORT,'Forward-test settlements are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_settlements_no_delete BEFORE DELETE ON forward_test_settlements BEGIN SELECT RAISE(ABORT,'Forward-test settlements are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_events_no_update BEFORE UPDATE ON forward_test_events BEGIN SELECT RAISE(ABORT,'Forward-test events are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_events_no_delete BEFORE DELETE ON forward_test_events BEGIN SELECT RAISE(ABORT,'Forward-test events are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_rejections_no_update BEFORE UPDATE ON forward_test_rejections BEGIN SELECT RAISE(ABORT,'Forward-test rejections are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_rejections_no_delete BEFORE DELETE ON forward_test_rejections BEGIN SELECT RAISE(ABORT,'Forward-test rejections are immutable'); END""",
        ),
    ),
    Migration(
        version=37,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS first_lab_run_executions (
                run_id TEXT PRIMARY KEY,
                request_fingerprint TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL CHECK(mode IN ('GENUINE','CONTROLLED_REHEARSAL')),
                execution_state TEXT NOT NULL CHECK(execution_state='STARTED'),
                created_at_utc TEXT NOT NULL,
                run_fingerprint TEXT NOT NULL UNIQUE,
                run_snapshot TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS first_lab_run_stage_events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                stage_order INTEGER NOT NULL CHECK(stage_order>=0),
                stage_name TEXT NOT NULL,
                stage_status TEXT NOT NULL CHECK(stage_status IN ('PASSED','BLOCKED','COMPLETED')),
                artifact_type TEXT,
                artifact_id TEXT,
                artifact_fingerprint TEXT,
                occurred_at_utc TEXT NOT NULL,
                event_fingerprint TEXT NOT NULL UNIQUE,
                event_snapshot TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES first_lab_run_executions(run_id),
                UNIQUE(run_id,stage_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_publication_reviews (
                review_id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL,
                review_status TEXT NOT NULL CHECK(review_status IN (
                    'LAB_PUBLICATION_REVIEW_PASSED','LAB_PUBLICATION_REVIEW_BLOCKED',
                    'LAB_PUBLICATION_REVIEW_REQUIRED'
                )),
                message_fingerprint TEXT,
                reviewed_at_utc TEXT NOT NULL,
                review_fingerprint TEXT NOT NULL UNIQUE,
                review_snapshot TEXT NOT NULL,
                FOREIGN KEY(observation_id) REFERENCES forward_test_observations(observation_id),
                UNIQUE(observation_id,review_fingerprint)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_result_previews (
                preview_id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL,
                settlement_id TEXT NOT NULL,
                preview_fingerprint TEXT NOT NULL UNIQUE,
                preview_snapshot TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY(observation_id) REFERENCES forward_test_observations(observation_id),
                FOREIGN KEY(settlement_id) REFERENCES forward_test_settlements(settlement_id),
                UNIQUE(observation_id,settlement_id)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_first_lab_stage_run ON first_lab_run_stage_events(run_id,stage_order)""",
            """CREATE INDEX IF NOT EXISTS idx_forward_test_review_observation ON forward_test_publication_reviews(observation_id,reviewed_at_utc)""",
            """CREATE TRIGGER IF NOT EXISTS first_lab_run_executions_no_update BEFORE UPDATE ON first_lab_run_executions BEGIN SELECT RAISE(ABORT,'First Lab run executions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS first_lab_run_executions_no_delete BEFORE DELETE ON first_lab_run_executions BEGIN SELECT RAISE(ABORT,'First Lab run executions are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS first_lab_run_stage_events_no_update BEFORE UPDATE ON first_lab_run_stage_events BEGIN SELECT RAISE(ABORT,'First Lab run stage events are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS first_lab_run_stage_events_no_delete BEFORE DELETE ON first_lab_run_stage_events BEGIN SELECT RAISE(ABORT,'First Lab run stage events are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_publication_reviews_no_update BEFORE UPDATE ON forward_test_publication_reviews BEGIN SELECT RAISE(ABORT,'Forward-test publication reviews are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_publication_reviews_no_delete BEFORE DELETE ON forward_test_publication_reviews BEGIN SELECT RAISE(ABORT,'Forward-test publication reviews are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_result_previews_no_update BEFORE UPDATE ON forward_test_result_previews BEGIN SELECT RAISE(ABORT,'Forward-test result previews are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS forward_test_result_previews_no_delete BEFORE DELETE ON forward_test_result_previews BEGIN SELECT RAISE(ABORT,'Forward-test result previews are immutable'); END""",
        ),
    ),
    Migration(
        version=38,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS forward_test_monitoring_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                requested_cutoff_utc TEXT NOT NULL,
                generated_at_utc TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                source_database_identity TEXT NOT NULL,
                source_fingerprint TEXT NOT NULL,
                snapshot_fingerprint TEXT NOT NULL UNIQUE,
                snapshot_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_monitoring_reports (
                report_id TEXT PRIMARY KEY,
                report_kind TEXT NOT NULL CHECK(report_kind IN ('WEEKLY','CUMULATIVE')),
                period_start_utc TEXT,
                period_end_utc TEXT NOT NULL,
                generated_at_utc TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL UNIQUE,
                report_fingerprint TEXT NOT NULL UNIQUE,
                report_json TEXT NOT NULL,
                FOREIGN KEY(snapshot_id) REFERENCES forward_test_monitoring_snapshots(snapshot_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_monitoring_audits (
                audit_id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL,
                cutoff_utc TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('LIFECYCLE_AUDIT_PASSED','LIFECYCLE_AUDIT_WARNING','LIFECYCLE_AUDIT_BLOCKED','LIFECYCLE_AUDIT_CORRUPT')),
                audit_fingerprint TEXT NOT NULL UNIQUE,
                audit_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY(observation_id) REFERENCES forward_test_observations(observation_id),
                UNIQUE(observation_id,cutoff_utc)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_monitoring_incidents (
                incident_id TEXT PRIMARY KEY,
                incident_code TEXT NOT NULL,
                severity TEXT NOT NULL CHECK(severity IN ('INFO','WARNING','BLOCKING','CORRUPT')),
                affected_identifier TEXT,
                detected_at_utc TEXT NOT NULL,
                incident_fingerprint TEXT NOT NULL UNIQUE,
                incident_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_monitoring_incident_events (
                event_id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK(event_type IN ('ACKNOWLEDGED','RESOLVED')),
                operator_identity TEXT NOT NULL,
                reason TEXT NOT NULL,
                occurred_at_utc TEXT NOT NULL,
                event_fingerprint TEXT NOT NULL UNIQUE,
                event_json TEXT NOT NULL,
                FOREIGN KEY(incident_id) REFERENCES forward_test_monitoring_incidents(incident_id),
                UNIQUE(incident_id,event_type)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forward_test_monitoring_exports (
                export_id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                export_format TEXT NOT NULL CHECK(export_format IN ('JSON','MARKDOWN','TELEGRAM_PREVIEW','CSV_BUNDLE')),
                content_fingerprint TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                export_fingerprint TEXT NOT NULL UNIQUE,
                export_json TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES forward_test_monitoring_reports(report_id),
                UNIQUE(report_id,export_format,relative_path)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_ft_monitoring_reports_period ON forward_test_monitoring_reports(report_kind,period_end_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_ft_monitoring_audits_observation ON forward_test_monitoring_audits(observation_id,cutoff_utc)""",
            """CREATE INDEX IF NOT EXISTS idx_ft_monitoring_incidents_code ON forward_test_monitoring_incidents(incident_code,detected_at_utc)""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_snapshots_no_update BEFORE UPDATE ON forward_test_monitoring_snapshots BEGIN SELECT RAISE(ABORT,'Forward-test monitoring snapshots are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_snapshots_no_delete BEFORE DELETE ON forward_test_monitoring_snapshots BEGIN SELECT RAISE(ABORT,'Forward-test monitoring snapshots are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_reports_no_update BEFORE UPDATE ON forward_test_monitoring_reports BEGIN SELECT RAISE(ABORT,'Forward-test monitoring reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_reports_no_delete BEFORE DELETE ON forward_test_monitoring_reports BEGIN SELECT RAISE(ABORT,'Forward-test monitoring reports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_audits_no_update BEFORE UPDATE ON forward_test_monitoring_audits BEGIN SELECT RAISE(ABORT,'Forward-test monitoring audits are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_audits_no_delete BEFORE DELETE ON forward_test_monitoring_audits BEGIN SELECT RAISE(ABORT,'Forward-test monitoring audits are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_incidents_no_update BEFORE UPDATE ON forward_test_monitoring_incidents BEGIN SELECT RAISE(ABORT,'Forward-test monitoring incidents are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_incidents_no_delete BEFORE DELETE ON forward_test_monitoring_incidents BEGIN SELECT RAISE(ABORT,'Forward-test monitoring incidents are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_incident_events_no_update BEFORE UPDATE ON forward_test_monitoring_incident_events BEGIN SELECT RAISE(ABORT,'Forward-test monitoring incident events are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_incident_events_no_delete BEFORE DELETE ON forward_test_monitoring_incident_events BEGIN SELECT RAISE(ABORT,'Forward-test monitoring incident events are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_exports_no_update BEFORE UPDATE ON forward_test_monitoring_exports BEGIN SELECT RAISE(ABORT,'Forward-test monitoring exports are immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS ft_monitoring_exports_no_delete BEFORE DELETE ON forward_test_monitoring_exports BEGIN SELECT RAISE(ABORT,'Forward-test monitoring exports are immutable'); END""",
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
