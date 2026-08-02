# First Genuine LAB Run

The entry point is `python -m app.lab_launch_readiness first-genuine-lab-run --database var/first_lab_forward_test.db --authorization-id <ID> --backup-root var/backups --max-candidates 50 --max-calls 40 --daily-reserve 20 --output human`.

The command verifies LAB policy, authorization, capacity and final readiness before provider work. Without separately verified Pro readiness it stops with `PROVIDER_PLAN_BLOCKED` and zero provider calls. The execution record and ordered stage events support exact replay and reject conflicts. The full dry-run pipeline ends after deterministic reasoning, governance snapshot, preview, and publication review. It never sends Telegram. Sending remains a separate command requiring the exact launch authorization and all six linked fingerprints.
