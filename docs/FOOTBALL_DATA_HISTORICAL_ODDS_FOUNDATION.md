# Football-Data historical odds foundation

## Verdict

Football-Data.co.uk is approved only for bounded, controlled raw-data
research. The reviewed download page calls the data free and offers the files
for quantitative testing. Raw files may therefore be retained in
operator-controlled storage outside Git for this internal research use. No
explicit raw-data redistribution or commercial-use license was found, so
neither use is authorized by this review.

The source is **not eligible for GoalVision calibration, backtesting, shadow
evaluation, governance passage, or publication evidence**. Its notes describe
non-`C` columns as pre-closing/first-set odds and `C` columns as closing odds.
The fixture page describes general Friday and Tuesday collection schedules,
but the CSV rows contain no quote capture timestamp. GoalVision does not assign
those general schedule times to individual rows and cannot prove its fixed
24-hour cutoff. All real source odds cells consequently remain immutable raw
evidence with `UNKNOWN_CAPTURE_TIME`; zero cells become normalized actionable
quotes.

Reviewed pages:

- <https://www.football-data.co.uk/downloadm.php>
- <https://www.football-data.co.uk/notes.txt>
- <https://www.football-data.co.uk/matches.php>
- <https://www.football-data.co.uk/disclaimer.php>

The complete structured decision is in
`docs/data_sources/football_data_co_uk_csv_review_v1.json`.

## Bounded acquisition

Only German Bundesliga `D1.csv` was downloaded for 2022/23, 2023/24, and
2024/25. Those three files are the smallest season set spanning the tail of
TRAIN plus every immutable VALIDATION and TEST assignment. They contain 918
match rows. SHA-256 identities and retrieval time are recorded in the source
manifest and canonical evidence. Raw files and the isolated evidence database
remain under `var/reviewed_historical_odds/` and outside Git.

The 2025/26 German `D1.csv` archive was confirmed available by a read-only HTTP
metadata request and was not downloaded. It is chronologically non-overlapping
with TEST, but it has the same timestamp limitation and is not suitable for a
genuine future shadow evaluation.

## Parsing and linkage

The offline parser accepts only explicit individual-bookmaker columns for
GoalVision's existing `HOME_WIN`, `DRAW`, `AWAY_WIN`, `OVER_2_5`, and
`UNDER_2_5` markets. Market maximums, averages, Asian handicaps, and every
other market are excluded.

Each retained source cell records its file, one-based CSV row, source column,
bookmaker, original value, parsed decimal value, canonical market, odds
semantics, absent capture timestamp, rejection reason, source event, and
deterministic provenance fingerprint. The complete raw-cell bundle is stored
append-only in the existing historical betting-evidence summary infrastructure;
it is not stored in the actionable `historical_odds_quotes` table.

Football-Data match times are interpreted in `Europe/London`, including DST.
Fixtures link only through reviewed competition/team aliases plus exact UTC
kickoff, home, away, and season. The importer reproducibly rebuilds the exact
existing live-78 dataset and verifies both its dataset fingerprint and the
unchanged 1,459/313/313 split fingerprint before reporting coverage. It never
uses fuzzy matching.

## Result

- Source rows: 918 accepted for identity/linkage; 0 rejected.
- Event links: 918 reviewed-alias matches; 0 ambiguous, conflicting, or
  unmatched.
- Real valid decimal source values: 41,097; four additional non-empty cells
  contain zero odds values (2024/25 row 295, Pinnacle opening/closing totals),
  and 2,351 reviewed bookmaker/market cells are blank.
- Actionable normalized quotes: 0; 41,101 raw cells rejected from normalization
  (41,097 missing capture timestamps and four invalid decimals).
- TRAIN: 280/1,459 linked fixtures (19.19%), 12,274 real source values, zero
  eligible quotes.
- VALIDATION: 313/313 linked fixtures (100%), 12,778 real source values, zero
  eligible quotes.
- TEST: 313/313 linked fixtures (100%), 15,475 real source values, zero eligible
  quotes.

Fixture coverage is complete for VALIDATION and TEST, but odds evidence
coverage is zero under GoalVision's timestamp policy. TEST is therefore not
sufficient for a genuine calibration/backtest attempt.

## Offline replay

Run the explicit `import-football-data-foundation` command with the three raw
CSV paths, the seven OpenLigaDB reference snapshots, the structured review,
the prior reviewed-real split evidence, an isolated database, and a fixed
retrieval timestamp. The command performs no provider discovery, inference,
training, recalibration, comparison, shadow evaluation, activation, Telegram,
Official, bankroll, statistics, or scheduler work.
