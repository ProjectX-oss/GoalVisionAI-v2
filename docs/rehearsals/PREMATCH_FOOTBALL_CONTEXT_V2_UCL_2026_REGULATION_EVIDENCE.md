# First genuine UCL 2026/27 regulation evidence — isolated TEST

Verdict: **VERIFIED_90**, for the standard scheduled regulation format only.
This is an AI-reviewed public-source chain, not a claim of personal human review
or a guarantee that any particular fixture completes 90 minutes.

Starting commit: `e93b8072ad3ac2d902c17b548e58beef5c70e60a` (requested base).
Starting worktree: `/tmp/goalvision-regulation-evidence`, clean; starting branch:
`codex/prematch-football-context-v2-incorporated-law`.
Delivery branch: `codex/prematch-v2-ucl-2026-regulation-evidence`.

## Sources and applicability

The existing contracts, initializer, CLI, repository, resolver, FormatEvidence
bridge and incorporated-law report were reused. No repository-wide audit was
repeated. Retained material is in [source_review.json](ucl_2026_regulation/source_review.json),
[ifab.json](ucl_2026_regulation/ifab.json) and [uefa.json](ucl_2026_regulation/uefa.json).
These contain bounded excerpts, paraphrases, document identities and hashes;
no full copyrighted document is committed.

- [API-Football public guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide):
  the practical tips identify Champions League as ID 2 and describe stable league
  IDs; `/leagues/seasons` explains the starting-year convention. Therefore this
  review maps 2026/27 to `API_FOOTBALL / competition_id=2 / season=2026`.
  This does not attest provider fixture availability or coverage.
- [UEFA Article 13](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-13-Competition-stages-Online):
  13.01 expressly incorporates IFAB Laws for all competition matches; 13.02 lists
  the stages. The retained 16-word excerpt is incorporation, not duration wording.
- [UEFA Article 1](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-1-Scope-of-application-Online?contentId=AWNVKC73_Ud10i2HCbMr4g):
  1.01 establishes the 2026/27 competition scope, including qualifying/play-offs.
- [UEFA Article 96](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-96-Adoption-and-entry-into-force-Online?contentId=Xb72NoiAqwnadXykMvZmlA):
  adopted 11 February 2026; effective 1 March; amendments effective immediately
  on 20 May and 29 July 2026. The displayed enforcement date is 29 July 2026.
  The bare requested URL failed twice; its directly linked content-ID URL worked.
- [IFAB catalogue](https://www.theifab.com/laws-of-the-game-documents/) identifies
  the actual English 2026/27 single-page edition. Its
  [edition-specific PDF](https://downloads.theifab.com/downloads/laws-of-the-game-202627-single-pages)
  was downloaded and inspected locally: printed p. 4 gives effectiveness from
  1 July 2026; pp. 20–21 cover modifications; pp. 93–94 contain Law 7.
  The 23,437,157-byte PDF SHA-256 is
  `89398520b353c6d995a1bb2557c97dc3c5aa1712c1d3009589f580a5a23c6a7d`.
  The catalogue's query-bearing download and query-free registry URL returned
  identical PDF hashes. The supplied
  [latest Law 7 page](https://www.theifab.com/laws/latest/the-duration-of-the-match/)
  was inspected for orientation; it is not the pinned authority.

The IFAB record carries 90 minutes. The UEFA
`IncorporatedCompetitionRegulation` has `regulation_minutes=null` and pins the
exact IFAB review ID and fingerprint. Article 13 does not explicitly name an IFAB
edition: choosing the effective 2026/27 edition is the dated reviewer inference
supported by the official catalogue and PDF, not a quotation attributed to UEFA.

Law 7 permits reductions only with prior referee/team agreement and competition
permission. Lost-time allowance and penalty completion may extend play;
abandonment may prevent completion. General modification permissions include
youth, veterans, disability and grassroots categories. The reviewed material
does not displace the standard scheduled UCL format. UEFA's directly linked
[Article 28](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-28-Completion-of-suspended-matches-Online?contentId=JPk7Ltwo5tad5wvXjGvc~Q)
also addresses completion of suspended matches. These qualifications prevent a
universal actual-duration claim; they do not prevent the narrower scheduled-format
verdict. No fixture-specific exception was investigated or cleared.

## Review times and validity

Reviewer/process: **OpenAI Codex AI assistant**, reviewing retrieved primary
documents in this authorized task. No human/operator personal review is asserted.

| Event | Actual UTC time |
| --- | --- |
| First successful edition PDF access | 2026-09-25 10:40:44.429592–10:40:44.951221 |
| Final guide / Article 13 / Article 96 / catalogue access batch | 2026-09-25 10:44:54–10:44:57 |
| Query-free edition PDF confirmation | 2026-09-25 10:46:25.555376–10:46:26.173657 |
| IFAB review | 2026-09-25 10:48:14.001943 |
| UEFA review | 2026-09-25 10:48:14.003016 |
| Resolution cutoff | 2026-09-25 10:49:04.203446 |

The manifest records access intervals for all inspected sources, including wider
bounds where per-request wall-clock timestamps were not captured. Web crawl dates
are not local access/review times. Official adoption/amendment dates above are
not substituted for review times.

The existing contract defines `source_effective_from/until` as a half-open UTC
**decision applicability interval**. Each record starts at its actual review and
ends at `2026-09-26T00:00:00Z`, an explicitly local next-UTC-day re-review cap.
This conservative TEST limit does **not** assert that either publisher's document
expires then or that its applicability cannot change. Both editions were already
effective when reviewed. The records do not establish historical review knowledge
or validity for the rest of the season. `validity_start/end=null` means exact
season 2026, not unlimited seasons. The successful cutoff lies strictly after
both reviews and inside both intervals. A later decision requires fresh
resolution; after this local cap, fresh reviewed evidence is needed.

## Offline import, complete proof and reproduction

Public retrieval stopped before record preparation/import. Socket connection and
HTTPX transport guards blocked networking during import and the focused suite.
The existing CLI initialized a new disposable registry at
`/tmp/goalvision-ucl-2026-test-g43j0wkj/registry.sqlite`, validated/imported both
records and verified two intact records. No pre-existing operational database was opened.

[offline_export.json](ucl_2026_regulation/offline_export.json) retains the complete
resolution, both complete records, embedded incorporation, FormatEvidence,
verification, exact CLI arguments and proof hashes. The registry was closed and
reopened; canonical resolution and FormatEvidence reproduced exactly. Reimporting
both records left the registry bytes unchanged.

| Proof | SHA-256 |
| --- | --- |
| IFAB record | `018d2f66f301441c3be0dac4e5c9bd6791249da70d0cf6b6b5fd64fe76e2c217` |
| UEFA record | `731a37d43eaad8ee5d0ed0f4913cc23c4f979b3404e5f91b42c34ec9827eb566` |
| Incorporation | `419bc8c564d2787a9e307bc0ceb51e60bdf47628bb7ec0c27665a370e260eb71` |
| Complete resolution / FormatEvidence proof hash | `df43ee514e22b710a79eb8e6faff60addf3b7bc5b3830ac86d95a4b5b1aa4207` |

Record source-content hashes commit to bounded retained source objects, not to
downloaded HTML/PDF bytes. The separate PDF hash identifies the downloaded file.
Hashes establish consistency, not independent authentication of reviewer judgment.

## Checks and exact tests

The existing suites and the small real-record rehearsal check passed:

- IFAB alone, wrong competition/season, before/equal-review cutoffs and expired
  local validity are unverified.
- Missing chains cannot bridge; tampered imports are rejected; corrupted stored
  chain content resolves unverified. Exact replay is idempotent.
- AET/PEN still require explicit regulation fulltime scores. The final rehearsal
  check exercises all four present/missing score cases using this actual UCL
  FormatEvidence and clearly synthetic fixture payloads. Final 4–3 goals cannot
  substitute for absent regulation scores; explicit 1–1 scores remain 1–1.

Interpreter: `/home/arvis/GoalVisionAI/.venv/bin/python`.
Executed a Python heredoc that blocks `socket.socket.connect`,
`socket.create_connection`, `httpx.HTTPTransport.handle_request` and
`httpx.AsyncHTTPTransport.handle_async_request`, then calls:

```python
pytest.main([
    'tests/test_prematch_football_context_regulation_registry.py',
    'tests/test_prematch_football_context_incorporated_law.py',
    'tests/test_ucl_2026_regulation_rehearsal.py', '-q',
])
```

Result: **113 passed in 2.83s**. After adding the genuine-chain AET/PEN cases,
executed `python -m pytest tests/test_ucl_2026_regulation_rehearsal.py -q`:
**1 passed in 0.36s** (the test blocks those same network paths).
`git diff --check` passed. No unrelated historical/ML suites were run; no
prediction algorithm changed, so no training or predictive backtest was performed.

Offline reproduction from the committed artifacts uses that small rehearsal test:
it creates a fresh registry, imports both records, resolves at the retained cutoff,
compares the complete export/proof and repeats the negative checks. No public
document download is needed for reproduction.

## Retrieval accounting and isolation

Public-document activity: **20 web open/click operations**, **4 web find
operations**, and **3 direct download attempts** (one 403, two successful).
The first successful direct download followed a redirect. Web-reader PDF attempts
hit size limits; the successful local PDF was decoded using temporary local
standard-library code and its embedded font mappings. The web tool does not expose
its underlying HTTP/cache/redirect count; these are tool-operation counts, not a
claim of exact total HTTP requests. **API-Football API calls: 0.**

Only four bounded evidence JSON files, this report and one small rehearsal test
are committed. No `app/` code, schema, formulas, runtime/readiness composition,
previous snapshots or existing real evidence changed. No production database,
credentials, live football cycle, bookmaker odds, training, calibration,
activation, Phase E, Telegram, Official, bankroll/statistics, scheduling,
deployment, merge or push activity occurred. LIVE remains disabled.

REAL_EVIDENCE_IMPORTED_AND_VERIFIED
