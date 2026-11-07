"""Show what the database is doing right now (running queries, waits, locks).

Usage:  python scripts/db_activity.py
Helps when a script seems stuck. Prints only session information, no invoice data.
"""
from sqlalchemy import text

from invoice_pipeline.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    print("Sessions on this database:")
    rows = conn.execute(text(
        "SELECT pid, state, wait_event_type, wait_event, "
        "now() - xact_start AS in_transaction_for, left(query, 70) AS query "
        "FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid() "
        "ORDER BY xact_start NULLS LAST"
    )).all()
    if not rows:
        print("  (no other sessions)")
    for r in rows:
        print("  ", *r)
    blocked = conn.execute(text(
        "SELECT count(*) FROM pg_locks WHERE NOT granted"
    )).scalar_one()
    print(f"\nLock requests currently waiting: {blocked}")
    print("synchronous_commit =", conn.execute(text("SHOW synchronous_commit")).scalar_one())
