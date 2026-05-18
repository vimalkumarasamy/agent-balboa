import os
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
]

SYSTEM_PROMPT = """You are Balboa, a personal fitness assistant and document helper with access to tools.

When the user asks about workouts, training, or what to do next:
- ALWAYS call get_recent_activities to understand their recent training load
- ALWAYS call get_coach_plan to see what the coach has scheduled this week
- ALWAYS call get_weather_forecast to check upcoming conditions
- ALWAYS call read_goals to understand their fitness goals
- Use get_best_efforts to contextualize performance — reference PRs when suggesting paces or goals
- Use web_search to find local races, running events, or any information not in the tools above
- Combine everything to give a specific, reasoned recommendation: what to do, when, and why

Never say you cannot access data — use the tools provided. Be concise and specific."""

agent = create_react_agent(get_model(), tools, prompt=SYSTEM_PROMPT)


def _handle_sync_on_startup():
    """Check sync status and prompt user on first run or after 24h."""
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


def chat():
    provider = os.getenv("LLM_PROVIDER", "lemonade")
    print(f"\nBalboa ready [{provider}]. Type 'exit' to quit.\n")

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

        # Manual sync trigger
        if user_input.lower() == "sync":
            print("Syncing Strava activities...")
            count = run_incremental_sync(progress_callback=lambda msg: print(f"  {msg}"))
            print(f"Done — {count} new activit{'y' if count == 1 else 'ies'} added.\n")
            continue

        history.append(HumanMessage(content=user_input))

        response = agent.invoke({"messages": history})
        messages = response["messages"]

        reply = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage) and m.content),
            None,
        )

        if reply:
            print(f"\nBalboa: {reply.content}\n")
            history = messages
        else:
            print("\nBalboa: (no response)\n")


if __name__ == "__main__":
    chat()
