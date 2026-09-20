# PREMATCH production-lineage integration

Base: `ce0289075c8ac3e6c4ecc5c8aaad0d20568783e1`.
Port source: `fadd59d7d9492133f84d9d80c9a72dad14c57c67` (patch only).
No production deployment or state migration is performed by this integration.

Discovery runs on the repository timer at 09:00–22:30 Europe/Riga, every
30 minutes. Application and per-request guards pause new selection work at
23:00 until 09:00; results and local learning remain independent. Remaining
provider quota, minus 100 result calls, is divided across remaining half-hour
slots. The maximum remains 400, with actual provider minute limits and retries
charged inside the same ceiling. Unneeded capacity is left unused. Shared
PREMATCH quota no longer holds disabled LIVE allocations.

All valid upcoming fixtures reach local model/context analysis, including
missing/stale current prices. These remain waiting for refresh without a
fabricated price or EV. Positive-EV quality findings lower confidence or lane;
nonpositive EV and corrupt contracts remain blockers. Lab has no 1.60 floor;
Official policy is unchanged. TRACKING cannot publish; READY needs a current
valid quote and positive EV. Existing delivery claims, Lab destination and Riga
publication cutoff remain authoritative. Started matches remain result/audit
and learning evidence, never new PREMATCH or LIVE selections.

Competition priority uses the existing reviewed provider/country registry.
Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Champions League,
Europa League and Conference League receive first resource access. Broader
priority classes and ordinary global fixtures follow. Exact retries remain
bounded, replace failed/stale broad quotes and share the cycle ceiling.

## Adaptive integration

Production observer, research/AutoML schedule, champion/bootstrap/rollback,
governance, health/status/why-no-picks and Sunday 22:30 Riga weekly statistics
are retained. The existing configured adaptive database receives the first
canonical fresh positive-EV pre-kickoff fixture/market observation. Subsequent
captures cannot replace it. Schema 5 adds two append-only tables; no production
database has been opened or migrated during development.

The existing settlement worker handles canonical observations within its
existing call budget, sharing fixture result responses with challenger shadow
settlement and reusing available published result evidence. There is no new
worker or `settle-shadow` command. Immutable results join into the existing
`learning_observations` path; published and shadow copies of a fixture/market
are counted once. Shadow observations have no publication timestamp and never
enter public SINGLE/COMBO statistics, Telegram delivery or bankroll accounting.
Historical evidence is never rewritten.

## Verification

Offline focused tests cover quota/window boundaries, analysis-first tracking,
low odds, EV and quality findings, exact refresh, competition priority, results,
canonical learning/idempotency, delivery isolation and all production adaptive
capabilities. The complete repository suite is also run.

Deterministic incident replay: 958 discovered; 958 local analysis attempts;
3 current-odds evaluated; 955 waiting for refresh; 0 READY; 96 provider calls.
This uses synthetic fixed model probabilities and sparse odds, not a historical
profitability claim or evidence for champion promotion. Real prediction-quality
validation remains necessary before any separately authorized deployment.

Repository systemd templates are documentation artifacts only. No units were
installed, reloaded, enabled or restarted. LIVE remains disabled.

Final verification: focused run **597 passed**; supplemental edge checks
**38 passed**, adaptive integration checks **177 passed**, and final incident/
canonical/no-demand checks **6 passed**. The complete suite passed **2,199 tests
and 563 subtests** (728.29 seconds), with dummy Telegram/OpenAI/football test
credentials. The historical-odds read-only test now owns disposable source and
output databases instead of depending on an untracked checkout database.

Full-suite command (isolated checkout only):

```sh
TELEGRAM_BOT_TOKEN=123456:test-only OPENAI_API_KEY=test-only FOOTBALL_API_KEY=test-only python -m pytest -q --tb=short
```
