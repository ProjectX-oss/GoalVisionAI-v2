# LIVE final-review budget review — 2026-10-10

Status: **PASS_READY_FOR_OPERATOR / NO_CHANGE**, already installed by the operator.
This task did not install or restart anything.

Source fix: `a4cdfa1043ec69c2838794371ba0a57d4163f50d`.
Existing reviewed branch: `fix/live-final-review-budget-20261009`,
head `2a5f6887bc3d8b39975653952b79c30144fbaae3`.
Actual LIVE release at 19:47 Riga:
`/opt/goalvision-live-quota-reader-3d4f5c5-20261010`.
Its runner, service, worker, engine, selection and daypart source hashes match
the reviewed source. Do not reinstall the older release over this successor.

For an allocated cycle ceiling B, initial discovery can use at most max(0, B−9)
HTTP attempts. Final refresh can use the remaining ceiling. Fixture state,
events and exact odds each allow at most three attempts: 3×3=9. Retries are
counted before HTTP and cannot spend the reserved tail in discovery. Existing
cached history/catalog are reused. The original ceiling is restored in finally.
The reserve is a local attempt allowance, not a guarantee of upstream data or
shared daily/minute quota availability. Quota exhaustion, partial state and
failed HTTP refresh still reject publication without claims or receipts.

Extended fake-provider end-to-end tests exercise three attempts per each of
the three final endpoints, complete HTTP failure, missing final fixture and
provider quota exhausted during final review. Success uses exactly nine final
attempts; failures send nothing; all stay within the unchanged 35-attempt test
ceiling. Existing tests cover discovery retries, tiny budgets, probability
boundaries, supported markets and final-review isolation. No prediction,
ranking, publication policy, API ceiling or safeguard changed.

Verification: 1088 tests and 5 subtests passed in the adjacent offline matrix;
the LIVE/new-calibration focused run was 34 passed. All socket connections and
DNS were denied. Telegram was fake transport only. Actual provider calls and
Telegram sends initiated by this work: zero.

Natural evidence at the fixed 19:47:52 Riga cutoff: the current 60–70% cohort
has six confirmed publications (two wins, one loss, three pending). On Oct 10,
one final refresh explicitly reports shared/provider quota blocked, and five
report no matching final quote. These are distinct from the fixed discovery
budget defect. Do not remove state/quote checks to turn them into publications.

Operator action: **no installation is needed for this existing fix**. Use the
main recovery report for the separate LIVE desired-state mismatch and the
remaining calendar-reader lock fix. Do not run a manual worker or test send.

## Read-only verification resumed on 2026-10-11

At 11:05:21.700896 UTC (14:05:21 Riga), the installed successor remains
`goalvision-live-quota-reader-3d4f5c5-20261010`. Worker, runner, service,
engine, selection and daypart hashes were rechecked against the reviewed source.
The premise that the reserve fix is still undeployed is therefore false.

Focused offline regression: 64 passed. Adjacent regression: 841 passed across
36 files; the four fake-provider final-review scenarios are included. This
resumed task initiated zero real provider calls, Telegram sends, deployments or
worker cycles. Earlier 1088-test evidence above belongs to the October 10 run.

LIVE actual evening timer is ACTIVE/ENABLED while installed observer reports
hardcoded DISABLED. The existing source health fix is already reviewed; it is
not installed. This mismatch does not invalidate the reserve arithmetic, and
requires a separate operator decision. Calendar-reader lock contention is a
separate remaining defect. See the final recovery report for current evidence.
