import os
import csv
import re
import calendar
import requests
from datetime import date
from typing import Optional


def _fetch_sheet_csv(url: str) -> str:
    sheet_id = url.split("/d/")[1].split("/")[0]
    gid = url.split("gid=")[-1].split("#")[0] if "gid=" in url else "0"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    resp = requests.get(csv_url, timeout=10)
    resp.raise_for_status()
    return resp.text


def _parse_week_date(raw: str, year: int) -> Optional[date]:
    abbr_to_month = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
    m = re.match(r"([A-Za-z]+)-?(\d+)", raw.strip())
    if not m:
        return None
    month_num = abbr_to_month.get(m.group(1).lower()[:3])
    if not month_num:
        return None
    try:
        return date(year, month_num, int(m.group(2)))
    except ValueError:
        return None


def get_coach_plan() -> str:
    """Return this week's coach plan with clearly labeled schedule and exercise lists.
    Exercise names are copied verbatim from the sheet — report them exactly as shown."""
    url = os.getenv("COACH_SHEET_URL", "")
    if not url:
        return "No coach sheet URL set. Add COACH_SHEET_URL to your .env file."

    try:
        rows = list(csv.reader(_fetch_sheet_csv(url).splitlines()))
        rows = [r for r in rows if any(c.strip() for c in r)]
    except Exception as e:
        return f"Could not fetch coach sheet: {e}"

    if not rows:
        return "Coach sheet is empty."

    today = date.today()

    # Row 0 is the header — skip it. All subsequent rows contain exercises in
    # cols 0-2 and optionally a week date in col 4 plus Mon-Sun workouts in cols 5-11.
    day_names = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
    header_idx = next(
        (i for i, r in enumerate(rows) if r and r[0].strip().lower() in day_names), 0
    )

    monday_ex, friday_ex, upper_ex, schedule_rows = [], [], [], []

    for row in rows[header_idx + 1:]:
        if row[0].strip():
            monday_ex.append(row[0].strip())
        if len(row) > 1 and row[1].strip():
            friday_ex.append(row[1].strip())
        if len(row) > 2 and row[2].strip():
            upper_ex.append(row[2].strip())
        week_cell = row[4].strip() if len(row) > 4 else ""
        if _parse_week_date(week_cell, today.year):
            schedule_rows.append(row)

    # Find the closest week
    best_row, best_diff = None, None
    for row in schedule_rows:
        diff = abs((_parse_week_date(row[4], today.year) - today).days)
        if best_diff is None or diff < best_diff:
            best_diff, best_row = diff, row

    if not best_row:
        return f"Today is {today}. Could not find current week in the coach's plan."

    DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    schedule = []
    for i, day in enumerate(DAYS):
        col = 5 + i
        workout = best_row[col].strip() if len(best_row) > col else ""
        schedule.append(f"  {day}: {workout or 'Rest'}")

    lines = [
        f"Today is {today} ({today.strftime('%A')}).",
        f"\nWEEK OF {best_row[4]}:",
        *schedule,
    ]

    if monday_ex:
        lines.append("\nMONDAY STRENGTH EXERCISES (exact — do not add sets or reps):")
        lines.extend(f"  - {e}" for e in monday_ex)

    if friday_ex:
        lines.append("\nFRIDAY STRENGTH EXERCISES (exact — do not add sets or reps):")
        lines.extend(f"  - {e}" for e in friday_ex)

    if upper_ex:
        lines.append("\nUPPER BODY EXERCISES (whenever possible):")
        lines.extend(f"  - {e}" for e in upper_ex)

    return "\n".join(lines)
