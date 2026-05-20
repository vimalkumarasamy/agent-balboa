import os
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from tools.calendar.auth import get_credentials


def get_upcoming_events(days: int = 14) -> str:
    """Return calendar events for the next N days (default 14).
    Use this to understand the user's schedule before recommending workouts —
    travel, busy days, and rest blocks should all influence the plan."""
    try:
        creds = get_credentials()
    except FileNotFoundError as e:
        return str(e)

    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(timezone.utc)
    until = now + timedelta(days=days)

    result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=until.isoformat(),
        maxResults=50,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    if not events:
        return f"No calendar events in the next {days} days."

    lines = [f"Upcoming calendar events (next {days} days):"]
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date", ""))
        end = e["end"].get("dateTime", e["end"].get("date", ""))

        # Format datetime strings nicely
        if "T" in start:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            time_str = f"{start_dt.strftime('%a %b %d, %I:%M %p')} – {end_dt.strftime('%I:%M %p')}"
        else:
            # All-day event
            time_str = f"{start} (all day)"

        title = e.get("summary", "Untitled")
        location = e.get("location", "")
        loc_str = f" @ {location}" if location else ""
        lines.append(f"  • {time_str}: {title}{loc_str}")

    return "\n".join(lines)
