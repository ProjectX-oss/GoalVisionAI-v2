# One-COMBO receipt recovery — operator runbook

Status: **BLOCKED_NEEDS_MORE_EVIDENCE** until the authenticated private owner replies to the original message. Preparing this tool does not repair the live ledger.

## Exact incident

- Prediction: `lab-v2-combo-accuracy-e1f7df2f5ab623619b141a4045aaf627cb287cd813124a887ba04ce6ce61f808`.
- COMBO Tirgus tests #1: France–Belgium, Northern Ireland–Georgia, Liptovský Mikuláš–Šamorín.
- Prediction created 2026-10-05 09:01:42 UTC; delivery timed out at 09:01:59 UTC.
- Frozen original body SHA-256: `3fe9f6530daee2dce50bbaf83a37f4e4cbc41c8519436121b7b7a014f8e137a3`.
- The user's pasted message exactly matches the frozen body. This is an attestation, not a Telegram receipt or a trustworthy message ID.
- Original claim and `delivery_unknown` exist. Original receipt, settlement and result receipt were absent at preparation.
- Existing settlement deliberately excludes this uncertain publication. The missing receipt must be reconciled before its natural settlement can proceed.

## Scope and safeguards

The operator tool binds one exact case to the original prediction/claim/unknown fingerprints, frozen route, body hash and original send-time window. It does not infer the result or resend the prediction.

Default mode only reads the ledger and the existing pinned runtime guard. `--capture` makes at most three Telegram reads: `getMe`, `getWebhookInfo`, `getUpdates(limit=100, timeout=0)`. It never supplies `offset`, `allowed_updates`, or `drop_pending_updates`. It refuses an active webhook; it does not change webhook/polling configuration or acknowledge updates. Unrelated updates are discarded in memory and never logged. Incoming updates expire at Telegram, so capture/apply must happen promptly after the owner reply.

The match requires the existing private owner, exact challenge, original bot, exact original body, chat, valid numeric message ID, and original timestamp. Forwarded/edited/ambiguous originals fail closed. No token, private recipient ID, original message ID or captured update is stored in Git.

`--apply` is a separate **manual operator action**. It requires root for protected guard verification, re-reads Telegram and requires the live proof to match the captured proof. Before opening the writable ledger, it drops to the ledger owner `arvis` to avoid root-owned journal/WAL files. One transaction appends exactly `delivery_reconciliation` and the original `receipt`; failures roll back both appends. It never updates/deletes historical evidence. Repeat apply is a no-op after the matching reconciliation exists.

The reconstructed receipt uses the **original Telegram message timestamp**, with explicit reconciliation source/provenance and today's confirmation timestamp separately. Historical unknown/claim/economic-claim evidence remains intact. Existing natural settlement may then produce the result and reply to the original message; no manual cycle is run by this tool. A reply/result is not guaranteed until natural settlement has sufficient result evidence.

No service, release, timer, model, selection, threshold, quota, bankroll, staking, Official, LIVE or ADMIN Codex setting is changed. Football provider calls = 0. Telegram sends by the tool = 0. No new listener is installed.

## Operator sequence

The staged entry point is `/home/arvis/goalvision-operations/combo-receipt.py`. Its package and source files are SHA-256 pinned.

1. Run the read-only plan:

   ```bash
   python3 ~/goalvision-operations/combo-receipt.py
   ```

2. In `@GoalVision_AI_Combo_Bot`, open the **original COMBO #1** with the three matches above. Use Reply / Ответить on that message and send the exact challenge printed by the plan. A fresh message without Reply is insufficient. Do not forward it or send a screenshot.

3. Capture the original ID, without changing the ledger:

   ```bash
   python3 ~/goalvision-operations/combo-receipt.py --capture
   ```

   Required outcome: `COMBO_ORIGINAL_REPLY_VERIFIED`. The minimal proof is saved outside Git in a 0600 file under `/home/arvis/goalvision-private/`. Do not paste that file or credentials into chat.

4. Only after a successful capture, manually reconcile:

   ```bash
   sudo python3 ~/goalvision-operations/combo-receipt.py --apply
   ```

   Required outcome: `COMBO_RECEIPT_RECONCILED`, or `COMBO_RECEIPT_ALREADY_RECONCILED` on repetition. This is a receipt-data repair, not a deployment. Do not start settlement/discovery manually and do not send a test.

5. Let the existing natural timer run. Verify receipt binding, settlement/result receipt and whether the original message receives the result. Preserve uncertainty if provider result evidence is absent.

Any `BLOCKED` result requires inspection. Do not edit the pinned case, guess an ID, delete unknown/claim evidence, advance Telegram offsets, or bypass fingerprint/runtime guards. A new release/config or an expired challenge requires a separately reviewed refreshed package.

## Validation

Focused offline suite: `tests/test_combo_receipt_recovery.py`. Socket connections are disabled throughout the suite. Coverage includes wrong owner/chat/bot/body/date, edited/forwarded messages, ambiguous parents, expired challenge, repeat replies, fixed read-only methods, webhook blocking, secret-free HTTP failures, no redirects, hash drift, atomic rollback, immutable evidence, idempotence, forged capture rejection, uid drop, and compatibility with the installed route/reply contracts.

Official Bot API references: [getUpdates](https://core.telegram.org/bots/api#getupdates), [Message](https://core.telegram.org/bots/api#message), [getWebhookInfo](https://core.telegram.org/bots/api#getwebhookinfo). No offset is used: the documented acknowledgement happens when an offset beyond an update's ID is supplied.
