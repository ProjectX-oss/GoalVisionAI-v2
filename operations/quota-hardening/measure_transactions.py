"""Synthetic SQLite transaction measurements. Never accepts a production DB path."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import timedelta
import json
from pathlib import Path
import statistics
import tempfile
import time
from app.adaptive_lab.repository import AuditRepository
from app.adaptive_lab.quota import SharedQuota
from app.adaptive_lab.observations import ingest
from tests.adaptive_lab.conftest import START, frozen


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='quota-measure-') as directory:
        repo = AuditRepository(Path(directory) / 'synthetic.sqlite')
        for i in range(1712):
            stamp = (START + timedelta(seconds=i)).isoformat()
            repo.append('quota_claims', str(i), 'PREMATCH', {
                'category': 'PREMATCH_DISCOVERY', 'created_at': stamp}, stamp)
        for i in range(1480):
            p, r, s = frozen(i)
            ingest(repo, p, r, s, stream='PREMATCH', publication_id=p['prediction_id'])
        durations = []
        transaction = repo.transaction
        @contextmanager
        def measured():
            nested = repo.connection.in_transaction
            with transaction():
                start = time.perf_counter()
                try:
                    yield
                finally:
                    if not nested:
                        durations.append((time.perf_counter() - start) * 1000)
        repo.transaction = measured
        provider = {'interpretation_status': 'NORMALIZED', 'daily_remaining': 7500, 'minute_remaining': 300}
        output = {}
        for name, operation in (
            ('quota_1712_claim_history', lambda i: SharedQuota(repo).claim('SETTLEMENT', now=START+timedelta(hours=1), provider=provider)),
            ('observer_1480_replays', lambda i: ingest(repo, *frozen(i), stream='PREMATCH', publication_id=frozen(i)[0]['prediction_id'])),
        ):
            durations.clear()
            start = time.perf_counter()
            for i in range(20 if name.startswith('quota') else 1480):
                operation(i)
            output[name] = {'elapsed_ms': round((time.perf_counter()-start)*1000, 3),
                'write_transactions': len(durations), 'max_writer_body_ms': round(max(durations, default=0), 3),
                'median_writer_body_ms': round(statistics.median(durations), 3) if durations else 0}
        repo.close()
        print(json.dumps(output, sort_keys=True))


if __name__ == '__main__':
    main()
