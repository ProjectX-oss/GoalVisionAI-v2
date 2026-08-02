"""SQLite-consistent LAB database backup, verification and isolated restore rehearsal."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint


class BackupConflict(RuntimeError):
    """Backup path, immutable metadata or verification failed."""


class LabBackupService:
    def __init__(self, connection: sqlite3.Connection, source_path: Path, allowed_root: Path) -> None:
        self.connection=connection; self.source_path=Path(source_path).resolve(); self.allowed_root=Path(allowed_root).resolve()

    def create(self, *, created_at_utc: datetime) -> dict:
        created=_utc(created_at_utc); self.allowed_root.mkdir(parents=True,exist_ok=True)
        destination=(self.allowed_root / f"goalvision-lab-{created:%Y%m%dT%H%M%S%fZ}.sqlite3").resolve(); self._inside(destination)
        if destination.exists(): raise BackupConflict("Backup destination already exists.")
        source_hash=_sha(self.source_path); target=sqlite3.connect(destination)
        try: self.connection.backup(target)
        finally: target.close()
        backup_hash=_sha(destination); schema=self.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        material={"schema_version":"goalvision-lab-database-backup-manifest-v1","source_path":self.source_path.name,"backup_path":str(destination),"source_sha256":source_hash,"backup_sha256":backup_hash,"database_schema_version":schema,"created_at_utc":created.isoformat(),"secrets_in_manifest":False};fp=fingerprint(material)
        value={**material,"backup_id":"lab-database-backup-"+fp,"backup_fingerprint":fp,"outcome":"BACKUP_CREATED"}
        with self.connection:self.connection.execute("INSERT INTO lab_database_backups VALUES (?,?,?,?,?,?,?,?)",(value["backup_id"],source_hash,backup_hash,schema,str(destination),fp,canonical_json(value),value["created_at_utc"]))
        return value

    def inspect(self, backup_id: str) -> dict:
        row=self.connection.execute("SELECT manifest_json FROM lab_database_backups WHERE backup_id=?",(backup_id,)).fetchone()
        if not row:raise BackupConflict("Backup record not found.")
        return json.loads(row[0])

    def verify(self, backup_id: str, *, verified_at_utc: datetime) -> dict:
        manifest=self.inspect(backup_id); path=Path(manifest["backup_path"]).resolve(); self._inside(path); blockers=[]
        if not path.is_file() or _sha(path)!=manifest["backup_sha256"]:blockers.append("BACKUP_HASH_MISMATCH")
        schema=None; foreign_keys=[]
        if not blockers:
            try:
                connection=sqlite3.connect(f"file:{path.as_posix()}?mode=ro",uri=True); schema=connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0];foreign_keys=connection.execute("PRAGMA foreign_key_check").fetchall();connection.close()
            except sqlite3.DatabaseError:blockers.append("BACKUP_OPEN_FAILED")
        if schema!=manifest["database_schema_version"]:blockers.append("BACKUP_SCHEMA_MISMATCH")
        if foreign_keys:blockers.append("BACKUP_FOREIGN_KEY_VIOLATION")
        outcome="BACKUP_VERIFIED" if not blockers else "BACKUP_FAILED";material={"backup_id":backup_id,"outcome":outcome,"blockers":blockers,"backup_sha256":manifest["backup_sha256"],"schema_version":schema,"foreign_key_violations":len(foreign_keys),"verified_at_utc":_utc(verified_at_utc).isoformat()};fp=fingerprint(material);value={**material,"verification_id":"lab-backup-verification-"+fp,"verification_fingerprint":fp}
        with self.connection:self.connection.execute("INSERT OR IGNORE INTO lab_database_backup_verifications VALUES (?,?,?,?,?,?)",(value["verification_id"],backup_id,outcome,fp,canonical_json(value),value["verified_at_utc"]))
        return value

    def restore_rehearsal(self, backup_id: str, destination: Path) -> dict:
        manifest=self.inspect(backup_id); source=Path(manifest["backup_path"]).resolve(); self._inside(source); target=Path(destination).resolve(); self._inside(target)
        if target.exists():raise BackupConflict("Restore rehearsal destination already exists.")
        source_connection=sqlite3.connect(f"file:{source.as_posix()}?mode=ro",uri=True); target_connection=sqlite3.connect(target)
        try:source_connection.backup(target_connection)
        finally:source_connection.close();target_connection.close()
        restored=sqlite3.connect(f"file:{target.as_posix()}?mode=ro",uri=True)
        try:
            schema=restored.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]; fk=restored.execute("PRAGMA foreign_key_check").fetchall()
            counts={table:restored.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("forward_test_observations","governance_policy_reviews","lab_launch_authorizations")}
        finally:restored.close()
        outcome="RESTORE_REHEARSAL_PASSED" if schema==manifest["database_schema_version"] and not fk else "RESTORE_REHEARSAL_FAILED"
        return {"outcome":outcome,"backup_id":backup_id,"isolated_destination":str(target),"restored_sha256":_sha(target),"schema_version":schema,"foreign_key_violations":len(fk),"important_record_counts":counts,"live_database_overwritten":False}

    def _inside(self,path:Path)->None:
        if path!=self.allowed_root and self.allowed_root not in path.parents:raise BackupConflict("Path is outside the allowed backup root.")


def _sha(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()


def _utc(value:datetime)->datetime:
    if value.tzinfo is None:raise ValueError("UTC offset is required.")
    return value.astimezone(timezone.utc)
