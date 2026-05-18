"""
Sync your Strava activities to local JSON files.

Usage:
    python scripts/sync.py           # incremental (default)
    python scripts/sync.py --full    # full all-time sync (run once on setup)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from tools.strava.sync import (
    run_initial_sync, run_incremental_sync,
    needs_initial_sync, get_db_stats
)

if __name__ == "__main__":
    full = "--full" in sys.argv

    if full or needs_initial_sync():
        print("Running full all-time sync...")
        count = run_initial_sync(progress_callback=print)
        print(f"\nDone — {count} activities synced.")
    else:
        stats = get_db_stats()
        last = stats.get("last_sync", "never")[:16].replace("T", " ")
        print(f"Running incremental sync (last sync: {last})...")
        count = run_incremental_sync()
        print(f"Done — {count} new activit{'y' if count == 1 else 'ies'} added.")
