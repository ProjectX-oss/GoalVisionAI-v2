# Prepared PREMATCH quota hardening package

No installation action is included or executed. The package is a frozen review
payload: two complete application trees, exact before/proposed service drop-ins,
release environments, a separately reviewed ADMIN mapping patch, and a pinned
manifest. `verify_package.py PACKAGE --sha256 MANIFEST_SHA256` is read-only.
The report records the manifest and archive hashes. Copy/extraction alone cannot
change a service route. Do not route production imports to the development tree.

## Proposed upgrade

- Discovery, settlement, observer and weekly reporting use the patched `23e57e9`
  lineage. Their existing drop-ins change only the release EnvironmentFile path.
- Daily research currently uses `363f567`. Its separate payload retains that
  complete lineage and replaces only repository, prepared batch, observation,
  AutoML and governance persistence files. A new service-only environment drop-in
  selects it; the shared legacy environment file is untouched.
- No timer, ExecStart, provider budget, reserve, model, selection threshold,
  publication flag, destination, schema, database or historical row changes.
- The ADMIN patch changes only one code mapping on `d811177`; it is a separate
  application change, not bundled into PREMATCH imports. Its sender stays disabled.
- The five changed persistence files are shared implementation only. Research
  eligibility, metrics, comparisons, candidate fitting and model thresholds are
  byte-identical to the installed research lineage.

## Future operator installation and bounded rollback contract

Installation requires a separately authorized maintenance operation. This package
has no self-installing script, post-install hook, service invocation or API probe.
Use an operator-reviewed deployment controller that implements the following exact
contract; the existing four-service controller cannot cover the fifth research
route unchanged. Do not point that older controller at this manifest.

1. Verify the pinned manifest and every package byte. Verify all five current
   service fragments, drop-ins, loaded commands, timer routes and preserved flags
   against the report and before bytes. Reject unknown drop-ins or configuration
   changes. Confirm ADMIN sender disabled through its normal privileged readback.
2. Take the existing installer coordination lock. Fence new starts for exactly
   these five services while preserving timer schedules and enablement. Do not
   kill a running producer, delivery or learning job. Wait at most 60 seconds for
   all five to become inactive. On timeout, remove the temporary fence and abort
   before replacing any persistent configuration.
3. After the drain, revalidate all before hashes and atomically/fsync replace only
   the five proposed drop-ins. Preserve the old release trees and rollback bytes.
   Reload systemd, verify loaded environment routes, commands and flags, then
   remove only the temporary fence. Let existing timers invoke normal cycles.
4. A failure during replacement must restore the exact before bytes (including
   send=true). The research target was absent: remove it only if its hash equals
   the proposed hash. Reload, verify the previous routes, and remove the fence
   only after all five agree. Preserve recovery evidence on an unresolved error.
5. A later rollback follows the same fence/drain/revalidation sequence with a
   60-second drain ceiling and individually bounded systemd commands (5 seconds).
   Restore four supplied before files and remove the exact research drop-in.
   Restore code/configuration only. Never restore/replace a database, delete quota
   claims or publications, revert results, or change sender/publication flags.

Installation and rollback were not executed. The supplied before/proposed bytes
and this bounded operator procedure are the rollback package. The read-only
verifier has no installation side effects; no automated deployment is included.
