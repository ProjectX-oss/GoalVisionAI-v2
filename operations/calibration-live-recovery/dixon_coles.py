"""Read-only existing forward evidence; no capture, fitting or metrics DB writes."""
import argparse
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.dixon_coles_research.repository import ResearchStore
from app.dixon_coles_research.sources import results, consumed_holdout_fixtures
from app.dixon_coles_research.contracts import digest, utc
from app.dixon_coles_forward.contracts import load_plan, reserved
from app.dixon_coles_forward import service, incremental


def main():
    def denied(*args, **kwargs):
        raise RuntimeError('RESEARCH_NETWORK_DISABLED')
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = denied
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('research', 'audit', 'ledger', 'output'):
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--as-of', required=True)
    a = p.parse_args()
    now = utc(a.as_of)
    plan, paired_plan = load_plan(), incremental.load_plan()
    store = ResearchStore(a.research, readonly=True)
    try:
        forecasts = store.all('forecast')
        models = {m['fingerprint']: m for m in store.all('model')}
    finally:
        store.close()
    exclusions = reserved(plan, consumed_holdout_fixtures(a.audit))
    holdout_start = utc(plan['protected_calendar']['windows']['SEALED_HOLDOUT'][0])
    forecasts = [f for f in forecasts if utc(f['forecast_at']) <= now
                 and utc(f['kickoff_utc']) < holdout_start and f['fixture_id'] not in exclusions]
    facts = results(a.ledger, a.audit, fixture_ids={f['fixture_id'] for f in forecasts}, now=now)
    full = service.evaluate(forecasts, models, facts, plan=plan, now=now, additional_reserved=exclusions)
    rows, diagnostics = incremental.prepare(forecasts, models, facts, plan=paired_plan,
                                           forward=plan, now=now, additional_reserved=exclusions)
    paired = incremental.report(rows, plan=paired_plan, forward=plan, now=now, diagnostics=diagnostics)
    report = {'as_of': now.isoformat(), 'full_market': full, 'strict_paired_1x2': paired,
        'source_forecast_fingerprint': digest(sorted(f['fingerprint'] for f in forecasts)),
        'source_result_fingerprint': digest(facts), 'forecast_count': len(forecasts),
        'provider_calls': 0, 'telegram_sends': 0, 'research_db_writes': 0, 'fit_invoked': False}
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+'\n'
    if a.output.exists():
        if a.output.read_text() != encoded:
            raise ValueError('IMMUTABLE_OUTPUT_CONFLICT')
    else:
        with a.output.open('x') as handle:
            handle.write(encoded)
    print(json.dumps({'forecast_count': len(forecasts), 'paired': paired['six_method_paired']['overall']}, sort_keys=True))


if __name__ == '__main__':
    main()
