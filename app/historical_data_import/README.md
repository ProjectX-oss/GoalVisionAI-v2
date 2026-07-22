# Historical Match Data Import Foundation

`app.historical_data_import` is the explicit, deterministic ingestion boundary
for supplied historical football datasets. It is the authoritative upstream
history source intended for future feature generation, model/calibration
training, backtesting, model comparison, and shadow evaluation.

The package performs no file discovery, live fetching, polling, scheduling,
prediction work, training, backtesting, publication, or Telegram activity.
Importing the package is inert. An application must explicitly supply a typed
`HistoricalDataset` or a strict JSON-compatible mapping, an import timestamp,
and a database-backed repository.

## Versioned dataset boundary

The supported schema is `goalvision_historical_dataset_v1`. Dataset identity is
the normalized provider, explicit dataset ID, and explicit dataset version.
Unknown mapping fields, missing required fields, empty datasets, and unsupported
schema versions fail before persistence.

Each match supplies competition, season, round, kickoff, teams, full-time score,
optional paired half-time score, result verification, venue, optional referee
and attendance, optional home/away statistics, and optional home/away lineups.
Statistics and lineups remain absent when the provider did not supply them; the
importer never invents values.

## Normalization and validation

- Text uses Unicode NFKC, trimmed/collapsed whitespace, and a separate
  punctuation-insensitive case-folded identity.
- All timestamps must carry an explicit offset and are stored in UTC with `Z`.
- Full-time result is derived from the score; a supplied result must agree.
- Scores are non-negative and bounded; paired half-time scores cannot exceed
  the final score.
- Decimal statistics reject binary floats and use finite Decimal-safe values.
- Possession is 0–100 and a supplied home/away pair must total 100 ± 1.
- Shots on target cannot exceed shots. xG, shots, corners, cards, fouls, and
  offsides have explicit impossible-value bounds in the versioned policy.
- A lineup has exactly 11 unique starters, at most 20 substitutes, no player in
  both collections, and an optional formation describing ten outfield players.
- Repeated provider identities, natural match identities, and normalized
  content within one dataset are rejected.

## Fingerprints and replay

Canonical JSON uses sorted keys, preserved list order, normalized UTC strings,
and canonical Decimal strings. SHA-256 identities cover normalized match
content, provider match identity, natural match identity, dataset content, and
the complete versioned dataset request. Input match order and the operator's
import timestamp do not alter content fingerprints.

An exact dataset replay returns `IDEMPOTENT_REPLAY` and writes nothing. A new
dataset version may reuse identical matches without duplicating rows. Corrected
content for the same provider match and kickoff appends the next immutable match
version. Reusing a dataset identity with different content, changing kickoff for
an existing provider match, or assigning the same natural match to another
provider ID fails closed.

## Persistence

Migration v23 adds:

- `historical_match_imports`
- `historical_matches`
- `historical_match_statistics`
- `historical_lineups`

One `BEGIN IMMEDIATE` transaction preflights the complete dataset, records the
import, appends new match versions, and appends all available statistics and
lineups. Any conflict or database failure rolls back the complete import. All
four tables reject updates and deletes through eight SQLite triggers.

## Explicit use

```python
from app.database import Database
from app.historical_data_import import build_historical_match_importer

database = Database("path/to/dedicated.db")
importer = build_historical_match_importer(database)
result = importer.import_mapping(payload, import_timestamp="2026-07-22T18:00:00Z")
```

The caller owns dataset acquisition, authorization, file handling, database
selection, and lifecycle. Live providers and automatic execution remain
deliberately outside this package.

The explicit downstream machine-learning boundary is
`app.historical_training_dataset`. It reads selected immutable import snapshots,
never mutates them, and enforces a strict source-kickoff-before-target cutoff.
The intended flow is historical import -> training dataset -> future split,
training, calibration fitting, backtesting, model comparison, and shadow review.
