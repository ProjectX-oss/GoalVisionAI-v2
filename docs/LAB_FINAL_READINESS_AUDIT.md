# LAB Final Readiness Audit

The final audit fails closed unless schema 42, an active approval and authorization, exact model/calibration bindings, LAB isolation, manual-only execution, disabled scheduling, disabled automatic sending, non-synthetic operational evidence, and database integrity are present. Outcomes are `LAB_LAUNCH_READY`, `LAB_LAUNCH_READY_WITH_WARNINGS`, or `LAB_LAUNCH_BLOCKED`.

The audit performs no provider request and constructs no Telegram transport. A stale capability cache is a warning; schema, authorization, isolation, scheduler, automatic-send, model, calibration, or synthetic-evidence failures block.
