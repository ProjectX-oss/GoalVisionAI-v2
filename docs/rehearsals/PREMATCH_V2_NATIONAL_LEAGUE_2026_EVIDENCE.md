# National League 2026/27 regulation evidence

**REGULATION_EVIDENCE_READY. Real cycle executed: NO.**

The existing registry accepted a genuine THE_FA → IFAB incorporation chain for
**API_FOOTBALL / 43 / 2026**, England National League 2026/27. It resolves to
`VERIFIED_90` for the standard scheduled regulation format. This is an AI source
review and isolated TEST import, not a human sign-off or prospective football
observation. Overall synthetic readiness remains `INSUFFICIENT_SAMPLE`.

## Scope and source review

Base: `4a24ec4c089719dedf0150508b034d46da711708`.
Branch: `codex/prematch-v2-national-league-regulation-evidence`.
Actual isolated worktree: `/tmp/goalvision-national-league-evidence`.
Original checkout `/tmp/goalvision-regulation-evidence` at `87f9f249` was preserved.
No app code, schema, authority policy, classification or prediction logic changed.

Sources actually inspected during 2026-09-25 12:28:50–12:33:44 UTC:

- [FA current handbook landing](https://www.thefa.com/football-rules-governance/lawsandrules/fa-handbook): identifies the 2026/27 handbook. The full handbook was not downloaded.
- [FA 2026/27 section 8](https://www.thefa.com/-/media/files/thefaportal/governance-docs/rules-of-the-association/2026-27/section-8---rules-of-association.ashx): A1/A1.1, Laws definition, B9.2 and J1.5, PDF pages 1, 7, 16 and 62. Adopted 1 June 2026. Requires conformity with IFAB Laws and recognizes their annual commencement.
- [FA 2026/27 section 21](https://www.thefa.com/-/media/files/thefaportal/governance-docs/rules-of-the-association/2026-27/section-21---national-league-system-regulations.ashx): definitions and regulations 2/3.1, PDF pages 1–2. Establishes sanctioned NLS scope and National League at Step 1, separately from North/South at Step 2. Diagram labels were decoded locally from embedded font encodings; web screenshot images were unavailable.
- [IFAB catalogue](https://www.theifab.com/laws-of-the-game-documents/) and its [2026/27 English single-page edition](https://downloads.theifab.com/downloads/laws-of-the-game-202627-single-pages): reused `/tmp/ucl-2026-ifab.pdf` after verifying all 23,437,157 bytes against SHA-256 `89398520b353c6d995a1bb2557c97dc3c5aa1712c1d3009589f580a5a23c6a7d`. Independently re-extracted and inspected printed pages 4, 20–21 and 93–94. No new IFAB download; original preserved.
- [API-Football guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide), `/leagues/seasons`: seasons use their starting year. [Public coverage](https://www.api-football.com/coverage) lists England National League separately from North/South/Cup; it is not a current-season API response.
- [Boreham Wood first-team calendar](https://www.borehamwoodfootballclub.co.uk/fixtures-results/) and [Solihull fixture detail](https://www.borehamwoodfootballclub.co.uk/fixtures-and-results/solihull-moors-v-bw/): the latter failed in the web reader, then succeeded in one direct public GET. No results page was accessed or website scores imported.

Applicability conclusion: the FA provisions establish incorporation by the
national governing authority, **not a direct National League operator statement
of 90 minutes**. The FA record therefore has `regulation_minutes: null`; its
fingerprinted link pins a new, exact-scope IFAB review carrying 90. The reviewer
selects the 2026/27 IFAB edition using J1.5 and the PDF's 1 July 2026 commencement;
the FA clauses do not themselves name that edition number.

Law 7 permits reduction only with prior referee/team agreement and competition
permission. Added time, penalty completion and abandonment qualify actual play;
interval, extra time and shoot-outs do not form the scheduled 90 minutes.
IFAB also permits category modifications for youth, veterans, disability and
FA-designated grassroots football. No duration derogation for this Step 1 league
was identified in the bounded review. This is not an assertion that every match
actually lasts 90 minutes. Neither senior status, profile, competition name nor
FT status supplies duration. IFAB alone is insufficient. No 2024/25 rules used.

The exact mapping entry is retained verbatim in
[source_manifest.json](national_league_2026_regulation/source_manifest.json), with
base commit, Git blob, file hash and last-change commit
`82c58f9aaf2a6237aad58abd9628753a7c409e98`. Its original `review_source` attributes
an earlier project review/catalogue capture. It is **project-reviewed evidence,
not a fresh provider response**. The entry has no season field. No separate
relevant retained catalogue was available in the inspected artifacts; no real
readiness database was read to search for one. Provider season **2026** follows
the official documented starting-year convention, not a guessed catalogue field.
Records cover only 43/2026; no implicit North/South, Cup, FA Cup, youth, friendly,
2025 or all-English-football applicability.

## Admission interval and fixture opportunity

IFAB review: `2026-09-25T12:36:32.436588Z`.
FA review: `2026-09-25T12:36:32.437646Z`.
Both must strictly precede decisions. Joint admission is:

`2026-09-25T12:36:32.437646Z < cutoff < 2026-10-02T12:36:32.436588Z`.

This is the approved maximum seven-day **local TEST/re-review limit**, measured
from the first review, not an official document expiry. No review was backdated.

The calendar confirms **Solihull Moors v Boreham Wood, 26 September 2026, 15:00**,
Enterprise National League, at The ARMCO Arena. It also lists Boreham Wood v
Kidderminster Harriers on 29 September, 19:00. Both dates are future at review and
inside admission. No postponed/cancelled marker was present in the inspected
calendar or first fixture detail. The pages do not explicitly label timezone;
Europe/London is a planning assumption requiring reconfirmation. A calendar entry
proves neither provider odds, exact TARGET, history nor candidate eligibility.

## Offline import and readiness evidence

Disposable TEST registry: `/tmp/goalvision-national-league-evidence-test/regulations.sqlite`.
It was created new using the existing CLI, followed by validate/import of both
JSON records, verify, exact resolve, import replay and resolve again. All reads
and tests after source preparation used a task-local kernel seccomp launcher
(`/tmp/national-league-source-review/offline.py`) denying network syscalls,
inherited by subprocesses. A socket attempt returned EPERM. Network namespaces
were unavailable; this did not weaken the seccomp block. No later web reads.

Resolution cutoff: `2026-09-25T12:37:04.594428Z`.
The [offline export](national_league_2026_regulation/offline_export.json) retains
the full chain, FormatEvidence, CLI action audit and registry hash. Exact replay
left registry bytes unchanged; closing/reopening reproduced the same resolution
and FormatEvidence. Canonical fingerprints:

| Proof | SHA-256 |
| --- | --- |
| IFAB retained source | `1346c7268424faf1580eb0c436d9c0ca79d0e435f87cd05470de68b14ecd2b06` |
| IFAB review | `3ead28c2c65ede2f8f0582eece7ef75b4feaf07cf8e8c1af09c7ce21cdd9f07b` |
| FA retained source | `61590aa5daa2acc4d0c18c83e5dd9a9b93822efda10ffc3f246532065f4264b4` |
| FA review | `ec2471858c8868ba4937e25eaee1e489aabb5e3c61c2ede77f676d211b7b3877` |
| Incorporation | `04db113b84e75bfa622ffba105827b5271771149d3f766f37d0fad28045e1de5` |
| Resolution / FormatEvidence proof | `95a5708f70a94244b282d619325c3f7e8731f75d13bbfd60841cf951f6abcfba` |
| Synthetic readiness snapshot | `6b74b870c5175ce1c98fd8eb341eb941a3b1bb792f0758a5221d9380604aadad` |

Source hashes commit to bounded retained objects; PDF byte hashes are separately
identified in the manifest. New records are [IFAB](national_league_2026_regulation/ifab.json)
and [THE_FA](national_league_2026_regulation/the_fa.json).

One new [rehearsal test](../../tests/test_national_league_2026_regulation_rehearsal.py)
uses existing readiness helpers and composition with the lower-division profile,
an injected clock, synthetic fixture 9999, synthetic team identities and eight
current-season history rows. Four rate features are available; the three Pi/form
features remain missing (`UNSUPPORTED_PI_STATE`, `INSUFFICIENT_SAMPLE`). Previous
season stays unverified. No model inputs or real provider payloads were collected.

The [synthetic export](national_league_2026_regulation/synthetic_rehearsal_export.json)
retains the snapshot, full regulation ledger events and report/verify/diagnostics
results after the rehearsal registry was renamed out of its original path.
Reproduction was 1 verified / 0 failed; verification left readiness files unchanged.
Actual rehearsal root:
`/tmp/goalvision-national-league-pytest/test_national_league_review_an0/synthetic-readiness`.
This is not a real prospective match observation. No live cycle or backtest was
run; prediction algorithms and model behavior are unchanged.

Tests actually executed under seccomp, using
`/home/arvis/GoalVisionAI/.venv/bin/python -m pytest -q`:

- New rehearsal file: **1 passed in 0.71s**; final annotation/export check rerun: **1 passed in 0.37s**.
- Existing regulation registry, incorporated-law, registry-readiness, UCL rehearsal
  and regulation-evidence files: **181 passed in 8.46s**.

These cover scope/timing, IFAB alone, missing/tampered chains, import immutability,
AET/PEN explicit regulation-score requirements, zero additional provider requests,
UCL evidence and golden old-unverified snapshot bytes/hashes. Data-specific checks
also preserve hashes of all original UCL artifacts and accepted rehearsal tests.
No unrelated/full-repository suite was run.

Public access: **25 web reader operations** (including find/open and two screenshot
attempts; backend HTTP count is not exposed), plus **3 direct public document/page
GETs**. **Football API calls: 0.** Document access is separate from provider API
access; no credentials were used or printed. Full downloaded documents remain
outside Git; only bounded reviews, identities and fingerprints are committed.

## Later manual observation, not executed

Existing exact review opens within 75 minutes of kickoff; early due review requires
more than 10 minutes' lead. The shortlist is bounded to five and prioritizes major
competitions. Exact TARGET uses a two-minute TTL; final-review freshness is five
minutes. For the listed 15:00 UK kickoff, **26 September 13:00–13:20 UTC**
(14:00–14:20 BST; 15:00–15:20 Berlin) is a reasonable manual observation window,
subject to reconfirming kickoff/timezone/status and evidence validity. This is a
recommendation, not a scheduled action.

The normal bounded cycle may never reach league 43: major competitions rank first,
National League priority depends partly on unmeasured provider capability, and
shortlist/quota/current odds/canonical eligibility can prevent an observation.
There is no fixture-specific flag and no guarantee of a pick. Discovery/ranking,
request strategy and existing retry behavior were not changed.

Later only, with authorized existing football credentials available to the normal
runtime, use the fresh root below. Do not shell-source `.env` or change credentials.
The existing readiness `cycle` explicitly sets `send=False`; it has no separate
`--no-send` flag. The root below has not been initialized by this task.

```bash
set -e
cd /tmp/goalvision-national-league-evidence
test ! -e /tmp/goalvision-national-league-prospective-20260926
/home/arvis/GoalVisionAI/.venv/bin/python -m app.prematch_football_context.readiness \
  --root /tmp/goalvision-national-league-prospective-20260926 init
/home/arvis/GoalVisionAI/.venv/bin/python -m app.prematch_football_context.readiness \
  --root /tmp/goalvision-national-league-prospective-20260926 cycle \
  --environment TEST --observe --max-calls 40 --horizon-days 1 \
  --regulation-registry /tmp/goalvision-national-league-evidence-test/regulations.sqlite
```

| Separate status | Result |
| --- | --- |
| Public fixture calendar | CONFIRMED at review |
| Provider competition/season mapping | SUBSTANTIATED as project mapping plus official season convention |
| Regulation proof | IMPORTED, VERIFIED_90 within local interval |
| Current provider odds / exact TARGET / history availability | NOT YET MEASURED |
| Real prospective snapshot | NOT YET COLLECTED |
| Real cycle executed | **NO** |

Official unchanged; LIVE remains disabled. No Telegram, production/existing real
readiness DB access, backfill, historical odds, model training/calibration, Phase E,
publication, stake, timer, startup, merge, deployment or push occurred.
