import os
import csv
import requests
from datetime import date


def _fetch_sheet_csv(url: str) -> str:
    sheet_id = url.split("/d/")[1].split("/")[0]
    gid = url.split("gid=")[-1].split("#")[0] if "gid=" in url else "0"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    resp = requests.get(csv_url, timeout=10)
    resp.raise_for_status()
    return resp.text


def _csv_to_table(csv_text: str) -> str:
    rows = list(csv.reader(csv_text.splitlines()))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        return "(empty sheet)"
    col_count = max(len(r) for r in rows)
    lines = []
    for row in rows:
        padded = row + [""] * (col_count - len(row))
        lines.append(" | ".join(cell.strip() for cell in padded))
    return "\n".join(lines)


def get_coach_plan() -> str:
    """Return the raw contents of the coach's Google Sheet. Today's date is
    included so the LLM can identify the current week and interpret the plan."""
    url = os.getenv("COACH_SHEET_URL", "")
    if not url:
        return "No coach sheet URL set. Add COACH_SHEET_URL to your .env file."
    try:
        table = _csv_to_table(_fetch_sheet_csv(url))
        return f"Today is {date.today().isoformat()}. Coach's workout sheet:\n\n{table}"
    except Exception as e:
        return f"Could not fetch coach sheet: {e}"
