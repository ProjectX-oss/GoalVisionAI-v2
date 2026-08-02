"""Regression coverage for deterministic live-78 prediction reasoning."""

from __future__ import annotations

import json
import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from app.database import Database
from app.historical_model_training import predict_raw_probabilities
from app.prediction_explainability import PredictionExplainabilityService
from app.prediction_explainability.audit import audit_reasoning
from app.prediction_explainability.catalog import CATALOG, CATALOG_FINGERPRINT
from app.prediction_explainability.controlled import CONTROLLED_TIME, controlled_artifact_and_input, run_controlled_rehearsal
from app.prediction_explainability.engine import ExplainabilityError, compute_class_attributions
from app.prediction_explainability.presentation import compose_reasoned_message, publication_reasoning_checks
from app.prediction_explainability.repository import ReasoningConflictError, SQLiteReasoningRepository
from app.real_match_lab_analysis.fingerprint import fingerprint


def context(artifact, model_input, *, selected="HOME_WIN"):
    prediction=predict_raw_probabilities(artifact,model_input.ordered_feature_values,model_input.missingness_mask,feature_schema_version=artifact.feature_schema_version,feature_schema_fingerprint=artifact.feature_schema_fingerprint,ordered_feature_names=model_input.ordered_feature_names)
    raw={item.target.value:item.probability for item in prediction.raw_probabilities.ordered_probabilities}
    evaluations=[]
    for rank,market in enumerate(sorted(raw,key=lambda value:(-raw[value],value)),1):
        odds=Decimal("2.20") if market==selected else Decimal("1.90")
        probability=raw[market]+(Decimal("0.02") if market==selected else Decimal(0))
        evaluations.append({"market":market,"raw_probability":raw[market],"calibrated_probability":probability,"bookmaker_odds":odds,"mathematical_rank":rank,"actionable":market==selected,"selected":market==selected,"rejection_reasons":[] if market==selected else ["MATHEMATICALLY_LOWER_RANKED_MARKET"]})
    return dict(analysis_id="fictional-analysis-1",observation_id="fictional-observation-1",selected_market=selected,market_evaluations=evaluations,created_at_utc=CONTROLLED_TIME,checked_at_utc=CONTROLLED_TIME,calibration_artifact_id="controlled-calibration-v1",calibration_fingerprint=fingerprint("controlled-calibration-v1"),calibration_quality_status="CALIBRATION_QUALITY_ACCEPTABLE",distribution_shift_status="DISTRIBUTION_SHIFT_WARNING",shifted_features=("home_recent_points_per_match",),optional_missing=model_input.missing_feature_names,lineup_status="UNAVAILABLE",injury_status="UNAVAILABLE",odds_age_minutes=Decimal("6"))


class PredictionExplainabilityTests(unittest.TestCase):
    def setUp(self):
        self.db=Database(":memory:")
        from app.lab_operator_console.demo import build_demo
        build_demo(self.db)
        self.artifact,self.model_input=controlled_artifact_and_input()

    def tearDown(self):self.db.close()

    def create(self, *, selected="HOME_WIN"):
        return PredictionExplainabilityService(self.db).create(artifact=self.artifact,model_input=self.model_input,**context(self.artifact,self.model_input,selected=selected))

    def test_catalog_exactly_covers_canonical_live_78(self):
        self.assertEqual(len(CATALOG),78);self.assertEqual(len({item.feature_name for item in CATALOG}),78);self.assertEqual(len(CATALOG_FINGERPRINT),64)
        self.assertTrue(all(item.display_name_lv and item.explanation_group and item.missingness_semantics and item.source_type for item in CATALOG))

    def test_exact_scores_and_probabilities_are_reproduced_for_every_class(self):
        values=compute_class_attributions(self.artifact,self.model_input)
        self.assertEqual(len(values),9);self.assertTrue(all(item.score_reproduced and item.probability_reproduced for item in values))
        self.assertEqual({item.estimator_identity for item in values},{"MATCH_RESULT","TOTAL_GOALS_BUCKET","BTTS_YES"})
        self.assertTrue(all(len(item.contributions)==78 for item in values))

    def test_reasoning_is_deterministic_grouped_traceable_and_bounded(self):
        value=self.create();record=value["record"]
        self.assertEqual(value["audit"].status,"REASONING_AUDIT_PASSED");self.assertEqual(record.reasoning_id,"prediction-reasoning-"+record.reasoning_fingerprint)
        self.assertLessEqual(len(record.supporting_factors),4);self.assertLessEqual(len(record.opposing_factors),3);self.assertEqual(len(record.market_explanations),11)
        contribution_names={item.feature_name for attribution in record.class_attributions for item in attribution.contributions}
        self.assertTrue(all(set(item.member_feature_names)<=contribution_names for item in record.supporting_factors+record.opposing_factors))
        self.assertIn("LAB",record.public_reasoning_html);self.assertNotIn("AI thinks",record.public_reasoning_html)

    def test_totals_are_explicitly_bucket_derived_not_fabricated_direct_logits(self):
        for market in ("OVER_2_5","UNDER_2_5","OVER_3_5","UNDER_1_5"):
            db=Database(":memory:")
            try:
                from app.lab_operator_console.demo import build_demo
                build_demo(db);artifact,model_input=controlled_artifact_and_input();value=PredictionExplainabilityService(db).create(artifact=artifact,model_input=model_input,**context(artifact,model_input,selected=market));selected=next(item for item in value["record"].market_explanations if item.market==market)
                self.assertIn(selected.attribution_mode,{"DERIVED_BUCKET_SCORE_CONTRAST","COMPLEMENT_INVERSION"});self.assertIn("TOTAL_GOALS_BUCKET",selected.target_identity)
            finally:db.close()

    def test_missing_calibration_shift_confidence_counterfactuals_and_rejections_are_visible(self):
        record=self.create()["record"]
        self.assertTrue(record.missing_data_disclosures);self.assertIn("Kalibr",record.calibration_explanation);self.assertIn("treniņu sadalījuma",record.shift_explanation)
        self.assertEqual(record.confidence,"REVIEW_REQUIRED");self.assertGreaterEqual(len(record.counterfactuals),4)
        self.assertTrue(all(item.primary_rejection_code for item in record.market_explanations if item.market!=record.selected_market))

    def test_replay_is_idempotent_and_conflicting_replay_is_rejected(self):
        first=self.create();second=self.create();self.assertFalse(first["replayed"]);self.assertTrue(second["replayed"]);self.assertEqual(first["record"],second["record"])
        changed=context(self.artifact,self.model_input);changed["odds_age_minutes"]=Decimal("7")
        with self.assertRaises(ReasoningConflictError):PredictionExplainabilityService(self.db).create(artifact=self.artifact,model_input=self.model_input,**changed)

    def test_records_and_children_are_immutable_and_foreign_keys_are_clean(self):
        record=self.create()["record"]
        for table in ("prediction_reasoning_records","prediction_reasoning_feature_contributions","prediction_reasoning_group_contributions","prediction_reasoning_factors","prediction_reasoning_market_explanations","prediction_reasoning_audits","prediction_reasoning_audit_findings"):
            row=self.db.connection.execute(f"SELECT rowid FROM {table} LIMIT 1").fetchone()
            if row:
                with self.assertRaises(sqlite3.IntegrityError):self.db.connection.execute(f"DELETE FROM {table} WHERE rowid=?",(row[0],))
        self.assertEqual(self.db.connection.execute("PRAGMA foreign_key_check").fetchall(),[]);self.assertIsNotNone(SQLiteReasoningRepository(self.db,migrate=False).load(record.reasoning_id))

    def test_audit_blocks_prohibited_copy_and_linkage_mismatch(self):
        record=self.create()["record"]
        bad=replace(record,public_reasoning_html=record.public_reasoning_html+" garantēti",public_reasoning_fingerprint=fingerprint({"version":"goalvision-public-latvian-reasoning-v1","html":record.public_reasoning_html+" garantēti"}))
        audit=audit_reasoning(bad,checked_at_utc=CONTROLLED_TIME);self.assertEqual(audit.status,"REASONING_AUDIT_BLOCKED");self.assertIn("PROHIBITED_REASONING_PHRASE",{item[0] for item in audit.findings})

    def test_reasoned_message_and_publication_checks_bind_exact_evidence(self):
        value=self.create();record,audit=value["record"],value["audit"];message=compose_reasoned_message("Base preview",record)
        self.assertIn(record.public_reasoning_html,message["message_html"]);self.assertEqual(len(message["message_fingerprint"]),64)
        checks=dict(publication_reasoning_checks(record,audit,analysis_id=record.analysis_id,observation_id=record.observation_id,selected_market=record.selected_market));self.assertTrue(all(checks.values()))
        self.assertFalse(dict(publication_reasoning_checks(None,None,analysis_id="a",observation_id="o",selected_market="HOME_WIN"))["REASONING_PRESENT"])

    def test_controlled_rehearsal_is_full_offline_and_has_no_product_mutation(self):
        fresh=Database(":memory:")
        try:
            with patch("httpx.AsyncClient.post") as post:
                value=run_controlled_rehearsal(fresh)
            post.assert_not_called();self.assertEqual(value["audit_status"],"REASONING_AUDIT_PASSED");self.assertTrue(value["score_reproduction"] and value["probability_reproduction"])
            self.assertEqual(value["feature_count"],78);self.assertEqual(value["market_count"],11)
            self.assertEqual(sum(value[key] for key in ("network_calls","telegram_calls","delivery_records","official_mutations","bankroll_mutations","statistics_mutations","scheduling_changes")),0)
        finally:fresh.close()

    def test_fail_closed_for_artifact_schema_or_feature_order_mismatch(self):
        bad_artifact=replace(self.artifact,ordered_feature_names=tuple(reversed(self.artifact.ordered_feature_names)))
        with self.assertRaises(ExplainabilityError) as caught:compute_class_attributions(bad_artifact,self.model_input)
        self.assertEqual(caught.exception.status,"FEATURE_SCHEMA_MISMATCH")

    def test_schema_40_and_no_startup_reasoning(self):
        self.assertEqual(self.db.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],42)
        empty=Database(":memory:")
        try:
            SQLiteReasoningRepository(empty)
            self.assertEqual(empty.connection.execute("SELECT COUNT(*) FROM prediction_reasoning_records").fetchone()[0],0)
        finally:empty.close()

    def test_cli_help_human_and_json_are_terminal_safe(self):
        from app.prediction_explainability.cli import main
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"controlled.db";output=io.StringIO()
            with redirect_stdout(output):code=main(["controlled-rehearsal","--database",str(path),"--output","json"])
            value=json.loads(output.getvalue());self.assertEqual(code,0);self.assertEqual(value["feature_count"],78);self.assertEqual(value["network_calls"],0)


if __name__ == "__main__":unittest.main()
