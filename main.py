import os
import sys
import time
import threading
import itertools
import warnings
import logging
warnings.filterwarnings("ignore")
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent

from tools.strava.activities import get_recent_activities, get_athlete_profile, get_best_efforts, get_training_summary
from tools.strava.gear import get_shoes
from tools.strava.social import get_top_friends, get_my_clubs, run_daily_kudos, build_top_friends, update_top_friends
from tools.strava.sync import (
    needs_initial_sync, needs_incremental_sync,
    run_initial_sync, run_incremental_sync, get_db_stats
)
from tools.fitness.weather import get_weather_forecast
from tools.fitness.goals import read_goals, save_goals
from tools.fitness.coach import get_coach_plan
from tools.fitness.search import web_search
from tools.fitness.form_analysis import analyze_form
from tools.calendar.events import get_upcoming_events
from tools.health.recovery import get_recovery_status

load_dotenv()
logging.basicConfig(level=logging.WARNING)


def get_model():
    provider = os.getenv("LLM_PROVIDER", "lemonade")
    if provider == "claude":
        return ChatAnthropic(model="claude-opus-4-7")
    return ChatOpenAI(
        base_url="http://localhost:13305/v1",
        api_key="lemonade",
        model="Qwen3-8B-GGUF",
    )


tools = [
    # Strava
    get_recent_activities,
    get_athlete_profile,
    get_best_efforts,
    get_training_summary,
    get_shoes,
    get_top_friends,
    get_my_clubs,
    run_daily_kudos,
    build_top_friends,
    update_top_friends,
    # Fitness planning
    get_coach_plan,
    get_weather_forecast,
    read_goals,
    save_goals,
    web_search,
    # Calendar
    get_upcoming_events,
    # Health platforms
    get_recovery_status,
    # Form analysis
    analyze_form,
]

SYSTEM_PROMPT = """You are Balboa, a personal fitness assistant with access to tools.

When the user asks about workouts, training, or what to do next:
- ALWAYS call get_recent_activities to understand their recent training load
- ALWAYS call get_coach_plan to see what the coach has scheduled this week
- ALWAYS call get_weather_forecast to check upcoming conditions
- ALWAYS call read_goals to understand their fitness goals
- ALWAYS call get_upcoming_events to check for travel, busy days, or conflicts before recommending workout timing
- ALWAYS call get_recovery_status to check sleep and HRV before recommending intensity — low recovery means easy day
- Use get_best_efforts to contextualize performance — reference PRs when suggesting paces or goals
- Use web_search to find local races, running events, or any information not in the tools above
- Combine everything to give a specific, reasoned recommendation: what to do, when, and why

When reporting data from tools, be exact:
- Copy exercise names and workout descriptions EXACTLY as the tool returns them — word for word
- NEVER invent sets, reps, durations, or exercises not explicitly listed in the tool output
- If the tool says "Plank" with no sets or reps, report "Plank" — nothing more
- Tool output is ground truth. Do not substitute or supplement with your own knowledge.

Never say you cannot access data — use the tools provided. Be concise and specific."""

agent = create_react_agent(get_model(), tools, prompt=SYSTEM_PROMPT)

# ---------------------------------------------------------------------------
# Streaming progress display
# ---------------------------------------------------------------------------

TOOL_LABELS = {
    "get_recent_activities":  "fetching recent activities",
    "get_best_efforts":       "computing personal records",
    "get_training_summary":   "analyzing training load",
    "get_athlete_profile":    "loading athlete profile",
    "get_shoes":              "checking gear",
    "get_top_friends":        "loading friends list",
    "get_my_clubs":           "fetching clubs",
    "run_daily_kudos":        "giving kudos",
    "build_top_friends":      "scanning kudos history",
    "update_top_friends":     "updating friends list",
    "get_coach_plan":         "reading coach plan",
    "get_weather_forecast":   "checking weather",
    "read_goals":             "reading goals",
    "save_goals":             "saving goals",
    "web_search":             "searching the web",
    "get_upcoming_events":    "checking your calendar",
    "get_recovery_status":    "checking recovery & sleep",
    "analyze_form":           "analysing video form",
}


class _Spinner:
    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self):
        self._msg = ""
        self._running = False
        self._thread = None

    def start(self, msg: str = "thinking"):
        self._msg = msg
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
            self._thread = None
        sys.stdout.write(f"\r{' ' * (len(self._msg) + 6)}\r")
        sys.stdout.flush()

    def _spin(self):
        for frame in itertools.cycle(self._FRAMES):
            if not self._running:
                break
            sys.stdout.write(f"\r  {frame} {self._msg}")
            sys.stdout.flush()
            time.sleep(0.1)


def _run_agent(history: list) -> tuple:
    """Stream agent execution with live progress. Returns (reply, updated_history, timing)."""
    spinner = _Spinner()
    t0 = time.time()
    t_mark = t0
    llm_secs = 0.0
    tool_secs = 0.0
    accumulated = list(history)
    reply = None

    spinner.start("thinking")

    for chunk in agent.stream({"messages": history}, stream_mode="updates"):
        now = time.time()
        elapsed = now - t_mark

        if "agent" in chunk:
            msgs = chunk["agent"]["messages"]
            accumulated.extend(msgs)
            llm_secs += elapsed
            t_mark = now
            msg = msgs[-1]

            if hasattr(msg, "tool_calls") and msg.tool_calls:
                spinner.stop()
                for tc in msg.tool_calls:
                    label = TOOL_LABELS.get(tc["name"], tc["name"])
                    print(f"  → {label}")
                spinner.start("thinking")
            else:
                spinner.stop()
                reply = msg

        elif "tools" in chunk:
            accumulated.extend(chunk["tools"]["messages"])
            tool_secs += elapsed
            t_mark = now

    total = time.time() - t0
    timing = {"total": total, "llm": llm_secs, "tools": tool_secs}
    return reply, accumulated, timing


# ---------------------------------------------------------------------------
# Startup sync
# ---------------------------------------------------------------------------

def _handle_sync_on_startup():
    if needs_initial_sync():
        print("Balboa: I don't have your Strava activities synced yet.")
        print("         A one-time sync fetches the last 1 year of activities locally.")
        answer = input("         Sync now? (yes/no): ").strip().lower()
        if answer in ("yes", "y"):
            print("         Syncing... (this takes ~10-20 seconds)")
            count = run_initial_sync(progress_callback=lambda msg: print(f"         {msg}"))
            print(f"         Done — {count} activities synced.\n")
        else:
            print("         Skipped. Type 'sync' anytime to sync later.\n")
    elif needs_incremental_sync():
        stats = get_db_stats()
        last = stats.get("last_sync", "")[:16].replace("T", " ")
        print(f"Balboa: Syncing new Strava activities (last sync: {last})...")
        count = run_incremental_sync()
        if count:
            print(f"         {count} new activit{'y' if count == 1 else 'ies'} added.\n")


# ---------------------------------------------------------------------------
# Chat loop
# ---------------------------------------------------------------------------

def chat():
    provider = os.getenv("LLM_PROVIDER", "lemonade")
    print(f"\nBalboa ready [{provider}]. Type 'exit' to quit.")
    print("  Form analysis: drop a video into data/videos/ then ask 'analyse my form'\n")

    _handle_sync_on_startup()

    history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("Goodbye!")
            break

        if user_input.lower() == "sync":
            print("Syncing Strava activities...")
            count = run_incremental_sync(progress_callback=lambda msg: print(f"  {msg}"))
            print(f"Done — {count} new activit{'y' if count == 1 else 'ies'} added.\n")
            continue

        history.append(HumanMessage(content=user_input))

        reply, history, timing = _run_agent(history)

        if reply:
            print(f"\nBalboa: {reply.content}")
            print(f"\n  ⏱  {timing['total']:.1f}s  ·  LLM {timing['llm']:.1f}s  ·  tools {timing['tools']:.1f}s\n")
        else:
            print("\nBalboa: (no response)\n")


if __name__ == "__main__":
    chat()
