"""Bastion: loading the enemy files (content/enemies/*.json) when the game is imported.

Enemies are cards above the board, not units on it. Each has 2-3 attacks it makes in turn (one
at the end of every round it's active) and its own ways to be beaten. Fields are documented in
content/README.md. Bad files are logged (logger "bastion") and skipped.

    ENEMIES   {id: enemy}, enemy = {
        "id", "name", "icon", "text", "tier": 1-3 (3 = a final boss),
        "hp":      damage it takes to beat (scaled by difficulty and players; a lair's tiles
                   instead when it has one)
        "defeat":  {"soldiers": soldiers per damage, "resources": {resource: n} per damage,
                    "cure": each plague it spread that is cured hurts it,
                    "cards": each of its curse cards paid off hurts it,
                    "raze": soldiers per lair tile razed} (any, at least one)
        "lair":    None or {"name", "icon", "cells": [(dy, dx)]}: placed on empty grass on arrival
        "attacks": [attack], attack = {"name", "text" (generated), and any of:
                    "steal": {resource | "most": n}  ("most": the good the city has most of)
                    "loot": n goods taken from unprotected road tiles (left there by hauls)
                    "ruin": n tiles, "prefer": [structure id] (those first)
                    "keep": damage, "shield": each wall tile next to the keep blocks 1
                    "place": {"name", "icon"}, "count": n   blight tiles on empty grass
                    "curse": card id, "to": "each" | "one"   added to discard piles
                    "plague": n buildings, "freeze": n buildings (can't work next round)
                    "kill": n soldiers} }
    attack_text(attack) / defeat_text(enemy)   readable rules text
    load_enemies(folder, cards) -> ENEMIES (tests feed temporary folders)
"""

import logging

from gamekit.data import flag, load_json_dir, text, whole
from gamekit.shapes import parse

from .cards import CARDS, amount_text
from .structures import CONTENT, RESOURCE_IDS, STRUCTURES, amounts

log = logging.getLogger("bastion")

ATTACK_KEYS = ("steal", "loot", "ruin", "keep", "place", "curse", "plague", "freeze", "kill")


def blight(data, key):
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object with name and icon")
    return {"name": text(value, "name", 30, required=True), "icon": text(value, "icon", 8)}


def parse_attack(data, cards):
    if not isinstance(data, dict):
        raise ValueError("each attack must be an object")
    attack = {"name": text(data, "name", 30, required=True)}
    if "steal" in data:
        attack["steal"] = amounts(data, "steal", RESOURCE_IDS + ["most"])
    for key, high in (("loot", 10), ("ruin", 6), ("keep", 20), ("plague", 4), ("freeze", 4), ("kill", 10)):
        if key in data:
            attack[key] = whole(data, key, 1, high)
    if "ruin" in attack:
        prefer = data.get("prefer", [])
        if not isinstance(prefer, list) or any(p not in STRUCTURES for p in prefer):
            raise ValueError("prefer must list structure ids")
        attack["prefer"] = prefer
    if "keep" in attack:
        attack["shield"] = flag(data, "shield")
    if "place" in data:
        attack["place"] = blight(data, "place")
        attack["count"] = whole(data, "count", 1, 4, default=1)
    if "curse" in data:
        if data["curse"] not in cards or cards[data["curse"]]["kind"] != "curse":
            raise ValueError("curse must be a curse card id")
        attack["curse"] = data["curse"]
        attack["to"] = data.get("to", "one")
        if attack["to"] not in ("each", "one"):
            raise ValueError("to must be \"each\" or \"one\"")
    attack["text"] = text(data, "text", 200) or attack_text(attack, cards)
    return attack


def attack_text(attack, cards=CARDS):
    parts = []
    if "steal" in attack:
        steal = dict(attack["steal"])
        most = steal.pop("most", 0)
        if steal:
            parts.append("Steals " + ("all gold" if steal.get("gold", 0) >= 20 and len(steal) == 1 else amount_text(steal)) + ".")
        if most:
            parts.append(f"Steals {most} of the good you have most of.")
    if "loot" in attack:
        parts.append(f"Loots {attack['loot']} goods left on roads (not next to a wall or near a watchtower).")
    if "ruin" in attack:
        n = attack["ruin"]
        where = ""
        if attack.get("prefer"):
            where = " (" + ", ".join(STRUCTURES[p]["name"] for p in attack["prefer"]) + " first)"
        parts.append(f"Ruins {n} unprotected building tile{'s' if n > 1 else ''}{where}.")
    if "keep" in attack:
        shield = ", 1 less per wall tile next to it" if attack.get("shield") else ""
        parts.append(f"{attack['keep']} damage to the keep{shield}.")
    if "place" in attack:
        n = attack["count"]
        parts.append(f"Puts {n} {attack['place']['name']}{'s' if n > 1 else ''} on the board "
                     f"(-1 output to buildings next to it).")
    if "curse" in attack:
        who = "each player's" if attack["to"] == "each" else "one player's"
        parts.append(f"Puts a {cards[attack['curse']]['name']} card in {who} discard pile.")
    if "plague" in attack:
        parts.append(f"Plagues {attack['plague']} building{'s' if attack['plague'] > 1 else ''} (can't work until cured).")
    if "freeze" in attack:
        parts.append(f"Freezes {attack['freeze']} building{'s' if attack['freeze'] > 1 else ''} for the next round.")
    if "kill" in attack:
        parts.append(f"Kills {attack['kill']} soldier{'s' if attack['kill'] > 1 else ''}.")
    return " ".join(parts) or "Rests."


def defeat_text(enemy):
    d, parts = enemy["defeat"], []
    if d.get("soldiers"):
        parts.append(f"{d['soldiers']} soldier{'s' if d['soldiers'] > 1 else ''} per damage")
    if d.get("resources"):
        parts.append(f"{amount_text(d['resources'])} per damage")
    if d.get("cure"):
        parts.append("1 damage per plague cured")
    if d.get("cards"):
        parts.append("1 damage per curse card paid off")
    if d.get("raze"):
        parts.append(f"raze its {enemy['lair']['name']} ({d['raze']} soldiers per tile)")
    return "; ".join(parts)


def parse_enemy(enemy_id, data, cards):
    defeat_data = data.get("defeat")
    if not isinstance(defeat_data, dict):
        raise ValueError("defeat must be an object")
    defeat = {}
    for key in ("soldiers", "raze"):
        if key in defeat_data:
            defeat[key] = whole(defeat_data, key, 1, 10)
    if "resources" in defeat_data:
        defeat["resources"] = amounts(defeat_data, "resources", RESOURCE_IDS)
    for key in ("cure", "cards"):
        if flag(defeat_data, key):
            defeat[key] = True
    if not defeat:
        raise ValueError("defeat needs at least one way")
    lair = None
    if "lair" in data:
        lair = blight(data, "lair")
        cells, _, _ = parse(data["lair"].get("shape"), max_size=3)
        lair["cells"] = cells
    if ("raze" in defeat) != (lair is not None):
        raise ValueError("a lair and defeat.raze go together")
    attacks = data.get("attacks")
    if not isinstance(attacks, list) or not 1 <= len(attacks) <= 4:
        raise ValueError("attacks must be a list of 1 to 4 attacks")
    enemy = {
        "id": enemy_id,
        "name": text(data, "name", 30, required=True),
        "icon": text(data, "icon", 8),
        "text": text(data, "text", 300),
        "tier": whole(data, "tier", 1, 3),
        "hp": whole(data, "hp", 1, 50, default=len(lair["cells"]) if lair else None),
        "defeat": defeat,
        "lair": lair,
        "attacks": [parse_attack(a, cards) for a in attacks],
    }
    enemy["defeatText"] = defeat_text(enemy)
    return enemy


def load_enemies(folder, cards):
    return load_json_dir(folder, lambda eid, data: parse_enemy(eid, data, cards), log)


ENEMIES = load_enemies(CONTENT / "enemies", CARDS)
