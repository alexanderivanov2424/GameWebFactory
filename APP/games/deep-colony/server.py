"""Deep Colony: a real-time co-op colony sim on a 2D grid, inspired by colony-survival games.

1-8 players share one underground colony. Colonists act on their own: they dig, haul, build,
run machines and look after their needs (breath, calories, bladder, stress, health, germs).
Players don't control colonists directly: they give orders (dig, build, deconstruct, cancel,
priority, machine on/off) that go into one shared queue, and every player sees everyone's
orders, cursor and drag box live, in that player's colour. Any player can pause the game or
set its speed (1x, 2x, 3x), so the colony can be planned together paused or live. The world
simulates gases (oxygen, CO2, polluted oxygen, hydrogen, steam), liquids (water, polluted
water), heat (conduction, freezing, boiling), germs and decor; buildings cover oxygen, power
(wires, generators, batteries), food, plumbing (pipes, pumps, toilets, sinks), heating and
decor. Endless: the game ends when every colonist has died or the host ends it.
Rules and numbers: logic/ (see logic/__init__.py) and the JSON in elements/ and buildings/.

Player options:  none
Settings:        {"colonists": 1-8 (3), "mapSize": "small" | "medium" | "large"}
Input messages:  {"type": "input", "cursor"?: [x, y], "tool"?: str (<= 24 chars),
                  "drag"?: [x0, y0, x1, y1]}   held state: where you point, shown to everyone
Game messages (any player, paused or not; spectators can't):
                 {"action": "dig", "rect": [x0, y0, x1, y1], "prio"?: 1-9}
                 {"action": "build", "building": id, "cells": [[x, y], ...], "prio"?: 1-9, "rot"?: 0-3}
                     (1x1 buildings: every cell of a drag; bigger ones: one at cells[0], the
                     top-left of the footprint turned rot quarter turns clockwise; locked until
                     researched)
                 {"action": "sweep", "rect": [...], "prio"?: 1-9}  haul the debris there to storage
                 {"action": "deconstruct", "rect": [...]}   {"action": "cancel", "rect": [...]}
                 {"action": "priority", "rect": [...], "prio": 1-9}
                 {"action": "toggle", "building": id}       machine on/off
                 {"action": "filter", "building": id, "elements": [element ids] | null}  storage filter
                 {"action": "research", "tech": id}          what the colony researches next
                 {"action": "schedule", "schedule": "1"-"3", "blocks": 24 chars of w/d/s}
                 {"action": "assign", "colonist": id, "schedule": "1"-"3"}
                 {"action": "pause", "paused": bool}         {"action": "speed", "speed": 1-3}
                 {"action": "end"}                            host only: end the colony
Public state:    logic/view.py (grid rows, buildings, digs, items, colonists, networks,
                 colony totals, players with cursors, log, clock)
Private state:   {"cell"?: exact values of the cell under your cursor}
Result:          {"reason": "..."}
"""

from gamekit import Choice, Int, LobbyError, RealtimeGame

from .logic import orders
from .logic.match import Match

PALETTE = ["#ff5c5c", "#4fc3f7", "#ffd54f", "#81c784", "#ba68c8", "#ff8a65", "#4db6ac", "#f06292"]
MAX_RECT = 40  # cells per side of an order rectangle


def _int_list(value, length, what):
    if not isinstance(value, list) or len(value) != length or any(type(v) is not int for v in value):
        raise LobbyError(f"Bad {what}.")
    return value


def _rect_cells(data):
    x0, y0, x1, y1 = _int_list(data.get("rect"), 4, "area")
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    if x1 - x0 >= MAX_RECT or y1 - y0 >= MAX_RECT:
        raise LobbyError(f"Areas are at most {MAX_RECT}x{MAX_RECT}.")
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


def _prio(data, default=5):
    prio = data.get("prio", default)
    if type(prio) is not int or not 1 <= prio <= 9:
        raise LobbyError("Priority must be 1-9.")
    return prio


class Game(RealtimeGame):
    MIN_PLAYERS = 1
    MAX_PLAYERS = 8
    TICK_RATE = 10
    SETTINGS = {
        "colonists": Int("Colonists", default=3, low=1, high=8),
        "mapSize": Choice("Map size", default="medium",
                          options={"small": "Small", "medium": "Medium", "large": "Large"}),
    }
    ACTIONS = {
        "dig": "dig", "build": "build", "deconstruct": "deconstruct", "cancel": "cancel",
        "priority": "priority", "toggle": "toggle", "pause": "pause", "speed": "speed",
        "end": "end_colony", "sweep": "sweep", "filter": "set_filter", "research": "research",
        "schedule": "set_schedule", "assign": "assign",
    }

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    def reset_game(self):
        self.match = None

    def start_game(self):
        players = self.players
        colors = {p.id: PALETTE[i % len(PALETTE)] for i, p in enumerate(players)}
        self.match = Match({p.id: p.name for p in players}, self.settings, colors=colors)
        for p in players:
            p.input = {}

    # --- real time ------------------------------------------------------------------------

    def on_input(self, member, data):
        clean = {}
        if "cursor" in data:
            clean["cursor"] = _int_list(data["cursor"], 2, "cursor")
        if "drag" in data:
            clean["drag"] = _int_list(data["drag"], 4, "drag")
        tool = data.get("tool")
        if isinstance(tool, str) and tool:
            clean["tool"] = tool[:24]
        member.input = clean

    def tick(self, dt):
        match = self.match
        if match is None or match.result is not None:
            return
        if not match.paused:
            for _ in range(match.speed):
                match.step(dt)
        self.check_over()

    def game_state(self):
        cursors = {p.id: dict(p.input or {}) for p in self.players}
        return self.match.public(cursors)

    def private_state(self, member):
        if not member.playing or self.match is None:
            return None
        return self.match.private(member.id, (member.input or {}).get("cursor"))

    # --- orders ---------------------------------------------------------------------------

    async def on_game_message(self, member, data):
        if not member.playing:
            raise LobbyError("Join the game to give orders.")
        await self.dispatch(member, data)

    def dig(self, member, data):
        orders.dig(self.match, member.id, _rect_cells(data), _prio(data))

    def build(self, member, data):
        building = data.get("building")
        if not isinstance(building, str):
            raise LobbyError("Pick a building.")
        cells = data.get("cells")
        if not isinstance(cells, list) or not 1 <= len(cells) <= orders.MAX_CELLS:
            raise LobbyError("Bad cells.")
        cells = [tuple(_int_list(c, 2, "cell")) for c in cells]
        rot = data.get("rot", 0)
        if type(rot) is not int or not 0 <= rot <= 3:
            raise LobbyError("Bad rotation.")
        orders.build(self.match, member.id, building, cells, _prio(data), rot)

    def sweep(self, member, data):
        orders.sweep(self.match, member.id, _rect_cells(data), _prio(data))

    def set_filter(self, member, data):
        building = data.get("building")
        if not isinstance(building, str):
            raise LobbyError("Pick a building.")
        orders.set_filter(self.match, member.id, building, data.get("elements"))

    def research(self, member, data):
        tech = data.get("tech")
        if not isinstance(tech, str):
            raise LobbyError("Pick a research.")
        self.match.research.select(member.id, tech)

    def set_schedule(self, member, data):
        sid = data.get("schedule")
        if not isinstance(sid, str):
            raise LobbyError("Unknown schedule.")
        self.match.schedules.set_blocks(member.id, sid, data.get("blocks"))

    def assign(self, member, data):
        dupe, sid = data.get("colonist"), data.get("schedule")
        if not isinstance(dupe, str) or not isinstance(sid, str):
            raise LobbyError("Pick a colonist and a schedule.")
        self.match.schedules.assign(member.id, dupe, sid)

    def deconstruct(self, member, data):
        orders.deconstruct(self.match, member.id, _rect_cells(data))

    def cancel(self, member, data):
        orders.cancel(self.match, member.id, _rect_cells(data))

    def priority(self, member, data):
        orders.set_priority(self.match, member.id, _rect_cells(data), _prio(data))

    def toggle(self, member, data):
        building = data.get("building")
        if not isinstance(building, str):
            raise LobbyError("Pick a building.")
        orders.toggle(self.match, member.id, building)

    def pause(self, member, data):
        paused = data.get("paused")
        if type(paused) is not bool:
            raise LobbyError("Bad pause.")
        self.match.set_paused(member.id, paused)

    def speed(self, member, data):
        speed = data.get("speed")
        if type(speed) is not int:
            raise LobbyError("Speed must be 1, 2 or 3.")
        self.match.set_speed(member.id, speed)

    def end_colony(self, member, data):
        if member.id != self.host_id:
            raise LobbyError("Only the host can end the colony.")
        self.finish({"reason": f"{member.name} ended the colony on cycle {self.match.cycle}."})

    def admin_info(self):
        info = super().admin_info()
        if self.match is not None:
            m = self.match
            info["colony"] = {"cycle": m.cycle, "colonists": len(m.dupes), "paused": m.paused,
                              "speed": m.speed, "buildings": len(m.buildings.by_id)}
        return info

    # --- leaving --------------------------------------------------------------------------

    def on_player_removed(self, member):
        self.match.remove(member.id)
        if not self.players:
            self.finish({"reason": "Everyone left."})

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
