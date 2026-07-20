# GoalVision AI Architecture

GoalVision AI keeps prediction generation, calibration, eligibility, public
presentation, delivery, bankroll management, settlement, and result reporting
as separate boundaries.

## Official prediction publication

The future scheduler-facing callable is
`prepare_and_publish_official_prediction(...)`. It assembles one supplied
candidate, persists the Official Quality Gate decision, creates the canonical
public message, obtains an atomic publication claim, sends through the injected
Telegram service, finalizes the delivery event, and then persists the
orchestration outcome.

`app/official_prediction_publication` owns public message assembly and the
claim/send/finalize adapter only. Prediction generation, calibration, market
selection, risk, exposure, bankroll, settlement, result publication, Telegram
credentials, scheduling, and non-Official products stay outside this boundary.
Unknown delivery outcomes are indeterminate and cannot be automatically resent.
Application startup constructs dependencies but never sends a prediction.
