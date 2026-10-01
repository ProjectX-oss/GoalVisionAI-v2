# PREMATCH protected current-odds pagination — 2026-10-01

User request: increase the three date-odds page calls observed in production.

## Evidence and change

At 13:00 Riga, the completed cycle spent 242 provider calls: 3 date-odds
pages, 43 fixture-odds calls and 185 prediction calls. The broad sweep
advertised 10 pages today, retained 6 tomorrow and 1 for the third day.
The priority analysis reservation used nearly all remaining quota, leaving
only the number of discovery dates for pagination.

Protect up to 32 page-call attempts from a quarter of the remaining cycle
budget before reserving the priority analysis backlog. At low quota this
shrinks to preserve the existing final-review and enrichment reservations.
Unused page allocation remains available for analysis. It is not a hard
32-page ceiling: low priority demand may permit more pages under existing
limits. Due exact reviews and tracked refreshes still precede broad pages.

Existing daily pacing, 400 requested cycle maximum, shared provider limits,
100-call results reserve, retries, quote freshness, publication checks,
probabilities and odds thresholds remain unchanged.

The report adds odds_pagination.protected_page_call_allowance and
odds_pagination.priority_analysis_reserve. A network-blocked synthetic
102-priority-fixture test with 10+6+1 pages changes coverage from 3 pages
and 0 quoted fixtures to 17 pages and 3 quoted fixtures, including restart
cursor gaps, within the same 258-call adaptive ceiling. These are software
regression results, not a claim of real future coverage or betting performance.
A 100+100+100-page test keeps pagination bounded and still funds predictions.

## Operator installation

Package: /home/arvis/goalvision-operations/prematch-odds-budget-20261001

python3 /home/arvis/goalvision-operations/prematch-odds-budget-20261001/update.py
sudo python3 /home/arvis/goalvision-operations/prematch-odds-budget-20261001/update.py --apply

The default command only verifies hashes. Apply checks the entire base Python
manifest, copies the immutable application, changes quota.py and runner.py,
and routes only discovery to the new release. It pauses the discovery timer
and waits at most 60 seconds for an active cycle without killing it. A busy
cycle refuses routing and restores prior timer activity; retry after completion.
A failed switch restores the prior route. Other service routes are checked.
No manual discovery, provider validation or test Telegram send is invoked.
Normal previously enabled scheduling resumes and can make its usual calls.

Rollback uses the same command with --apply --rollback. It restores the
existing fc4a740 discovery route, preserving ledgers and immutable releases.

## Remaining independent issues

This update does not fix the 13:38 ledger lock or AutoRepair worker startup
failure found in the preceding inspection. Those remain separate repairs.
More page calls do not make provider-stale quotes current or guarantee picks.

## Verification

286 tests passed in 31.06 seconds with real socket connections blocked:
new allocation and installer regressions; Lab V2 throughput, PREMATCH, shadow,
accuracy delivery and hardening suites. Installer tests cover exact staging,
idempotency, rollback, failed reload recovery, source tampering, running-cycle
refusal and inactive timer preservation. No production controls were invoked.
