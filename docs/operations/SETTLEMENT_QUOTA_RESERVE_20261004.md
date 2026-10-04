# Settlement status reserve repair — operator deployment only

The 2026-10-04 operator diagnostic records 12 settlement starts failing before HTTP with 86 local daily slots remaining. The status preflight used STATUS, which preserves 100 slots, although SETTLEMENT is the intended consumer of that reserve.

The change gives this existing initial request the SETTLEMENT category and explicitly permits its initial NOT_OBSERVED preflight. Daily/minute accounting, request limits, exact observed provider headers, zero-quota refusal, discovery reserve and contention handling remain unchanged. No additional request is introduced. Prediction/selection code, thresholds and champion are unchanged.

The package is pinned to the installed combo-market-parallel-abddde7 release. Its overlay contains only app/adaptive_lab/quota.py and app/lab_combo/cli.py. Build and default wrapper modes are read-only with respect to services. --apply requires the operator; it drains active workers without starting a manual cycle, preserves timer states and leaves research/ADMIN/weekly routes untouched.

Do not apply an older PREMATCH package over this baseline. No deployment or rollback is authorized for the agent. The consolidated Watch report records the final package and commands.
