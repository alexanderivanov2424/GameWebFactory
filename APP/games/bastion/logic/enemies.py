"""Bastion: loading the enemy files (content/enemies/*.json) and the levels (content/levels/*.json).

    ENEMIES   {id: enemy}, enemy = {
                  "id", "name", "icon", "text",
                  "hp", "speed" (road cells per tick), "armor" (taken off every hit, min 1 damage),
                  "keep" (damage when it reaches the keep), "attack" + "attackEvery" (ticks): hits on
                  walls and soldiers blocking it, "siege" (attack multiplier against walls),
                  "flying" (ignores walls, soldiers and road traps; only towers with "air" hit it),
                  "regen" (hp per tick), "explode" (blows up on the first blocker for that damage),
                  "heal" {"amount", "radius", "every"}: heals other enemies around it,
                  "summon" {"enemy", "every", "max"}: raises another enemy where it stands,
                  "breath" {"radius", "every", "stun", "damage"}: stuns towers around it for
                      `stun` ticks and hurts blockers in range,
                  "boss" (drawn bigger) }
    LEVELS    [level, ...] in file-name order, level = {
                  "id", "name", "text", "buildTurns" (build turns before the siege), "reward" (gold
                  each player gets for holding), "waves": [{"enemy", "count", "road", "start", "gap"}] }
              Roads are "main" and "flank" (every map has both, see maps.py).
    public_level(level)   what clients get (adds "roads": the roads used, "counts": {enemy: n})
"""

import logging

from gamekit.data import flag, load_json_dir, text, whole

from .cards import CONTENT

log = logging.getLogger("bastion")

ROADS = ("main", "flank")


def number(data, key, low, high, default=None):
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(f"{key} must be a number from {low} to {high}")
    return value


def _sub(data, key, fields):
    """An optional object of numbers, e.g. "heal": {"amount": 4, "radius": 1.6, "every": 6}."""
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return {name: number(value, name, low, high, default) for name, (low, high, default) in fields.items()}


def parse_enemy(enemy_id, data):
    enemy = {
        "id": enemy_id,
        "name": text(data, "name", 30, required=True),
        "icon": text(data, "icon", 8, required=True),
        "text": text(data, "text", 240),
        "hp": number(data, "hp", 1, 10000),
        "speed": number(data, "speed", 0.01, 1),
        "armor": whole(data, "armor", 0, 50, default=0),
        "keep": whole(data, "keep", 0, 100, default=1),
        "attack": number(data, "attack", 0, 500, default=0),
        "attackEvery": whole(data, "attackEvery", 1, 100, default=2),
        "siege": number(data, "siege", 0, 20, default=1),
        "flying": flag(data, "flying"),
        "regen": number(data, "regen", 0, 100, default=0),
        "explode": number(data, "explode", 0, 1000, default=0),
        "heal": _sub(data, "heal", {"amount": (0, 500, None), "radius": (0, 10, None), "every": (1, 100, None)}),
        "summon": None,
        "breath": _sub(data, "breath", {"radius": (0, 10, None), "every": (1, 200, None), "stun": (0, 200, 0),
                                         "damage": (0, 500, 0)}),
        "boss": flag(data, "boss"),
    }
    summon = data.get("summon")
    if summon is not None:
        if not isinstance(summon, dict) or not isinstance(summon.get("enemy"), str):
            raise ValueError("summon must be {\"enemy\": id, \"every\": ticks, \"max\": n}")
        enemy["summon"] = {"enemy": summon["enemy"], "every": whole(summon, "every", 1, 200),
                           "max": whole(summon, "max", 1, 50, default=5)}
    return enemy


def _check_summons(enemies):
    for enemy_id in list(enemies):
        summon = enemies[enemy_id]["summon"]
        if summon and summon["enemy"] not in enemies:
            log.error("Skipping enemy %s: summons unknown enemy %r", enemy_id, summon["enemy"])
            del enemies[enemy_id]
    return enemies


def parse_level(level_id, data, enemies):
    waves = data.get("waves")
    if not isinstance(waves, list) or not waves:
        raise ValueError("waves must be a non-empty list")
    clean = []
    for wave in waves:
        if not isinstance(wave, dict) or wave.get("enemy") not in enemies:
            raise ValueError(f"wave enemy must be one of {', '.join(enemies)}")
        if wave.get("road", "main") not in ROADS:
            raise ValueError(f"wave road must be one of {', '.join(ROADS)}")
        clean.append({"enemy": wave["enemy"], "road": wave.get("road", "main"),
                      "count": whole(wave, "count", 1, 100), "start": whole(wave, "start", 0, 2000, default=0),
                      "gap": whole(wave, "gap", 1, 200, default=6)})
    return {
        "id": level_id,
        "name": text(data, "name", 40, required=True),
        "text": text(data, "text", 300),
        "buildTurns": whole(data, "buildTurns", 1, 5, default=2),
        "reward": whole(data, "reward", 0, 50, default=5),
        "waves": clean,
    }


def public_level(level):
    counts = {}
    for wave in level["waves"]:
        counts[wave["enemy"]] = counts.get(wave["enemy"], 0) + wave["count"]
    roads = [road for road in ROADS if any(w["road"] == road for w in level["waves"])]
    return {"name": level["name"], "text": level["text"], "buildTurns": level["buildTurns"],
            "reward": level["reward"], "counts": counts, "roads": roads}


ENEMIES = _check_summons(load_json_dir(CONTENT / "enemies", parse_enemy, log))
LEVELS = list(load_json_dir(CONTENT / "levels", lambda i, d: parse_level(i, d, ENEMIES), log).values())
