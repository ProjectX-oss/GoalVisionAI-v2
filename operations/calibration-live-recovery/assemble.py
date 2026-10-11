"""Compact reviewed offline outputs; never access runtime databases or transports."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def without(value: dict, *keys: str) -> dict:
    return {k: v for k, v in value.items() if k not in keys}


def compact_scores(value):
    if isinstance(value, dict):
        return {k: compact_scores(v) for k, v in value.items() if k != 'reliability_bins'}
    if isinstance(value, list):
        return [compact_scores(v) for v in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = {}

    def read(name: str):
        data = (args.source / name).read_bytes()
        sources[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        return json.loads(data)

    hard = read('hardening.json')
    live = read('comparisons/live.json')
    replay = read('comparisons/replay.json')
    dc = read('dc.json')
    outputs = {
        'calibration.json': read('calibration_final.json'),
        'learning.json': read('watch/learning_champion.json'),
        'performance.json': read('watch/performance.json'),
        'combo.json': read('comparisons/combo.json'),
        'diagnostics.json': read('diagnostics.json'),
        'odds_yield.json': read('quality/odds_yield.json'),
        'disagreement.json': read('quality/disagreement.json'),
        'publication.json': read('publication.json'),
        'runtime.json': read('runtime_review.json'),
        'live.json': {
            'diagnostics': without(live, 'rows', 'same_state_quote_pairs'),
            'actual_cohorts': hard['actual_cohorts'],
            'context_v2': without(hard['context_v2'], 'versions'),
            'policy_screens': {k: without(v, 'rows') for k, v in hard['policy_screen_summaries'].items()},
            'snapshot_comparison_fingerprints': [r['fingerprint'] for r in hard['snapshot_comparisons']],
            'hardening_source_fingerprint': hard['source_fingerprint'],
            'hardening_result_fingerprint': hard['result_source_fingerprint'],
            'limitations': hard['limitations'],
        },
        'research.json': {
            'dixon_coles': compact_scores(dc),
            'combo_replay': without(replay, 'cycles', 'scored_hypothetical_coupons'),
            'combo_replay_cycles': [without(r, 'strategies') for r in replay['cycles']],
            'no_prospective_or_paired_strategy_superiority_claim': True,
        },
    }
    # Never publish raw receipts, credentials, transport bodies, or runtime logs.
    forbidden = {'chat_id', 'recipient_id', 'bot_token', 'api_key', 'password',
                 'authorization', 'headers', 'message_text', 'response_body'}

    def inspect(value):
        if isinstance(value, dict):
            if forbidden & {str(k).lower() for k in value}:
                raise ValueError('UNREVIEWED_SENSITIVE_EVIDENCE_FIELD')
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    args.output.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, value in outputs.items():
        inspect(value)
        encoded = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
        files[name] = {'sha256': hashlib.sha256(encoded).hexdigest(), 'bytes': len(encoded)}
        path = args.output / name
        if path.exists():
            if path.read_bytes() != encoded:
                raise ValueError('IMMUTABLE_EVIDENCE_CONFLICT:' + name)
        else:
            with path.open('xb') as handle:
                handle.write(encoded)
    manifest = {'version': 'CALIBRATION_LIVE_RECOVERY_EVIDENCE_V1',
                'as_of': live['as_of'], 'sources': sources, 'files': files,
                'raw_db_or_transport_data_committed': False}
    encoded = json.dumps(manifest, indent=2, sort_keys=True) + '\n'
    path = args.output / 'manifest.json'
    if path.exists() and path.read_text() != encoded:
        raise ValueError('IMMUTABLE_MANIFEST_CONFLICT')
    if not path.exists():
        with path.open('x') as handle:
            handle.write(encoded)
    print(json.dumps({'files': len(files), 'bytes': sum(v['bytes'] for v in files.values()),
                      'manifest_sha256': hashlib.sha256(encoded.encode()).hexdigest()}))


if __name__ == '__main__':
    main()
