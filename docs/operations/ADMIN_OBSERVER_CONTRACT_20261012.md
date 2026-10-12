# ADMIN observer output compatibility — 2026-10-12

Incident 8c440c57f2857c55f96954b8, invocation a54d7838f7c44048b1ed2ae95e2b8b99: observer exited 0 and emitted a complete 11,562-byte final document. The new PREMATCH producer correctly reports LIVE=NOT_EVALUATED and LIVE_SCOPE=PREMATCH_OBSERVER. ADMIN still required the old misleading LIVE=DISABLED literal. In the journal window since 2026-10-11 05:00 UTC, 22 of 49 observer outputs were rejected solely due to this field.

The one-file fix accepts the scoped new pair and retains legacy compatibility, all existing final-artifact fields and exact journal InvocationID attribution. It neither changes LIVE timers nor suppresses genuine missing output. Existing bounded historical rechecks can recover matching incidents on natural ADMIN scans after operator installation, preserving old evidence, sent receipts and other incident types. No manual scan, recovery write or Telegram send occurred.

Verification: 539 tests and 93 subtests passed with outbound network denied. Added invalid scope/missing fields/no API/no send regressions and both-format exact recovery including unrelated invocation isolation. The user's exact journal artifact passed offline recognition and exact-invocation replay. Root-only ADMIN DB remains unread by the agent; journal evidence is authoritative for this output defect, but not a complete enumeration of private ADMIN incidents.

A separate real quota contention issue was also found and is being addressed by the batch quota-reader change. Neither that issue nor a learning-readiness block should be classified as this false alert. The two reviewed source changes will use one operator package based on the actual installed releases. No production deploy by the agent.
