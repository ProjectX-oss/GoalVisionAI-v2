# Separate COMBO bot — 2026-10-03

Status: IMPLEMENTED / OFFLINE VERIFIED; NOT CONFIGURED / NOT DEPLOYED.
Authorized user: Arvis. Bot: @GoalVision_AI_Combo_Bot.
Channel deferred by the user. Initial destination: operator-verified private
conversation, explicitly confirmed during enrollment before any routing change.
Source base: ead9a0b; installed application base: e355b51.

## Behavior

New COMBO predictions and their settlement notifications use the dedicated bot
after operator activation. SINGLE and all pre-cutover COMBO result notifications
retain their existing Lab bot/destination. SINGLE >=1.30 and every COMBO leg
>=1.30 remain inclusive; no additional combined-odds floor. The later SINGLE
1.50 experiment remains pending and is not included here.

The original prediction's claim and confirmed receipt freeze product, bot numeric
identity/username, recipient, private-chat type and prospective statistics period.
Settlement follows that receipt, even with new-publication routing paused.
The atomic economic claim is unchanged and spans both destinations, preventing
route changes from authorizing duplicate bets. Unknown sends are never retried.

New COMBO result previews use only confirmed publications assigned to the same
frozen route/period. Prior-period result previews count only prior publications;
already frozen previews remain unchanged. All-time internal metrics retain the
full history, losses and pending outcomes. Hypothetical flat-unit accounting is
unchanged; no new cash bankroll or staking rule is introduced. Existing ticket
IDs/numbers remain stable. New-period public headings identify GoalVision AI COMBO.

COMBO bot/configuration failure cannot redirect COMBO into the SINGLE channel.
Bot batches have separate lifecycles; a failing COMBO lifecycle cannot suppress
the otherwise valid SINGLE batch. Configurations and incoming Telegram update
payloads never enter Git, operational logs, or publication documents.

No new polling daemon or scheduler is installed. Enrollment reads the explicitly
initiated private START challenge once; normal existing discovery and settlement
timers publish qualifying bets/results. There is no synthetic welcome/test send.
The separate channel and an independent weekly COMBO delivery are future work;
the existing protected weekly route remains unchanged.

## Operator steps (package must be built first)

1. Run without sudo:

   python3 ~/goalvision-operations/combo-bot.py --configure

   Enter the dedicated bot token at the hidden prompt. The helper verifies
   getMe against @GoalVision_AI_Combo_Bot and the token's bot numeric ID. It rejects
   reuse of configured Lab/Official tokens. Open its unique Telegram START link
   in your own account, press START, then Enter in the terminal. It accepts only
   a fresh exact challenge from one non-bot private sender whose ID equals the
   chat ID, then asks for JA to confirm that recipient.

   Credentials and recipient proof are written once, mode 0600, outside Git:
   /home/arvis/goalvision-private/combo-telegram.json (parent 0700).
   Existing configuration is not overwritten. The period begins at enrollment;
   only new confirmed publications after activation belong to it.

   Enrollment performs at most one getMe and one getUpdates request. No offset,
   filter changes, webhook changes or send methods are used. The token is never
   a command argument. A real interactive terminal is required. The helper
   rejects absent/ambiguous/expired START evidence and does not guess a recipient.

2. After successful COMBO_PRIVATE_RECIPIENT_CONFIGURED:

   sudo python3 ~/goalvision-operations/combo-bot.py --apply

   Apply requires valid enrollment before release creation or timer changes.
   The installer pins the actual e355b51 source, full application/plan hashes,
   helper hashes, exact four service routes and protected ADMIN/weekly commands.
   It pauses only those four timers, drains naturally, changes routes atomically
   and restores prior timer states. No service is forcibly started/killed.

3. Verify readback and the next qualifying natural cycle, with zero test sends.
   These remain pending until the operator has configured and applied.

Compatible rollback:

   sudo python3 ~/goalvision-operations/combo-bot.py --apply --rollback

Rollback sets GOALVISION_COMBO_BOT_ROUTING=0: pause all new COMBO publications.
It retains both settlement readers/routes, credentials, evidence and both 1.30
floors. SINGLE continues. Do not restore the pre-routing application tree while
new-bot bets/results are pending. Do not remove credentials needed for settlement.

## Verification

- 622 offline tests passed, one inherited inapplicable case skipped.
- Tests include private challenge matching, exact bot identity, wrong receipts,
  credential loss, cross-channel economic deduplication, unknown sends,
  persistence failure, old/new mixed settlement, independent period accounting,
  early financial loss and late remaining-leg details, installer source/hash
  drift, missing-config non-mutation, partial recovery and compatible rollback.
- Full application parity: 815 base files plus two added modules = 817 entries;
  five reviewed runtime overlay files. Frozen calibration plan unchanged.
- Existing 13:00 Riga natural cycle independently verified: three SINGLE and
  three COMBO receipts, all nine COMBO legs >=1.30, today-only, unique receipt IDs
  and immutable fingerprints. 13:08 observer report fingerprint verified.
- Protected model state unchanged: 3 cycles, 133 training runs, 59 artifacts,
  0 holdout results, 0 shadow runs, 1 generation; LIVE publications 0.
- No production DB mutation, deployment, bot enrollment, Telegram calls/sends,
  provider calls or manual operational cycles performed by the implementation.
- Evidence: docs/evidence/combo_bot_20261003/.

Official unchanged; LIVE and ADMIN Codex remain DISABLED. Champion, de-vig and
calibration schedule/learning evidence unchanged. No historical bookmaker odds.

Telegram primary references reviewed for the operator protocol:
https://core.telegram.org/bots/api#getme
https://core.telegram.org/bots/api#getupdates
https://core.telegram.org/bots/features#deep-linking

## Prepared package

Source commit: 9a3b19890e951224cef335c78054c0af203e7428

Package: /home/arvis/goalvision-operations/combo-bot-9a3b198-20261003

Pinned entry point: /home/arvis/goalvision-operations/combo-bot.py

8 package checksum entries verified. Read-only preflight PASS, current mode BASE.
Enrollment contract loaded under network denial; token/recipient remain unconfigured.
No deployment or Telegram calls performed.
