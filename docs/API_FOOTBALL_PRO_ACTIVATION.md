# API-Football Pro Activation

Subscription activation remains a manual operator action outside GoalVision AI. After activation, verify `.env` locally and run the existing bounded command: `python -m app.current_odds_forward_test pro-readiness --network-verify --output json`. This is the only documented preflight network boundary and is limited to the account-status request.

The persisted launch preflight must show authentication, a non-Free plan, current-season access, and at least 12 calls remaining after the configured reserve. Reports contain status and quota facts only; credentials are never persisted or printed. Without the explicit network flag the new preflight records zero calls and returns `PRO_PREFLIGHT_NETWORK_NOT_REQUESTED`.
