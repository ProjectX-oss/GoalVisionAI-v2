"""Deterministic governance reports and preview-only exports."""

import csv,io,json
from pathlib import Path

from app.real_match_lab_analysis.fingerprint import canonical_json,fingerprint


def build_report(evaluation,kind="LATEST"):
    value={"schema_version":"goalvision-forward-test-governance-report-v1","report_kind":kind,"evaluation_id":evaluation["evaluation_id"],"evaluation_fingerprint":evaluation["evaluation_fingerprint"],"cutoff_utc":evaluation["cutoff_utc"],"sample_maturity":evaluation["sample_maturity"],"decision":evaluation["decision"],"metrics":evaluation["metrics"],"scope_statuses":evaluation["scope_statuses"],"recommendations":evaluation["recommendations"],"limitations":["Forward-test samples may be insufficient.","Predictive governance is not proof of profitability.","No automatic retraining, recalibration, activation, rollback, publication, or Telegram action occurs."]};value["report_fingerprint"]=fingerprint(value);return value


def markdown(report):
    return "\n".join(("# GoalVision AI Forward-Test Governance",f"- Decision: {report['decision']['status']}",f"- Sample maturity: {report['sample_maturity']}",f"- Cutoff: {report['cutoff_utc']}",f"- Predictive: {report['metrics']['predictive_status']}",f"- Calibration: {report['metrics']['calibration_status']}",f"- Input drift: {report['metrics']['input_drift_status']}",f"- Explanation drift: {report['metrics']['explanation_drift']['status']}","","Sample warnings apply. This report is not proof of profitability."))


def telegram_preview(report):return "\n".join(("⚽ GoalVision AI LAB Governance",f"Decision: {report['decision']['status']}",f"Sample: {report['sample_maturity']}",f"Predictive: {report['metrics']['predictive_status']}",f"Calibration: {report['metrics']['calibration_status']}","Preview only — nothing has been sent.","Governance evidence is not proof of profitability."))


def csv_text(report):
    stream=io.StringIO(newline="");writer=csv.writer(stream,lineterminator="\n");writer.writerow(("scope_type","scope_value","status","primary_reason","scope_fingerprint"))
    for item in report["scope_statuses"]:writer.writerow((item["scope_type"],item["scope_value"],item["status"],item["primary_reason"],item["scope_fingerprint"]))
    return stream.getvalue()


def export(report,directory:Path):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False);files={"governance.json":canonical_json(report)+"\n","governance.md":markdown(report)+"\n","governance.csv":csv_text(report),"telegram-preview.txt":telegram_preview(report)+"\n"}
    for name,text in files.items():(directory/name).write_text(text,encoding="utf-8",newline="")
    manifest={"files":[{"name":name,"fingerprint":fingerprint(text),"bytes":len(text.encode("utf-8"))} for name,text in sorted(files.items())],"telegram_sent":False};manifest["manifest_fingerprint"]=fingerprint(manifest);return manifest
