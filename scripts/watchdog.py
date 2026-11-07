"""Run another script and print where it is stuck if it takes too long.

Usage:  python scripts/watchdog.py scripts/load_warehouse.py --input digital --simulate-review
Every 20 seconds (WATCHDOG_SECONDS to change) while the script is still running, the Python
stack of all threads is printed to the screen: file, line and function where it waits.
"""
import faulthandler
import os
import runpy
import sys

if len(sys.argv) < 2:
    raise SystemExit("usage: python scripts/watchdog.py <script.py> [arguments]")
seconds = int(os.environ.get("WATCHDOG_SECONDS", "20"))
faulthandler.dump_traceback_later(seconds, repeat=True, file=sys.stdout)
target = sys.argv[1]
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(os.path.abspath(target)))
runpy.run_path(target, run_name="__main__")
faulthandler.cancel_dump_traceback_later()
