"""
One-time Google Calendar OAuth flow.

Usage:
    python scripts/calendar_auth.py

A browser window opens → sign in → authorize → done.
Token is saved to data/calendar_token.json automatically.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from tools.calendar.auth import run_oauth_flow

if __name__ == "__main__":
    run_oauth_flow()
