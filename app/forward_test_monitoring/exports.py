"""Deterministic, secret-safe report renderers."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint


CSV_FILES = ("observations.csv", "settlements.csv", "market.csv", "competition.csv", "bookmaker.csv", "calibration_bins.csv", "data_quality.csv", "lifecycle.csv", "unresolved.csv")


def markdown(report: dict[str, Any]) -> str:
    metrics=report["metrics"]; volume=metrics["volume"]; results=metrics["results"]; simulation=metrics["hypothetical_flat_stake"]
    return "\n".join((
        f"# GoalVision AI Forward-Test {report['report_kind'].title()} Report",
        "", f"Period: {report.get('period_start_utc') or 'inception'} to {report['period_end_utc']} UTC",
        f"Policy: {report['policy_id']} {report['policy_version']}", f"Sample status: **{metrics['sample_status']}**", "",
        "> LAB forward-test evidence only. No bets were placed. Returns are HYPOTHETICAL_FLAT_STAKE. This is not proof of profitability.", "",
        "## Volume", "", f"- Observations: {volume['observations_created']}", f"- Actionable: {volume['actionable_selections']}", f"- No selection: {volume['no_selections']}", f"- Blocked: {volume['blocked_analyses']}", f"- Published / unpublished: {volume['published_predictions']} / {volume['unpublished_valid_predictions']}", "",
        "## Results", "", f"- Won / lost / void: {results['wins']} / {results['losses']} / {results['voids']}", f"- Hit rate: {_show(results['hit_rate'])}", f"- Net units: {_show(simulation['net_profit_units'])}", f"- ROI: {_show(simulation['roi'])}", f"- Maximum drawdown: {_show(simulation['maximum_drawdown'])}", "",
        "## Data quality", "", f"- Status: {report['data_quality']['status']}", f"- Findings: {len(report['data_quality']['findings'])}", f"- Unresolved: {len(report['unresolved'])}", "",
        "## Limitations", "", *(f"- {item}" for item in report["limitations"]), "", f"Report fingerprint: `{report['report_fingerprint']}`", "",
    ))


def telegram_preview(report: dict[str, Any]) -> str:
    metrics=report["metrics"]; volume=metrics["volume"]; results=metrics["results"]; simulation=metrics["hypothetical_flat_stake"]
    return "\n".join(("⚽ GoalVision AI LAB Forward-Test", f"{report['report_kind'].title()} monitoring preview", "", f"Observations: {volume['observations_created']}", f"Actionable / no selection / blocked: {volume['actionable_selections']} / {volume['no_selections']} / {volume['blocked_analyses']}", f"W / L / Void: {results['wins']} / {results['losses']} / {results['voids']}", f"Hypothetical net: {_show(simulation['net_profit_units'])} units", f"Sample: {metrics['sample_status']}", "", "LAB forward-test only. No bets were placed.", "Hypothetical flat-stake simulation; not proof of profitability.", "Preview only — Telegram send is disabled."))


def export_bundle(report: dict[str, Any], output_directory: Path, *, overwrite: bool = False) -> dict[str, Any]:
    if output_directory.exists() and any(output_directory.iterdir()) and not overwrite:
        raise FileExistsError("Export destination is not empty; pass --overwrite explicitly.")
    output_directory.mkdir(parents=True, exist_ok=True)
    files: dict[str,str]={"report.json":canonical_json(report)+"\n","report.md":markdown(report),"telegram-preview.txt":telegram_preview(report)+"\n"}
    segment_map={"market.csv":"market","competition.csv":"competition","bookmaker.csv":"bookmaker"}
    observation_headers=("observation_id","fixture_id","created_at_utc","status","actionable","market","bookmaker","provider","quoted_odds","raw_probability","calibrated_probability","expected_value","published","outcome","observation_fingerprint")
    settlement_headers=("settlement_id","observation_id","result_id","market","outcome","quoted_odds","hypothetical_stake","hypothetical_net_return","settled_at_utc","settlement_fingerprint")
    files["observations.csv"]=_csv(observation_headers, (tuple(row.get(key) for key in observation_headers) for row in report["records"]["observations"]))
    files["settlements.csv"]=_csv(settlement_headers, (tuple(row.get(key) for key in settlement_headers) for row in report["records"]["settlements"]))
    for filename,segment in segment_map.items(): files[filename]=_csv(("key","count","sample_status"), ((r["key"],r["count"],r["sample_status"]) for r in report["segments"][segment]))
    files["calibration_bins.csv"]=_csv(("lower","upper","count","predicted","observed","absolute_error","sample_status"), ((r.get("lower"),r.get("upper"),r.get("count"),r.get("predicted"),r.get("observed"),r.get("absolute_error"),r.get("sample_status")) for r in report["metrics"]["calibration"]["bins"]))
    files["data_quality.csv"]=_csv(("severity","code","affected_identifier","provenance","detail"), ((r["severity"],r["code"],r["affected_identifier"],r["provenance"],r["detail"]) for r in report["data_quality"]["findings"]))
    files["lifecycle.csv"]=_csv(("observation_id","status","finding_count","audit_fingerprint"), ((row["observation_id"],row["status"],len(row["findings"]),row["audit_fingerprint"]) for row in report["lifecycle_audits"]))
    files["unresolved.csv"]=_csv(("observation_id","state","overdue","due_at_utc"), ((r["observation_id"],r["state"],r["overdue"],r["due_at_utc"]) for r in report["unresolved"]))
    manifest=[]
    for name,content in sorted(files.items()):
        (output_directory/name).write_text(content,encoding="utf-8",newline="")
        manifest.append({"path":name,"sha256":hashlib.sha256(content.encode("utf-8")).hexdigest(),"bytes":len(content.encode("utf-8"))})
    value={"schema_version":"goalvision-forward-test-export-manifest-v1","report_id":report["report_id"],"files":manifest,"telegram_send_executed":False}; value["manifest_fingerprint"]=fingerprint(value)
    (output_directory/"manifest.json").write_text(canonical_json(value)+"\n",encoding="utf-8",newline="")
    return value


def _csv(headers,rows):
    stream=io.StringIO(newline=""); writer=csv.writer(stream,lineterminator="\n"); writer.writerow(headers)
    for row in rows: writer.writerow([_show(value) for value in row])
    return stream.getvalue()


def _show(value):
    if value is None:return "N/A"
    if isinstance(value,(dict,list)):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return str(value)
