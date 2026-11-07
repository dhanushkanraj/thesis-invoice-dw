"""Step-by-step database check. Prints every stage with its time, never hangs for long.

Usage:  python scripts/diagnose_db.py
Prints no password and no invoice data.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T0 = time.perf_counter()


def say(msg):
    print(f"[{time.perf_counter() - T0:5.1f}s] {msg}", flush=True)


say("1. files saved?")
db_src = (ROOT / "src" / "invoice_pipeline" / "db.py").read_text(encoding="utf-8")
wh_src = (ROOT / "src" / "invoice_pipeline" / "warehouse.py").read_text(encoding="utf-8")
ld_src = (ROOT / "scripts" / "load_warehouse.py").read_text(encoding="utf-8")
say(f"   db.py has time limits: {'lock_timeout' in db_src}")
say(f"   warehouse.py keeps existing views: {'refresh_views' in wh_src}")
say(f"   load_warehouse.py prints progress: {'invoices done' in ld_src}")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
say(f"2. settings: host={os.environ.get('DB_HOST')} port={os.environ.get('DB_PORT')} "
    f"db={os.environ.get('DB_NAME')} user={os.environ.get('DB_USER')}")

import psycopg

say("3. connecting (5 s limit) ...")
try:
    conn = psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"), port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"], user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
        connect_timeout=5, autocommit=True,
    )
except Exception as e:
    say(f"   CONNECT FAILED: {type(e).__name__}: {str(e)[:200]}")
    sys.exit(1)
say("   connected")

cur = conn.cursor()
cur.execute("SET lock_timeout = '5s'")
cur.execute("SELECT version()")
say("4. " + cur.fetchone()[0][:60])
cur.execute("SHOW synchronous_commit")
say(f"   synchronous_commit = {cur.fetchone()[0]}")

say("5. other sessions on this database:")
cur.execute(
    "SELECT pid, state, wait_event_type, wait_event, now() - xact_start, left(query, 60) "
    "FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()"
)
rows = cur.fetchall()
for r in rows or [("(none)",)]:
    say("   " + " | ".join(str(x) for x in r))
cur.execute("SELECT count(*) FROM pg_locks WHERE NOT granted")
say(f"   lock requests waiting: {cur.fetchone()[0]}")

say("6. row counts:")
for t in ("fact_invoice", "fact_invoice_line", "review_queue", "dim_date"):
    try:
        cur.execute(f"SELECT count(*) FROM {t}")
        say(f"   {t}: {cur.fetchone()[0]}")
    except Exception as e:
        say(f"   {t}: {type(e).__name__}: {str(e)[:100]}")

say("7. can I lock fact_invoice (5 s limit)?")
try:
    with conn.transaction():
        cur.execute("LOCK TABLE fact_invoice IN ACCESS EXCLUSIVE MODE")
    say("   yes, nothing is blocking it")
except Exception as e:
    say(f"   NO: {type(e).__name__}: {str(e)[:120]}")

say("8. speed of 20 small committed transactions:")
cur.execute("CREATE TEMP TABLE speedtest (x int)")
t = time.perf_counter()
for i in range(20):
    with conn.transaction():
        cur.execute("INSERT INTO speedtest VALUES (%s)", (i,))
say(f"   {(time.perf_counter() - t) / 20 * 1000:.1f} ms per transaction")
say("done")
