"""Create the star schema (and fill dim_date) in the PostgreSQL database from .env.

Usage:  python scripts/init_db.py [--reset]
--reset drops all warehouse tables first (all loaded data is lost).
"""
import sys

from sqlalchemy import inspect

from invoice_pipeline.db import get_engine
from invoice_pipeline.warehouse import create_schema, drop_schema

engine = get_engine()
if "--reset" in sys.argv:
    drop_schema(engine)
    print("Dropped existing warehouse tables.")
create_schema(engine)
insp = inspect(engine)
print("Tables:", ", ".join(sorted(insp.get_table_names())))
print("Views: ", ", ".join(sorted(insp.get_view_names())))
