"""Dedicated append-only research store; refuses every other database schema."""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3
from .contracts import seal,verify,canonical

class ResearchStore:
    def __init__(self,path: Path,*,readonly: bool=False,protected_paths: tuple[Path,...]=()) -> None:
        path=path.absolute()
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError("RESEARCH_SYMLINK")
        if any(path.resolve()==p.resolve() or (path.exists() and p.exists() and path.samefile(p))
               for p in protected_paths):
            raise ValueError("PRODUCTION_DATABASE_FORBIDDEN")
        if not readonly: path.parent.mkdir(parents=True,exist_ok=True)
        self.connection=sqlite3.connect(path.as_uri()+("?mode=ro" if readonly else "?mode=rwc"),uri=True,timeout=.1)
        try:
            if readonly: self.connection.execute("PRAGMA query_only=ON")
            names={r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if names-{"dc_research_records"}: raise ValueError("DEDICATED_RESEARCH_DATABASE_REQUIRED")
            if readonly and names!={"dc_research_records"}: raise ValueError("RESEARCH_SCHEMA_MISSING")
            if not readonly:
                with self.connection:
                    self.connection.execute("CREATE TABLE IF NOT EXISTS dc_research_records(kind TEXT NOT NULL,identity TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(kind,identity))")
                    for action in ("UPDATE","DELETE"):
                        self.connection.execute(f"CREATE TRIGGER IF NOT EXISTS dc_no_{action.lower()} BEFORE {action} ON dc_research_records BEGIN SELECT RAISE(ABORT,'Immutable research'); END")
        except BaseException:
            self.connection.close(); raise

    def close(self) -> None: self.connection.close()

    def get(self,kind: str,identity: str) -> dict | None:
        row=self.connection.execute("SELECT document FROM dc_research_records WHERE kind=? AND identity=?",(kind,identity)).fetchone()
        if row is None: return None
        value=json.loads(row[0]); verify(value); return value

    def append(self,kind: str,identity: str,value: dict) -> bool:
        verify(value)
        with self.connection:
            cursor=self.connection.execute("INSERT OR IGNORE INTO dc_research_records VALUES(?,?,?)",
                                           (kind,identity,canonical(value)))
            if not cursor.rowcount and self.get(kind,identity)!=value: raise ValueError("IMMUTABLE_RESEARCH_CONFLICT")
            return bool(cursor.rowcount)

    def all(self,kind: str) -> list[dict]:
        rows=self.connection.execute("SELECT document FROM dc_research_records WHERE kind=? ORDER BY identity LIMIT 50001",(kind,)).fetchall()
        if len(rows)>50000: raise ValueError("RESEARCH_CAPACITY")
        values=[json.loads(row[0]) for row in rows]
        for value in values: verify(value)
        return values
