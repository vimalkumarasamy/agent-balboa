import os

GOALS_FILE = os.path.join(os.path.dirname(__file__), "../../data/goals.md")


def read_goals() -> str:
    """Read your current fitness goals."""
    path = os.path.abspath(GOALS_FILE)
    if not os.path.exists(path):
        return "No goals set yet. Use save_goals to set your fitness goals."
    with open(path) as f:
        return f.read()


def save_goals(goals: str) -> str:
    """Save or update your fitness goals. Provide the full goals text — this
    overwrites the existing goals file."""
    path = os.path.abspath(GOALS_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(goals)
    return "Goals saved successfully."
