# Balboa — Personal Fitness Agent

A personal fitness assistant running on a local LLM via [Lemonade](https://github.com/lemonade-sdk/lemonade).
Combines your Strava data, coach's plan, weather, and goals to suggest your next workout.

---

## Prerequisites

### Lemonade (local LLM server)

Balboa runs on your local machine using Lemonade to serve the LLM. Install it first:

```bash
# macOS
brew install lemonade

# Or download from: https://github.com/lemonade-sdk/lemonade/releases
```

Then pull the recommended model and start the server:

```bash
lemonade pull Qwen3-8B-GGUF
lemonade load Qwen3-8B-GGUF
```

Verify it's running:
```bash
curl http://localhost:13305/v1/models
```

> **Don't want to run locally?** Set `LLM_PROVIDER=claude` in `.env` and use your Anthropic API key instead. Lemonade is not needed in that case.

---

## Setup

### 1. Clone and install dependencies
```bash
git clone https://github.com/yourname/balboa.git
cd balboa
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure `.env`
```bash
cp .env.example .env
```
Then fill in your values:
```env
# --- LLM ---
LLM_PROVIDER=lemonade          # or "claude" to use Anthropic API
ANTHROPIC_API_KEY=             # only needed if LLM_PROVIDER=claude

# --- Strava ---
STRAVA_CLIENT_ID=              # from strava.com/settings/api
STRAVA_CLIENT_SECRET=          # from strava.com/settings/api
STRAVA_REFRESH_TOKEN=          # auto-filled after running scripts/strava_auth.py

# --- Location ---
HOME_CITY=Seattle, WA          # your city, used for weather forecast

# --- Coach plan (optional) ---
COACH_SHEET_URL=               # Google Sheets URL shared as "anyone with link can view"
```

### 3. Connect Strava (one-time)

Register a free API app at [strava.com/settings/api](https://www.strava.com/settings/api):
- **Website**: `http://localhost`
- **Authorization Callback Domain**: `localhost`

Then run the auth flow:
```bash
python scripts/strava_auth.py
```
A browser opens → click Authorize → your refresh token is saved to `.env` automatically.

### 4. Sync your Strava activities (one-time)
```bash
python scripts/sync.py --full
```
This fetches your full activity history and stores it locally in `data/activities/` by year.
Subsequent syncs are incremental and fast.

### 5. Set up shell alias
```bash
echo 'alias balboa="/path/to/.venv/bin/python /path/to/main.py"' >> ~/.zshrc
source ~/.zshrc
```

---

## Running

```bash
balboa
# or
.venv/bin/python main.py
```

Balboa checks for new Strava activities automatically on startup (every 24h).
Type `sync` anytime in the chat to force a sync.

---

## What you can ask

```
what should my next workout be?      → Strava + coach plan + weather + goals
what does my coach have this week?   → full weekly breakdown with exercise lists
what are my best times?              → all-time PRs from your full activity history
how have my runs been lately?        → recent activity summary + weekly mileage
find running races near me in June   → live web search for local events
what's the weather this week?        → 3-day forecast for your city
save my goals: sub 3:30 marathon     → saves to data/goals.md
give kudos to my friends             → kudos to top friends via shared clubs
```

---

## Standalone scripts

```bash
# Sync Strava activities
python scripts/sync.py                # incremental (new activities only)
python scripts/sync.py --full         # full all-time sync

# Build top friends list (who kudoses you most)
python scripts/build_friends.py       # incremental update
python scripts/build_friends.py --full  # full rebuild

# Give daily kudos
python scripts/daily_kudos.py         # give kudos (max 50/day)
python scripts/daily_kudos.py --dry-run  # preview without giving
```

---

## Coach Plan — Expected Google Sheet Structure

Share the sheet as **"Anyone with the link can view"** and set `COACH_SHEET_URL` in `.env`.

```
| Monday exercises | Friday exercises | Upper Body (optional) | | Week date | Mon      | Tue  | Wed          | Thu  | Fri      | Sat  | Sun  |
|------------------|------------------|-----------------------|-|-----------|----------|------|--------------|------|----------|------|------|
| Activation       | Activation       | Incline Press         | | May-18    | Strength | Easy | Hill sprints | Easy | Strength | Easy | Easy |
| Plank            | Pallof Holds     | Shoulder Press        | | May-25    | Strength | Easy | Hill sprints | Easy | Strength | Easy | Easy |
```

- **Column 0** (`Monday`): Exercises to do every Monday strength session
- **Column 1** (`Friday`): Exercises to do every Friday strength session
- **Column 2** (`Upper Body`): Optional upper body exercises (whenever possible)
- **Column 4**: Week start date — formats like `May-18`, `May18`, `Jun1`, `Jun-8`
- **Columns 5–11**: Workout type — `Strength` expands to the exercise list, `Easy` = easy run, anything else shown as-is

---

## Switching models

Edit `LLM_PROVIDER` in `.env`:

| Value | Model | Cost | Requires |
|---|---|---|---|
| `lemonade` | Qwen3-8B (local) | Free, offline | Lemonade installed |
| `claude` | Claude Opus 4.7 | API usage | Anthropic API key |

---

## Running tests

```bash
.venv/bin/pytest tests/ -v
```

---

## Inputs summary

| Input | Where | Required |
|---|---|---|
| Strava credentials | `.env` | Yes |
| Home city | `.env` → `HOME_CITY` | Yes |
| Coach's Google Sheet | `.env` → `COACH_SHEET_URL` | Optional |
| Fitness goals | say `save my goals:` in chat | Optional |
| Anthropic API key | `.env` → `ANTHROPIC_API_KEY` | Only if using Claude |
