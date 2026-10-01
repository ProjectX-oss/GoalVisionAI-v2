# Lab accuracy COMBO policy — 2026-10-01

## Confirmed incident

Read-only inspection of the running b6bca3f discovery release and Lab ledger
confirmed nine SINGLE Telegram receipts on October 1 through 12:35 UTC,
and no COMBO receipt in those cycles. Eight of those nine singles had
non-positive expected value under the system's own retained probabilities.
SINGLE uses the approved accuracy-first policy (p >= 0.55, odds >= 1.30).
COMBO still uses the old APPROVED/READY, positive-EV, independent-evidence
policy. More SINGLE publications therefore do not imply three eligible
COMBO legs. The last inspected discovery completed successfully.

This is a policy mismatch, not evidence of a Telegram outage. Negative EV
is a mathematical estimate from the existing model, not an observed loss.
No odds were acquired and no live cycle or Telegram send was initiated
during this work. The existing scheduled services continued independently.

## Prepared behavior

The new explicit option is --accuracy-combos with --label-v2-selections,
or GOALVISION_LAB_ACCURACY_COMBOS=1 in the immutable discovery release
environment. It is off by default. Policy:
LAB_COMBO_ACCURACY_FROM_SINGLES_V1.

It takes the current cycle's accuracy-approved SINGLE candidate pool,
chooses one highest-probability market per fixture, and builds at most three
disjoint 3-leg combos, ranked by the product of the estimated probabilities.
Already-published singles can supply legs; their published messages are
never rewritten. A prior claimed combo fixture cannot be used again.
Different fixtures with the same team remain excluded within each combo
and batch. No candidate is loaded from an old published ticket to pretend
that its quote or review is still fresh.

Every leg keeps its original decision, failures, quote and signal evidence.
NON_POSITIVE_VALUE is the only allowed source failure, exactly as for
accuracy SINGLE. Identity, source replay, freshness, publication windows,
Lab bot/destination, explicit origin, preview integrity and exactly-once
claims are checked before delivery. Too few suitable legs produces an
explicit reason, not a forced combo.

The policy can create a combo with negative estimated EV. This is an
experimental accuracy-first change, not an improvement in demonstrated
profitability. Products of probabilities/EV are retained only with
INDEPENDENCE_ASSUMED_NOT_VERIFIED; distinct teams do not prove independence.
The public preview labels the experiment and says all three selections
must win and estimated value may be negative.

Legacy combo selection is unchanged when the option is off. SINGLE policy,
Official, LIVE, provider quotas, source predictions, settlement rules,
separate Lab ledgers and historical results are unchanged. New-policy
settlement uses the existing generic three-leg WON/LOST/VOID/PARTIAL_VOID
handling, including automatic result notifications under existing scheduling.

## Operator package

/home/arvis/goalvision-operations/lab-combo-accuracy-20261001

Read-only package verification:

    python3 /home/arvis/goalvision-operations/lab-combo-accuracy-20261001/update.py

After explicit approval of this policy and deployment:

    sudo python3 /home/arvis/goalvision-operations/lab-combo-accuracy-20261001/update.py --apply

Rollback:

    sudo python3 /home/arvis/goalvision-operations/lab-combo-accuracy-20261001/update.py --apply --rollback

The installer checks hashes against the entire immutable b6bca3f application,
stages a new immutable release, and changes only the discovery route using
zz-accuracy-combo-20261001.conf. Other service routes are compared unchanged.
It temporarily pauses the discovery timer and allows an active discovery
up to 60 seconds to finish; otherwise it refuses and restores timer activity.
No active discovery is killed and no manual discovery/send is invoked.
Prior active scheduling resumes and may then send eligible real Lab combos.
A previously inactive timer stays inactive. Rollback restores b6bca3f
without deleting any prediction, claim, receipt or settlement.

Production activation is pending. AGENTS.md section 13 requires explicit
approval for publication-policy changes and production deployment.
The concrete decision is whether Lab COMBO may use accuracy-approved
SINGLE candidates even when their estimated EV is non-positive.

## Validation

Offline tests block real sockets. Coverage includes negative-EV opt-in,
nine candidates producing three disjoint combos, missing quality evidence,
stale quotes, source/aggregate/preview tampering, origin and bot identity,
already-published singles, immutable replay, unknown delivery and no resend,
CLI-to-ledger fake transport delivery, legacy policy regression, settlement
compatibility, package hashes, idempotent installation and rollback.
This is software validation, not evidence of betting performance.

Verification completed: 262 adjacent regression tests passed, followed by
97 focused tests after package integration and 35 final new-policy/package
tests after adding environment opt-in coverage. These runs overlap and must
not be summed. Compilation and git diff whitespace checks passed.
