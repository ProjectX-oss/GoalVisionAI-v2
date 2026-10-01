# Current-odds de-vig comparator — 2026-10-01

Status: PASS (math/contracts/offline integration); NEEDS_MORE_EVIDENCE (forward outcomes).
No production deployment, historical bookmaker odds or new provider calls.

app/adaptive_lab/devig_research.py implements:
- Existing Decimal multiplicative normalisation as the reference.
- Numerical Shin with bounded root solving; underround is explicitly inapplicable.
- Power with a bracketed normalisation root.
- OO-EPC Algorithm 5, including its explicitly recorded multiplicative fallback
  if an adjusted outcome would be nonpositive. No silent probability clamp.

Each method uses a complete two/three-outcome market from the same bookmaker,
fixture, quote source timestamps and fingerprints. Capture rejects stale,
post-kickoff, incomplete, duplicate or mismatched evidence. The discovery runner
stores a separate devig_research sibling after candidate selection, with a
frozen model-probability reference for disagreement metrics. Existing
market-consensus probabilities and selection inputs are unchanged.

Forward evaluation uses the first capture per fixture/bookmaker/market family,
later resolved scores only, with explicit counts. Repeated cycles do not create
extra samples. Metrics include Brier/log loss/ECE, favourite/other bias,
difference from multiplicative and model-market disagreement. Bookmaker samples
are correlated and are not independent model-learning observations.
No method is declared better before adequate forward evidence.

Primary specifications:
https://www.sciencepublishinggroup.com/article/10.11648/j.ajss.20170506.12
https://arxiv.org/html/2604.17194v1 (Algorithms 2, 4, 5)
Only odds-only mathematics is used; no historical-odds dataset or FL-GLM fitting.

Validation: 74 focused de-vig/runner tests pass. Coverage includes fair-market
invariance, Shin's binary additive equivalence, power sum root, OO-EPC equal
standard-error adjustment and documented fallback, stale/identity rejection,
no source mutation, first-capture deduplication and future-result exclusion.
Changed: devig_research.py, runner.py, test_devig_research.py.
