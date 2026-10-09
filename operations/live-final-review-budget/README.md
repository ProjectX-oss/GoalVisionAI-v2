# LIVE final-review budget repair, 2026-10-09

Only the existing LIVE runner, service diagnostics and worker allocation are
included in the optional operator release. No active market, probability, EV,
quote-age, model, exposure, timer, PREMATCH, COMBO or Official rule is changed.

## Verified problem

Fixed read-only cutoff 2026-10-09T18:09:03.379063+00:00 (21:09 Riga):
38 natural cycles; 721 candidate versions across 28 fixtures; 64 initially READY;
26 selected final-review attempts, all `LIVE_FINAL_REFRESH_FAILED`; zero claims
or publication receipts. Each run consumed 35, 36 or 37 provider calls. Available
daily quota remained above the PREMATCH result reserve.

The scan had no phase ceiling, so it could consume the complete dynamically
allocated cycle budget before `publish()` requested another exact refresh. It
continued trying remaining fixtures after exhaustion and swallowed the request
limit under generic diagnostics. The old output does not retain exception types,
so an individual historic failure cannot be conclusively relabeled.

The exact failure mechanism reproduces offline through the real FootballClient
HTTP-attempt accounting, worker, runner, service and fake HTTP/Telegram transports
at all three observed budgets. No-reserve runs exhaust the ceiling and fail final
refresh; reserved runs keep the same ceiling and complete one fake publication.
This is software evidence, not evidence that any historical candidate would have
passed a genuine counterfactual final quote.

## Repair

- Reserve nine existing-budget HTTP attempts for one final fixture/events/odds
  refresh, covering the current three-attempt retry policy for each endpoint.
- Scan-only authorization checks before every HTTP attempt/retry; shared quota
  authorization still runs for every permitted attempt. No new HTTP ceiling.
- Stop scanning when the allowance is reached, retain already prepared candidates,
  release only the scan guard in `finally`, then perform normal exact final review.
- Final-review history and catalog are already cached for a scanned candidate.
  Changed/missing provider inputs still fail closed; the reserve guarantees no
  publication, successful response or immunity from shared daily/minute limits.
- Emit the cycle/scan ceilings and fixed, sanitized final-review failure reason.
- Existing provider-side reserve, 18–23 window, one pick/cycle, 60–70% band,
  probability ranking, EV-off behavior and settlement remain authoritative.

The tradeoff is fewer initially examined fixtures within a tight cycle, so that
an eligible retained candidate can actually receive its mandatory final review.
No forced fallback candidate or retry publication is introduced.

## Expanded market research

`app/adaptive_lab/expanded_markets_research.py` adds isolated regulation-time
DOUBLE_CHANCE, DNB, TOTAL and integer/half-goal ASIAN_HANDICAP payoff integration
over separately pinned as-of score scenarios. It reuses existing exact scenario
probability serialization and provenance hashes. Win/loss/push are distinct;
expected unit P/L is `p_win*(odds-1)-p_loss`. DNB conditional win probability is
never silently substituted for unconditional probability or the active band.

There is no active provider-ID mapping, new model, synthetic odds, publisher hook
or calibration claim. Missing retained quote means no EV. Quarter handicaps,
cards, corners and correct-score publications remain unsupported. Current stored
LIVE candidate quotes expose only the old 11 targets; coverage of the new markets
cannot be reconstructed from those filtered rows. A separately reviewed current
payload/catalog mapping and end-to-end settlement integration is required before
any publication expansion. This module is excluded from the repair release.

## Reproduce without network

```bash
.venv/bin/python -B operations/live-combo-research/offline_tests.py \
  tests/adaptive_lab/test_live_final_review_budget.py \
  tests/adaptive_lab/test_expanded_markets_research.py \
  tests/test_live_final_review_install.py
```

Use the existing `/home/arvis/GoalVisionAI/.venv/bin/python` when running from the
isolated worktree. No production cycle, provider request or Telegram test is needed.

## Operator installation (not executed by the agent)

After the reviewed package is built, validate read-only first:

```bash
python3 ~/goalvision-operations/live-final-review-budget.py
sudo python3 ~/goalvision-operations/live-final-review-budget.py --apply
```

The second command is the explicit operator deployment. It preserves the existing
LIVE configuration, uses a new immutable release, briefly pauses/restores only the
LIVE timer while draining an existing run, and never starts a manual service cycle.
Do not run `--apply` as part of testing. Installation checks exact base hashes,
loaded routes, protected PREMATCH/research/ADMIN routes, timer configuration and
the disabled ADMIN Codex guard. Other release drift fails closed.

After installation, inspect the next natural cycle for `request_budget`,
`scan_stop_reason`, final-review status and immutable receipts. No message is
guaranteed: the refreshed candidate must still pass all existing gates.
