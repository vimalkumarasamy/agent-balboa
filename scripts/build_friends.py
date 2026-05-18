"""
Build or update your top friends list based on who kudoses you most.

Usage:
    python scripts/build_friends.py           # incremental update (fast)
    python scripts/build_friends.py --full    # full rebuild from scratch
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from tools.strava.social import build_top_friends, update_top_friends

if __name__ == "__main__":
    full = "--full" in sys.argv

    if full:
        print("Building top friends list (full scan)...")
        result = build_top_friends(progress_callback=print)
    else:
        print("Updating top friends list (incremental)...")
        result = update_top_friends(progress_callback=print)

    print(f"\nDone.")
    print(f"  Mode: {result.get('mode', 'full')}")
    print(f"  Total kudosers found: {result.get('total_unique_kudosers', 'N/A')}")
    print(f"  Top friends saved: {result.get('top_friends_saved', 'N/A')}")
    if result.get("top_5_preview"):
        print(f"  Top 5:")
        for f in result["top_5_preview"]:
            print(f"    {f}")
