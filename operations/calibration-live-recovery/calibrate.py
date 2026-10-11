"""Explicit offline fit of frozen PREMATCH calibration rows, never a worker."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.adaptive_lab.calendar_monitor import load_plan
from app.adaptive_lab.calendar_calibration_fit import fit_only
from app.adaptive_lab.contracts import digest, utc
from app.adaptive_lab.repository import AuditRepository


def main() -> None:
    def denied(*args, **kwargs):
        raise RuntimeError('RESEARCH_NETWORK_DISABLED')
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = denied
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--fitted-at', required=True, help='Pinned actual experiment timestamp, separate from source cutoff')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = load_plan()
    repo = AuditRepository(args.database, readonly=True)
    try:
        # Materialize before decoding; later validation/holdout documents are
        # excluded by prediction timestamp in SQL, not deserialized and discarded.
        records = repo.connection.execute(
            "SELECT document,fingerprint FROM learning_observations WHERE stream='PREMATCH' "
            "AND json_extract(document,'$.prediction_created_at')<? AND created_at<=? ORDER BY created_at,id",
            (plan.windows()['CALIBRATION_FIT'][1].isoformat(), args.as_of)).fetchall()
        champion = repo.champion('PREMATCH')
        artifact = repo.get('model_artifacts', champion['artifact_id'])
        consumed = repo.connection.execute("SELECT count(*) FROM holdout_results WHERE stream='PREMATCH'").fetchone()[0]
        if consumed:
            raise ValueError('HOLDOUT_ALREADY_CONSUMED_REQUIRES_SEPARATE_REVIEW')
    finally:
        repo.close()
    rows = []
    for document, expected in records:
        row = json.loads(document)
        if digest(row) != expected:
            raise ValueError('ARTIFACT_INTEGRITY_FAILURE')
        rows.append(row)
    if utc(args.fitted_at) < utc(args.as_of):
        raise ValueError('FIT_BEFORE_SOURCE_CUTOFF')
    result = fit_only(rows, plan, champion, artifact, now=utc(args.fitted_at))
    result.pop('fingerprint')
    result['source_as_of'] = utc(args.as_of).isoformat()
    result['fingerprint'] = digest(result)
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        if args.output.read_text() != encoded:
            raise ValueError('IMMUTABLE_RESEARCH_OUTPUT_CONFLICT')
    else:
        with args.output.open('x') as handle:
            handle.write(encoded)
        args.output.chmod(0o444)
    print(json.dumps({'status': 'RESEARCH_FIT_ONLY', 'fingerprint': result['fingerprint'],
        'fit_independent_fixtures': result['fit_independent_fixtures'],
        'methods': {k: {'status': v['status'], 'metrics': v.get('metrics')} for k, v in result['methods'].items()},
        'production_eligible': False}, sort_keys=True))


if __name__ == '__main__':
    main()
