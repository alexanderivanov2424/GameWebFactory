"""Marooned: what clients see: the public state for everyone and each player's private part.

    view.public(m)        # server.py's game_state (via Match.public)
    view.private(m, pid)  # server.py's private_state (via Match.private): role, objectives,
                          # your secret roll, tiles you drew, check cards in your hand, your
                          # ballot, and the squares you can move to or explore

Sent with PatchState: no None values (optional keys are left out), collections keyed by id.
"""

from . import actions, objectives, people, scoring
from .actions import DIE, GATHER_YIELD, TOOL_BONUS
from .island import key, tile_types
from .survivor import BASE_ENERGY, MAX_HUNGER, PACK_SIZE


def public(m):
    data = {
        "names": m.names,
        "stage": m.stage,
        "day": m.day,
        "monsoon": m.monsoon,
        "size": m.island.size,
        "camp": list(m.island.camp),
        "tiles": m.island.public(),
        "tileTypes": tile_types(),
        "seats": list(m.seats),
        "order": list(m.order),
        "turnList": list(m.turn_list),
        "people": {pid: {**s.public(), "points": scoring.running(m, pid)} for pid, s in m.people.items()},
        "projects": m.camp.public(),
        "checkDeck": m.checks.public(),
        "tilesLeft": len(m.island.deck),
        "votes": {night_day: entry["tally"] for night_day, entry in m.vote_history.items()},
        "rules": rules(m),
        "log": dict(m.logs),
        "logSize": len(m.logs),
    }
    if m.turn():
        data["turn"] = m.turn()
    if m.actor():
        data["actor"] = m.actor()
    if m.check:
        data["check"] = m.check.public()
    if m.pending:
        data["pending"] = {"kind": m.pending["kind"], "player": m.pending["player"]}
        if m.pending["kind"] == "explore":
            data["pending"]["cell"] = key(m.pending["cell"])
    if m.launch_day is not None:
        data["launchDay"] = m.launch_day
    if m.stage == "objectives":
        data["picked"] = {pid: True for pid in m.seats if m.picks.chosen(pid)}
    if m.stage == "vote":
        data["voted"] = {pid: True for pid in m.order if m.votes.chosen(pid)}
    return data


def rules(m):
    return {
        "energy": BASE_ENERGY, "pack": PACK_SIZE, "maxHunger": MAX_HUNGER, "die": DIE,
        "gatherYield": GATHER_YIELD, "toolBonus": TOOL_BONUS, "tools": actions.tool_rules(),
        "costs": {"explore": actions.EXPLORE_COST, "gather": actions.GATHER_COST,
                  "search": actions.SEARCH_COST, "build": people.BUILD_COST,
                  "craft": people.CRAFT_COST, "attack": people.ATTACK_COST},
        "machete": list(actions.MACHETE_TILES),
        "keep": m.keep,
    }


def private(m, pid):
    if pid not in m.people:
        return None
    data = {"role": "imposter" if pid == m.imposter else "castaway"}
    if m.stage == "objectives":
        data["dealt"] = [objectives.public(oid) for oid in m.dealt.get(pid, [])]
        if m.picks.chosen(pid):
            data["kept"] = list(m.picks.choice(pid))
    else:
        data["objectives"] = [objectives.public(oid) for oid in m.objectives.get(pid, [])]
    if m.pending and m.pending["player"] == pid:
        if m.pending["kind"] == "gather":
            data["roll"] = {"item": m.pending["item"], "face": m.pending["roll"]}
        else:
            data["tileChoices"] = [dict(card) for card in m.pending["cards"]]
    if m.check and m.check.actor() == pid and m.check.step in ("discard", "reveal"):
        data["checkHand"] = [dict(card) for card in m.check.hand]
    if m.stage == "vote" and m.votes.chosen(pid):
        data["ballot"] = m.votes.choice(pid)
    if pid in m.order and m.stage == "day":
        s = m.people[pid]
        data["moves"] = {key(c): actions.move_cost(m, s, c)
                         for c in m.island.neighbours(s.pos) if m.island.tile(c)}
        data["explorable"] = [key(c) for c in m.island.neighbours(s.pos) if m.island.explorable(c)]
    return data
