# LAB Database Backup and Recovery

`create-backup` uses SQLite's online backup API, writes a timestamped file below the configured backup root, refuses overwrite, records source/backup SHA-256 values and schema, and stores a secret-free deterministic manifest. `verify-backup` opens the backup read-only, checks its hash, schema, and foreign keys.

`restore-rehearsal` always targets a new isolated path under the backup root. It verifies schema, foreign keys, and important record counts and never restores over the operational database. Backups and restore files are operational artifacts and must not be committed.
