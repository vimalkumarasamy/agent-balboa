import os
import re
import csv
import requests
import calendar
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _fetch_sheet(url: str) -> list[list[str]]:
    sheet_id = url.split("/d/")[1].split("/")[0]
    gid = url.split("gid=")[-1].split("#")[0] if "gid=" in url else "0"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    resp = requests.get(csv_url, timeout=10)
    resp.raise_for_status()
    return list(csv.reader(resp.text.splitlines()))


def _extract_exercise_list(rows: list, col: int, start_row: int) -> list[str]:
    """Extract all non-empty exercises from a given column starting after the header."""
    exercises = []
    for row in rows[start_row:]:
        if col < len(row) and row[col].strip():
            exercises.append(row[col].strip())
    return exercises


def get_coach_plan(weeks_ahead: int = 0) -> str:
    """Read the coach's workout plan from Google Sheets for the current or upcoming week.

    The sheet has two structures:
    1. Exercise lists: columns labeled 'Monday' and 'Friday' contain the full list of
       strength/activation exercises to complete on those days each week.
    2. Weekly schedule: columns Mon-Sun for each week date show the workout type
       (Strength = do the exercise list, Easy = easy run, or specific workout like hill sprints).

    Set weeks_ahead=1 to see next week's plan."""
    url = os.getenv("COACH_SHEET_URL", "")
    if not url:
        return "No coach sheet URL set. Add COACH_SHEET_URL to your .env file."

    rows = _fetch_sheet(url)

    # Find the header row containing day names
    header_row_idx = next(
        (i for i, r in enumerate(rows) if "Monday" in r and "Sunday" in r), None
    )
    if header_row_idx is None:
        return "Could not parse the sheet structure."

    headers = rows[header_row_idx]

    # Extract the standing exercise lists from the left side of the sheet
    # Col 0 = Monday exercises, Col 1 = Friday exercises, Col 2 = Upper body
    monday_exercises = _extract_exercise_list(rows, 0, header_row_idx + 1)
    friday_exercises = _extract_exercise_list(rows, 1, header_row_idx + 1)
    upper_body = _extract_exercise_list(rows, 2, header_row_idx + 1)

    # Find the weekly schedule section
    week_col = next((i for i, h in enumerate(headers) if h.strip() in ("Column 1", "Week")), 4)
    target_date = date.today() + timedelta(weeks=weeks_ahead)

    abbr_to_month = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}

    def parse_week_date(raw: str):
        m = re.match(r"([A-Za-z]+)-?(\d+)", raw.strip())
        if not m:
            return None
        month_num = abbr_to_month.get(m.group(1).lower()[:3])
        if not month_num:
            return None
        return date(target_date.year, month_num, int(m.group(2)))

    best_row = None
    best_diff = None
    for row in rows[header_row_idx + 1:]:
        if week_col >= len(row) or not row[week_col].strip():
            continue
        parsed = parse_week_date(row[week_col])
        if parsed is None:
            continue
        diff = abs((parsed - target_date).days)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_row = row

    if best_row is None:
        return "Could not find a matching week in the coach's plan."

    week_label = best_row[week_col]

    # Build daily schedule — expand "Strength" into the actual exercise list
    schedule_lines = []
    for day in DAYS:
        col = next((i for i, h in enumerate(headers) if h.strip() == day and i > week_col), None)
        workout = best_row[col].strip() if col and col < len(best_row) else ""

        if day == "Monday" and (not workout or workout.lower() == "strength"):
            detail = "Strength session:\n  - " + "\n  - ".join(monday_exercises) if monday_exercises else "Strength"
        elif day == "Friday" and (not workout or workout.lower() == "strength"):
            detail = "Strength session:\n  - " + "\n  - ".join(friday_exercises) if friday_exercises else "Strength"
        elif workout:
            detail = workout
        else:
            detail = "Easy run"

        schedule_lines.append(f"{day}: {detail}")

    # Append upper body note if available
    upper_body_note = ""
    if upper_body:
        upper_body_note = "\n\nUpper Body Session (whenever possible):\n  - " + "\n  - ".join(upper_body)

    return (
        f"Coach's plan for week of {week_label}:\n\n"
        + "\n\n".join(schedule_lines)
        + upper_body_note
    )
