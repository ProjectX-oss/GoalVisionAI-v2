"""Bounded read-only ADMIN incident export; never scans, acknowledges or sends."""
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

ROW_KEYS = ("id","service","rule","object_id","state","severity","count","first_seen","last_seen",
            "last_sent","invocation","episode","generation","notified_state")
EVENT_KEYS = ("service","rule","object_id","source","observed","healthy","invocation","cycle","facts")
SECRET_KEYS = ("token","secret","password","credential","api_key","authorization","headers",
               "body","receipt","chat_id","message")

def safe(value: object, depth: int = 0) -> object:
    if depth > 6:
        return "OMITTED"
    if value is None or type(value) in (bool,int,float):
        return value
    if isinstance(value,str):
        return value if re.fullmatch(r"[a-zA-Z0-9_.-]{0,160}",value) and "token" not in value.lower() else "REDACTED"
    if isinstance(value,dict):
        return {key:safe(item,depth+1) for key,item in list(value.items())[:80]
                if isinstance(key,str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}",key)
                and not any(word in key.lower() for word in SECRET_KEYS)}
    if isinstance(value,list):
        return [safe(item,depth+1) for item in value[:100]]
    return "OMITTED"

def read_object(path: Path) -> dict:
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError("SOURCE_SYMLINK")
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,"rb") as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>4*1024*1024:
            raise ValueError("SOURCE_SIZE_OR_TYPE")
        value=json.load(source)
    if not isinstance(value,dict):
        raise ValueError("SOURCE_TYPE")
    return value

def collect(root: Path, *, now: float, hours: int = 24) -> dict:
    """Use query-only rollback-journal reads; retain source bytes and permissions."""
    root=root.absolute()
    database=root/"admin.sqlite"
    if any(p.is_symlink() for p in (database,*database.parents)):
        raise ValueError("SOURCE_SYMLINK")
    with database.open("rb") as source:
        header=source.read(100)
    if len(header)!=100 or header[:16]!=b"SQLite format 3\x00":
        raise ValueError("SOURCE_HEADER")
    if header[18]==2 and not (os.statvfs(database).f_flag & os.ST_RDONLY):
        raise ValueError("WAL_REQUIRES_READONLY_MOUNT")
    if not 1<=hours<=72:
        raise ValueError("INVALID_WINDOW")
    since=now-hours*3600
    output={"mode":"READ_ONLY","as_of_epoch":now,"since_epoch":since,"hours":hours,
            "monitor_scan":False,"provider_calls":0,"telegram_sends":0,"source_writes":0}
    with sqlite3.connect(database.as_uri()+"?mode=ro",uri=True,timeout=.2) as db:
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        deadline=time.monotonic()+3
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        columns=",".join(ROW_KEYS)
        rows=db.execute(f"""SELECT {columns},
            CASE WHEN length(CAST(evidence AS BLOB))<=131072 THEN evidence ELSE NULL END AS evidence
            FROM incidents WHERE last_seen>=? OR last_sent>=? OR state IN ('OPEN','REPEATED','ESCALATED')
            ORDER BY last_sent DESC,last_seen DESC,id LIMIT 201""",(since,since)).fetchall()
        output["truncated"]=len(rows)>200
        output["incidents"]=[]
        for row in rows[:200]:
            value=safe({k:row[k] for k in ROW_KEYS})
            try:
                document=json.loads(row["evidence"]) if row["evidence"] is not None else {}
                value["evidence"]=safe({k:document[k] for k in EVENT_KEYS if k in document})
            except (ValueError,TypeError):
                value["evidence"]={"status":"EVIDENCE_UNAVAILABLE"}
            notifications=db.execute("""SELECT state,count(*) AS rows,sum(acknowledged) AS acknowledged
                FROM outbox WHERE incident=? AND created>=? GROUP BY state""",(row["id"],since)).fetchall()
            value["outbox_created_in_window"]=[safe(dict(v)) for v in notifications]
            output["incidents"].append(value)
        output["delivery_attempts_in_window"]=[safe(dict(v)) for v in db.execute(
            "SELECT result,count(*) AS count FROM attempts INDEXED BY attempt_time WHERE started>=? GROUP BY result",(since,))]
    for filename,keys in (
        ("incident-report.json",("source_access","admin_delivery","autorepair")),
        ("last-scan.json",("elapsed_seconds","stdout_bytes","events","telegram_sends","football_api_calls","no_send"))):
        try:
            document=read_object(root/filename)
            output[filename.replace(".json","").replace("-","_")]=safe({k:document[k] for k in keys if k in document})
        except (OSError,ValueError):
            output[filename.replace(".json","").replace("-","_")]={"status":"REPORT_UNAVAILABLE"}
    return output

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours",type=int,default=24)
    args=parser.parse_args()
    try:
        report=collect(Path("/var/lib/goalvision-admin-alerts"),now=time.time(),hours=args.hours)
        print(json.dumps(report,indent=2,sort_keys=True,allow_nan=False))
        return 0
    except (OSError,ValueError,sqlite3.Error) as exc:
        print(json.dumps({"mode":"READ_ONLY","status":"DIAGNOSTIC_UNAVAILABLE","error_type":type(exc).__name__}))
        return 1

if __name__=="__main__":
    raise SystemExit(main())
