"""Append-only governance persistence and reproduction evidence."""

import json

from app.database import Database,MigrationManager
from app.real_match_lab_analysis.fingerprint import canonical_json,fingerprint


class GovernanceConflictError(RuntimeError):pass


class SQLiteGovernanceRepository:
    def __init__(self,database:Database,*,migrate=True):
        self.connection=database.connection
        if migrate:MigrationManager(self.connection).migrate()

    def ensure_policy(self,policy,created_at_utc):
        value={"policy_id":policy.policy_id,"version":policy.version,"fingerprint":policy.fingerprint,"policy":policy,"created_at_utc":created_at_utc};row=self.connection.execute("SELECT policy_json FROM forward_test_governance_policies WHERE policy_fingerprint=?",(policy.fingerprint,)).fetchone()
        if row:return json.loads(row[0])
        with self.connection:self.connection.execute("INSERT INTO forward_test_governance_policies VALUES (?,?,?,?,?)",(policy.policy_id,policy.version,policy.fingerprint,canonical_json(value),created_at_utc))
        return value

    def append(self,evaluation,request_fingerprint,created_at_utc):
        row=self.connection.execute("SELECT evaluation_fingerprint,evaluation_json FROM forward_test_governance_evaluations WHERE request_fingerprint=?",(request_fingerprint,)).fetchone()
        if row:
            if row[0]!=evaluation["evaluation_fingerprint"]:raise GovernanceConflictError("GOVERNANCE_EVALUATION_REPLAY_CONFLICT")
            return json.loads(row[1]),True
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute("INSERT INTO forward_test_governance_evaluations VALUES (?,?,?,?,?,?,?,?,?,?)",(evaluation["evaluation_id"],evaluation["cutoff_utc"],evaluation["evidence_class"],evaluation["sample_maturity"],evaluation["decision"]["status"],evaluation["policy_fingerprint"],evaluation["evaluation_fingerprint"],request_fingerprint,canonical_json(evaluation),created_at_utc))
            for window in evaluation["windows"]:
                wid="governance-window-"+window["window_fingerprint"];self.connection.execute("INSERT INTO forward_test_governance_windows VALUES (?,?,?,?,?,?,?,?)",(wid,evaluation["evaluation_id"],window["kind"],window["scope_type"],window["scope_value"],window["sample_size"],window["window_fingerprint"],canonical_json(window)))
            for scope in evaluation["scope_statuses"]:
                sid="governance-scope-"+scope["scope_fingerprint"];self.connection.execute("INSERT INTO forward_test_governance_scope_statuses VALUES (?,?,?,?,?,?,?,?)",(sid,evaluation["evaluation_id"],scope["scope_type"],scope["scope_value"],scope["status"],scope["primary_reason"],scope["scope_fingerprint"],canonical_json(scope["metrics"])))
            decision=evaluation["decision"];did="governance-decision-"+decision["decision_fingerprint"];self.connection.execute("INSERT INTO forward_test_governance_decisions VALUES (?,?,?,?,?,?)",(did,evaluation["evaluation_id"],decision["status"],decision["publication_impact"],decision["decision_fingerprint"],canonical_json(decision)))
            previous=self.connection.execute("SELECT evaluation_id,governance_status FROM forward_test_governance_evaluations WHERE cutoff_utc<? ORDER BY cutoff_utc DESC,evaluation_id DESC LIMIT 1",(evaluation["cutoff_utc"],)).fetchone();transition={"evaluation_id":evaluation["evaluation_id"],"previous_evaluation_id":previous[0] if previous else None,"previous_status":previous[1] if previous else None,"current_status":decision["status"],"reason":"INITIAL_EVALUATION" if not previous else "STATUS_CHANGED" if previous[1]!=decision["status"] else "STATUS_RETAINED","occurred_at_utc":created_at_utc};tfp=fingerprint(transition);self.connection.execute("INSERT INTO forward_test_governance_transitions VALUES (?,?,?,?,?,?,?,?,?)",("governance-transition-"+tfp,evaluation["evaluation_id"],transition["previous_evaluation_id"],transition["previous_status"],transition["current_status"],transition["reason"],tfp,canonical_json(transition),created_at_utc))
            for recommendation in evaluation["recommendations"]:
                rfp=fingerprint({"evaluation":evaluation["evaluation_id"],**recommendation});self.connection.execute("INSERT INTO forward_test_governance_recommendations VALUES (?,?,?,?,?,?)",("governance-recommendation-"+rfp,evaluation["evaluation_id"],recommendation["type"],recommendation["outcome"],rfp,canonical_json(recommendation)))
            self.connection.commit();return evaluation,False
        except Exception:self.connection.rollback();raise

    def load(self,evaluation_id):
        row=self.connection.execute("SELECT evaluation_json FROM forward_test_governance_evaluations WHERE evaluation_id=?",(evaluation_id,)).fetchone();return json.loads(row[0]) if row else None
    def by_request(self,request_fingerprint):
        row=self.connection.execute("SELECT evaluation_json FROM forward_test_governance_evaluations WHERE request_fingerprint=?",(request_fingerprint,)).fetchone();return json.loads(row[0]) if row else None
    def request_at_cutoff(self,cutoff_utc,evidence_class,policy_fingerprint):
        return self.connection.execute("SELECT request_fingerprint,evaluation_json FROM forward_test_governance_evaluations WHERE cutoff_utc=? AND evidence_class=? AND policy_fingerprint=?",(cutoff_utc,evidence_class,policy_fingerprint)).fetchone()
    def latest(self,cutoff_utc=None):
        if cutoff_utc:row=self.connection.execute("SELECT evaluation_json FROM forward_test_governance_evaluations WHERE cutoff_utc<=? ORDER BY cutoff_utc DESC,evaluation_id DESC LIMIT 1",(cutoff_utc,)).fetchone()
        else:row=self.connection.execute("SELECT evaluation_json FROM forward_test_governance_evaluations ORDER BY cutoff_utc DESC,evaluation_id DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None
    def history(self,limit=100):return tuple(json.loads(row[0]) for row in self.connection.execute("SELECT evaluation_json FROM forward_test_governance_evaluations ORDER BY cutoff_utc,evaluation_id LIMIT ?",(limit,)))

    def append_reproduction(self,evaluation_id,status,actual,checked_at_utc):
        value={"evaluation_id":evaluation_id,"status":status,"actual_fingerprint":actual,"checked_at_utc":checked_at_utc,"network_calls":0,"telegram_calls":0};fp=fingerprint(value);value.update({"reproduction_id":"governance-reproduction-"+fp,"reproduction_fingerprint":fp})
        with self.connection:self.connection.execute("INSERT OR IGNORE INTO forward_test_governance_reproductions VALUES (?,?,?,?,?,?)",(value["reproduction_id"],evaluation_id,status,fp,canonical_json(value),checked_at_utc))
        return value

    def append_event(self,evaluation_id,event_type,operator,reason,occurred_at):
        value={"evaluation_id":evaluation_id,"event_type":event_type,"operator_identity":operator,"reason":reason,"occurred_at_utc":occurred_at};fp=fingerprint(value);value.update({"event_id":"governance-event-"+fp,"event_fingerprint":fp})
        with self.connection:self.connection.execute("INSERT OR IGNORE INTO forward_test_governance_events VALUES (?,?,?,?,?,?,?,?)",(value["event_id"],evaluation_id,event_type,operator,reason,fp,canonical_json(value),occurred_at))
        return value

    def append_observation_snapshot(self, value):
        row=self.connection.execute("SELECT snapshot_fingerprint,snapshot_json FROM forward_test_observation_governance_snapshots WHERE observation_id=?",(value["observation_id"],)).fetchone()
        if row:
            if row[0]!=value["snapshot_fingerprint"]:raise GovernanceConflictError("OBSERVATION_GOVERNANCE_SNAPSHOT_CONFLICT")
            return json.loads(row[1]),True
        with self.connection:self.connection.execute("INSERT INTO forward_test_observation_governance_snapshots VALUES (?,?,?,?,?,?,?)",(value["snapshot_id"],value["observation_id"],value["evaluation_id"],value["publication_decision"],value["snapshot_fingerprint"],canonical_json(value),value["created_at_utc"]))
        return value,False
