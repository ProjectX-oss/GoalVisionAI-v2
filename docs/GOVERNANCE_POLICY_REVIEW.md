# Governance Policy Review

The review is independent of forward-test outcomes. It fingerprints the exact frozen governance policy, classifies every parameter, and checks warning/block ordering, recovery hysteresis, stale-evidence limits, insufficient-sample behavior, market isolation, and integrity-wide blocking. Outcomes are `PASSED`, `PASSED_WITH_WARNINGS`, `BLOCKED`, or `INCOMPLETE`.

Run `python -m app.lab_launch_readiness review-governance-policy --database <LAB_DB> --output json`. Approval is a separate append-only action and requires `APPROVE_GOALVISION_LAB_GOVERNANCE_POLICY`. Revocation requires `REVOKE_GOALVISION_LAB_GOVERNANCE_POLICY`. A revoked approval cannot authorize a launch.
