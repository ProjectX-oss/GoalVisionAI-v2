# Prepared deployment package — blocked, never executed

This directory is an inert review package. No installer runs during development.
The service remains no-send even if LIVE_SEND_ENABLED is mistakenly set.

Before deployment approval:

1. Resolve the quota/market blockers in `docs/LIVE_V2_PRIVATE_FOUNDATION.md`.
2. Review the exact commit, focused tests and bounded rehearsal evidence.
3. Build a separate release from that commit under `/opt/goalvision-live-v2/releases/`.
   Use its own Python environment; never change the PREMATCH installed release or environment.
4. Populate `/etc/goalvision-live-v2/private.env` from operator-controlled secrets.
   Require a positive fixed private chat ID, expected LIVE bot ID/username and `/start`.
5. Review competition coverage and supply reviewed competition IDs to ExecStart.
6. Create only `/var/lib/goalvision-live-v2`, owned by the LIVE service user (0700).
7. Install ONLY the two LIVE units here. Confirm the PREMATCH units/release checksums
   are unchanged. Enable only the LIVE timer after explicit deployment approval.
8. Observe the first no-send opportunity and its evidence before separately reviewing
   a production send composition. This foundation exposes no operator send command.

`disable-live-v2` disables and stops only `goalvision-live-v2-private.timer`.
It neither stops PREMATCH nor edits any PREMATCH configuration. It does not retract
messages, erase evidence, or abort an already executing opportunity.

A future send composition must call the frozen-preview delivery service with the
explicit confirmation contract. Environment enablement alone cannot send.
