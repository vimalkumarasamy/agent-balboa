"""
One-time Strava OAuth setup. Run this once to get your refresh token.
The token is saved automatically to your .env file.

Usage:
    python scripts/strava_auth.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.strava.auth import run_oauth_flow

if __name__ == "__main__":
    print("Starting Strava OAuth flow...")
    run_oauth_flow()
    print("Done. Your refresh token has been saved to .env.")
