"""Orbit Run: task cards, loaded from tasks/<id>.json next to server.py.

A task file:
    {"name": "Refuel", "text": "Win 3 or more tricks.",
     "goal": {"kind": "tricks", "min": 3},
     "success": {"fuel": true},          # effects when the task is done at the end of the mission
     "failure": {"damage": 1}}           # effects when it isn't
Goal kinds (GOALS: kind -> (parse, check)):
    tricks  {"min": n}             the holder wins n or more tricks
    cards   {"cards": ["r3", ...]} the holder wins every listed card (in any of their tricks)
Effects (ship.apply_effects): "fuel": true / "food": true add the mission's fuel / food amount,
"damage": n takes n hull, "science": n adds science.

    TASKS                    {id: task}
    status(task, mine, theirs, chances) -> "done" | "failed" | "open"
        mine:    tricks the holder won (lists of card ids); theirs: set of cards won by others;
        chances: how many more tricks the holder can still win (0 once the mission is over)
"""

import logging
from pathlib import Path

from gamekit.data import DataError, flag, load_json_dir, text, whole

from . import cards

log = logging.getLogger("orbit-run.tasks")


def _parse_tricks(goal):
    return {"kind": "tricks", "min": whole(goal, "min", 1, 40)}


def _check_tricks(goal, mine, theirs, chances):
    if len(mine) >= goal["min"]:
        return "done"
    return "failed" if len(mine) + chances < goal["min"] else "open"


def _parse_cards(goal):
    wanted = goal.get("cards")
    if not isinstance(wanted, list) or not wanted or any(c not in cards.deck() for c in wanted):
        raise DataError("goal cards must be a list of card ids like \"r3\"")
    return {"kind": "cards", "cards": list(dict.fromkeys(wanted))}


def _check_cards(goal, mine, theirs, chances):
    won = {card for trick in mine for card in trick}
    if all(card in won for card in goal["cards"]):
        return "done"
    return "failed" if any(card in theirs for card in goal["cards"]) or not chances else "open"


GOALS = {"tricks": (_parse_tricks, _check_tricks), "cards": (_parse_cards, _check_cards)}


def parse_effects(data):
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise DataError("effects must be an object")
    effects = {}
    for key in ("fuel", "food"):
        if flag(data, key):
            effects[key] = True
    for key in ("damage", "science"):
        if key in data:
            effects[key] = whole(data, key, 0, 20)
    return effects


def parse_task(task_id, data):
    goal = data.get("goal")
    if not isinstance(goal, dict) or goal.get("kind") not in GOALS:
        raise DataError(f"goal.kind must be one of {', '.join(GOALS)}")
    return {
        "id": task_id,
        "name": text(data, "name", 40, required=True),
        "text": text(data, "text", 200, required=True),
        "goal": GOALS[goal["kind"]][0](goal),
        "success": parse_effects(data.get("success")),
        "failure": parse_effects(data.get("failure")),
    }


TASKS = load_json_dir(Path(__file__).parent.parent / "tasks", parse_task, log)


def status(task, mine, theirs, chances):
    return GOALS[task["goal"]["kind"]][1](task["goal"], mine, theirs, chances)


def public(task):
    return {"id": task["id"], "name": task["name"], "text": task["text"]}
