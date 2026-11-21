"""Planet Jumpers: mission cards, loaded from missions/<id>.json next to server.py, and the 3 mission decks.

A mission file:
    {"name": "Moon Pit Stop", "deck": 1, "fuel": 3, "food": 3,
     "tasks": ["refuel", "safety-checks", "load-supplies"],   # task ids (tasks/), drafted each mission
     "setup": ["Any special setup, one line each"]}
"fuel" / "food" are what the tasks with a fuel / food effect give the ship.

    MISSIONS                      {id: mission}
    DECKS                         (1, 2, 3): missions are drawn from deck 1 until it's empty, then 2, then 3
    deck_left(completed)          {deck: missions left in it}: a played mission is discarded
    draw(completed, rng)          a random mission id from the lowest deck that isn't empty, or None
                                  once every deck is empty (the run is complete)
"""

import logging
from pathlib import Path

from gamekit.data import DataError, load_json_dir, text, whole

from .tasks import TASKS

log = logging.getLogger("orbit-run.missions")
DECKS = (1, 2, 3)


def parse_mission(mission_id, data):
    tasks = data.get("tasks", [])
    if not isinstance(tasks, list) or any(t not in TASKS for t in tasks) or len(set(tasks)) != len(tasks):
        raise DataError("tasks must be a list of different task ids from tasks/")
    setup = data.get("setup", [])
    if not isinstance(setup, list) or not all(isinstance(line, str) for line in setup):
        raise DataError("setup must be a list of strings")
    return {
        "id": mission_id,
        "name": text(data, "name", 40, required=True),
        "deck": whole(data, "deck", DECKS[0], DECKS[-1]),
        "fuel": whole(data, "fuel", 0, 9, default=0),
        "food": whole(data, "food", 0, 9, default=0),
        "tasks": tasks,
        "setup": [line.strip()[:200] for line in setup if line.strip()],
    }


MISSIONS = load_json_dir(Path(__file__).parent.parent / "missions", parse_mission, log)


def deck_left(completed):
    done = set(completed)
    return {d: sum(1 for m in MISSIONS.values() if m["deck"] == d and m["id"] not in done) for d in DECKS}


def draw(completed, rng):
    done = set(completed)
    for d in DECKS:
        left = [m for m in MISSIONS if MISSIONS[m]["deck"] == d and m not in done]
        if left:
            return rng.choice(left)
    return None
