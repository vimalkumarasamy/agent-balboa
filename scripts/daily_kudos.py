"""
Give kudos to recent activities from your top friends via shared clubs.
Safe to run daily — caps at 50 kudos/day and skips already-kudosed activities.

Usage:
    python scripts/daily_kudos.py            # give kudos
    python scripts/daily_kudos.py --dry-run  # preview without giving
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from tools.strava.social import run_daily_kudos

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("Dry run — previewing kudos (none will be given)...\n")
    else:
        print("Giving kudos to friends...\n")

    result = run_daily_kudos(dry_run=dry_run)

    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)

    if dry_run:
        print(f"Would give kudos to {result['would_kudos']} activities:")
        for a in result.get("activities", []):
            print(f"  {a['athlete_name']} — {a['activity_name']} ({a['club']})")
    else:
        print(f"Gave {result['kudos_given']} kudos:")
        for name in result.get("to", []):
            print(f"  {name}")
        print(f"\nDaily total: {result['daily_total']}/50")
