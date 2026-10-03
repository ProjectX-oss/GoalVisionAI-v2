# PREMATCH settlement replies — 2026-10-03

User request: send the WIN/LOST result as a Telegram reply to its original
prediction, so the user can open that bet directly. Applies to SINGLE and COMBO.

## Behavior

With GOALVISION_LAB_SETTLEMENT_REPLIES=1, each unsent settlement binds to the
confirmed original prediction receipt, never to the most recent chat message.
The original chat and positive integer Telegram message ID are required.
Prediction messages remain unchanged. Existing route checks preserve old Lab
COMBO results in the Lab channel and new COMBO results in the enrolled private
@GoalVision_AI_Combo_Bot conversation. No token or recipient changes are needed.

Text and photo-caption results both use Telegram ReplyParameters with
allow_sending_without_reply=True and no cross-chat destination. If the parent
was deleted, Telegram can deliver the result without the parent in that same
request. The application never sends a second fallback request. A confirmed
reply parent is checked against the requested message ID and original chat.
An absent parent in the response is recorded as NOT_CONFIRMED, not as a
confirmed threaded reply. A mismatched parent is an ambiguous delivery
requiring reconciliation, with the durable claim retained and no retry.

Claims and receipts retain the immutable reply binding. The existing terminal
claim checks precede reply configuration, so toggling the flag or rolling back
cannot resend an already attempted result. Prior result messages are not edited
or replayed. Existing open bets with a confirmed original receipt can use replies
when their first result is naturally sent after activation.

WON, LOST, VOID and COMBO PARTIAL_VOID notifications use the same behavior.
Early COMBO loss still announces once; later remaining-leg tracking does not
create another economic result or message. Settlements and statistics are
unchanged. The default flag value is 0 until explicitly enabled by the operator.

## Exact-base operator update

Installed base independently checked:
 /opt/goalvision-prematch-combo-bot-9a3b198-20261003

Three runtime overlay files: Lab service, Lab-only transport, and the new
settlement_reply helper. The shared Official Telegram transport is unchanged.
The complete candidate is exactly the 817-file installed application/frozen-plan
manifest plus those reviewed changes (818 files including the new module).

After the pinned package has been prepared:

    python3 ~/goalvision-operations/settlement-replies.py
    sudo python3 ~/goalvision-operations/settlement-replies.py --apply

Apply validates the installed base, package hashes, existing enrolled COMBO
configuration, ReplyParameters dependency, exact four loaded service routes,
protected ADMIN/weekly commands and the disabled ADMIN Codex guards. It pauses
only the four existing PREMATCH timers and allows active services to finish.
Route changes are atomic, prior timer states are restored, and failures restore
previous routes. It does not start a manual operational cycle or send a test.

Compatible rollback:

    sudo python3 ~/goalvision-operations/settlement-replies.py --apply --rollback

Rollback disables only GOALVISION_LAB_SETTLEMENT_REPLIES. COMBO bot routing,
credentials, statistics periods, claims, both 1.30 floors, today-only, early loss,
remaining-leg tracking, de-vig research and calibration readiness remain enabled.
It retains the compatible application reader and all historical evidence.

## Verification and boundaries

744 offline tests passed; one inherited inapplicable installer case skipped.
The 16-file matrix covers binding to an older original message, receipt
validation, text/photos, same-chat ReplyParameters, deleted/mismatched parents,
timeout/persistence failures, claim terminality through rollback, SINGLE and
both COMBO routes, all result states, early loss with remaining legs, legacy
direct settlement, routing/cohorts, selection floors, today-only and installer
drift/recovery/rollback. All network access in tests is denied.

Existing COMBO configuration and the installed python-telegram-bot ReplyParameters
API were also validated locally without Telegram requests.
Full runtime source parity PASS; protected model state/champion unchanged.
All four loaded service routes still use the deployed 9a3b198 release. Timers
remain active/enabled. A naturally running settlement was observed, not started
or interrupted by this work. ADMIN Codex systemd guard PASS.

Evidence: docs/evidence/settlement_replies_20261003/.
No deployment, production DB write, manual cycle, provider request, Telegram
request/test send, champion promotion or git push was performed.
Official unchanged; LIVE and ADMIN Codex remain disabled.
SINGLE >=1.30 and each COMBO leg >=1.30; SINGLE 1.50 remains separate future work.
No new channel, weekly route or statistics reset is included.

Telegram primary references:
https://core.telegram.org/bots/api#replyparameters
https://docs.python-telegram-bot.org/en/stable/telegram.replyparameters.html

## Prepared package

Source commit: 2436d39fcab122c70febafe048b1af6a98ce4215

Package: /home/arvis/goalvision-operations/settlement-replies-2436d39-20261003

Pinned entry point: /home/arvis/goalvision-operations/settlement-replies.py

Five package checksum entries verified. Read-only preflight PASS, current mode
BASE. Existing COMBO configuration and ReplyParameters dependency locally valid.
Operator apply and the first natural threaded result remain pending. No deployment
or test send performed. Evidence: operator_package.json in the evidence folder.

## Operator deployment and first natural reply

The operator deployed the pinned 2436d39 package on 2026-10-03; route files were
updated at 11:57:06 UTC / 14:57:06 Europe/Riga. Independent readback at 12:08:59 UTC
verified the entire installed 818-file manifest, release/rollback environments,
ENABLED mode and all four service routes. Existing COMBO configuration validates
locally. All four timers are active/enabled. ADMIN Codex is inactive with MainPID 0
and its timer disabled. Protected commands/routes and champion/model counts match
the reviewed package and previous readback.

The natural settlement cycle at 15:05 Riga succeeded and produced the first
confirmed SINGLE result reply: LOST, Telegram result message 616, original
prediction message 582, sent 15:05:54 Riga. The receipt records
reply_status=CONFIRMED. Independently verified original receipt, result receipt,
claim and economic outcome fingerprints; the frozen parent message and original
chat match exactly. This is natural production evidence, with no test send.

No COMBO result with reply metadata appeared in the latest 200 receipts at this
readback. COMBO replies are enabled and offline tested; the first natural COMBO
reply remains pending. No manual cycle, provider/Telegram request, production DB
write, deployment or service restart was performed by this readback.

Evidence: docs/evidence/settlement_replies_20261003/deployed_readback.json.
