"""Bastion: the siege, a deterministic tick-by-tick simulation of one level's waves against the board.

    result = run_siege(board, level, keep_hp, hp_scale, battle_id)
    result.keep          keep health afterwards (<= 0: the keep fell)
    result.held          True if the keep still stands
    result.replay        everything the client needs to animate it (format below)
    result.summary       {"kills", "leaked", "keepDamage", "wallsLost", "ticks"}
The board is changed in place: walls keep their damage and destroyed walls are removed.

One tick, in order:
  1. enemies due this tick enter at the start of their road
  2. towers fire (each waits `cooldown` ticks between shots) at the enemy nearest the keep in
     range: `area` towers hit every enemy in range, `splash` towers also hit ground enemies
     within that radius of the target; `air`/`ground` say what they can hit; `pierce` ignores
     armor; otherwise armor is taken off each hit (at least 1 damage gets through)
  3. spikes hurt ground enemies standing on them (armor ignored)
  4. barracks soldiers (one squad per barracks, holding its rally cell) respawn when due and
     strike one enemy they block
  5. enemies: regenerate, heal, summon, breathe; then walk (tar slows), or, when the next cell
     ahead holds a wall or a squad, stop in front of it and attack it (exploding enemies blow
     up instead); flying enemies ignore walls, squads, spikes and tar
  6. enemies at the end of their road hit the keep and leave; the siege ends when the keep
     falls, or when every enemy has entered and none is left.
Bonuses from the board: forges add damage to towers and barracks next to them, watchtowers add
range to towers next to them, a farm next to a barracks halves its respawn time.

Replay (sent once in the public state as game.battle):
    {"id", "level", "ticks", "held", "keep": [before, after], "summary",
     "enemies": {uid: [enemy id, road, max hp]},
     "frames":  one flat list per tick: [uid, round(progress * 100), hp, uid, ...] (alive enemies)
     "events":  [[tick, "s", x, y, uid, shot style], shots
                 [tick, "k", uid, keep hp],          an enemy reached the keep
                 [tick, "w", "x,y", hp],             wall health (0 = destroyed)
                 [tick, "q", squad id, hp],          squad health (0 = all dead)
                 [tick, "b", x10, y10, radius10, stun ticks],   a breath attack (stuns towers)
                 [tick, "x", uid]]                   an enemy exploded
     "walls":   {"x,y": [card id, level, hp, max hp]} at the start
     "towers":  {"x,y": card id} at the start (re-watching after the board changed)
     "squads":  {squad id: [x, y, max hp, barracks x, barracks y]}}
"""

import math

from .board import distance, key
from .cards import CARDS, stat
from .enemies import ENEMIES

MAX_TICKS = 3000
STOP = 0.55  # an enemy stops this far (in road cells) before the cell of what blocks it


class Enemy:
    def __init__(self, uid, kind, road, cells, hp_scale, p=0.0):
        self.uid = uid
        self.kind = kind
        self.info = ENEMIES[kind]
        self.road = road
        self.cells = cells
        self.p = p
        self.max_hp = max(1, round(self.info["hp"] * hp_scale))
        self.hp = float(self.max_hp)
        self.alive = True
        self.blocker = None
        self.attack_timer = max(1, self.info["attackEvery"] // 2)
        self.timers = {"heal": 0, "summon": 0, "breath": 0}
        self.summoned = 0
        self.xy = cells[0]

    def position(self):
        last = len(self.cells) - 1
        p = min(max(self.p, 0.0), last)
        i = min(int(p), last - 1)
        f = p - i
        (x1, y1), (x2, y2) = self.cells[i], self.cells[i + 1]
        return x1 + (x2 - x1) * f, y1 + (y2 - y1) * f

    def cell(self):
        return self.cells[min(int(self.p + 0.5), len(self.cells) - 1)]

    def remaining(self):
        return len(self.cells) - 1 - self.p


class Tower:
    def __init__(self, structure, board):
        card = CARDS[structure.card]
        level = structure.level
        self.x, self.y = structure.x, structure.y
        self.shot = card["shot"]
        self.damage = stat(card, "damage", level) + board.boost(self.x, self.y, "forge")
        self.range = stat(card, "range", level) + board.boost(self.x, self.y, "watch")
        self.min_range = stat(card, "minRange", level)
        self.cooldown = max(1, int(stat(card, "cooldown", level, 1)))
        self.air = bool(stat(card, "air", level, False))
        self.ground = bool(stat(card, "ground", level, True))
        self.pierce = bool(stat(card, "pierce", level, False))
        self.area = bool(stat(card, "area", level, False))
        self.splash = stat(card, "splash", level)
        self.timer = 0
        self.stunned = -1


class Wall:
    def __init__(self, structure):
        self.structure = structure
        self.cell = (structure.x, structure.y)
        self.key = key(*self.cell)
        self.is_wall = True

    @property
    def hp(self):
        return self.structure.hp

    def alive(self, tick):
        return self.structure.hp > 0

    def hit(self, damage, tick):
        self.structure.hp = max(0.0, self.structure.hp - damage)


class Squad:
    def __init__(self, sid, structure, cell, board):
        card = CARDS[structure.card]
        level = structure.level
        self.sid = sid
        self.home = (structure.x, structure.y)
        self.cell = cell
        self.is_wall = False
        self.max_hp = stat(card, "hp", level)
        self.damage = stat(card, "damage", level) + board.boost(*self.home, "forge")
        self.cooldown = max(1, int(stat(card, "cooldown", level, 2)))
        fed = board.near(*self.home, "farm")
        self.respawn = max(1, int(stat(card, "respawn", level, 20) / (2 if fed else 1)))
        self.hp = float(self.max_hp)
        self.timer = 0
        self.back_at = 0

    def alive(self, tick):
        return self.hp > 0

    def hit(self, damage, tick):
        self.hp = max(0.0, self.hp - damage)
        if self.hp <= 0:
            self.back_at = tick + self.respawn


class Result:
    def __init__(self, keep, replay, summary):
        self.keep = keep
        self.held = keep > 0
        self.replay = replay
        self.summary = summary


class Siege:
    def __init__(self, board, level, keep_hp, hp_scale):
        self.board = board
        self.map = board.map
        self.level = level
        self.keep = keep_hp
        self.hp_scale = hp_scale
        self.enemies = []
        self.uid = 0
        self.towers = [Tower(s, board) for s in board.of_kind("tower")]
        self.spikes = {(s.x, s.y): stat(CARDS[s.card], "damage", s.level) for s in board.of_kind("spikes")}
        self.tar = {(s.x, s.y): stat(CARDS[s.card], "slow", s.level) for s in board.of_kind("tar")}
        self.walls = [Wall(s) for s in board.of_kind("wall") if s.hp > 0]
        self.squads = []
        for structure in board.of_kind("barracks"):
            cell = board.rally(structure.x, structure.y)
            if cell:
                self.squads.append(Squad(len(self.squads) + 1, structure, cell, board))
        self.blockers = {}  # cell -> [blocker, ...] (squads first: they stand in front)
        for blocker in self.squads + self.walls:
            self.blockers.setdefault(blocker.cell, []).append(blocker)
        # For each road, the indices of its cells that can hold a blocker.
        self.block_points = {name: [i for i, c in enumerate(cells) if c in self.blockers]
                             for name, cells in self.map.roads.items()}
        self.spawns = sorted(
            ((wave["start"] + n * wave["gap"], i, wave["enemy"], wave["road"])
             for i, wave in enumerate(level["waves"]) for n in range(wave["count"])))
        self.events = []
        self.frames = []
        self.kills = 0
        self.leaked = 0
        self.tick = 0
        self.changed = {}  # this tick's blocker health changes: event key -> event

    # --- helpers --------------------------------------------------------------------------

    def add_enemy(self, kind, road, p=0.0):
        self.uid += 1
        enemy = Enemy(self.uid, kind, road, self.map.roads[road], self.hp_scale, p)
        self.enemies.append(enemy)
        return enemy

    def hurt(self, enemy, damage, pierce=False):
        if not enemy.alive:
            return
        if not pierce:
            damage = max(1, damage - enemy.info["armor"])
        enemy.hp -= damage
        if enemy.hp <= 0:
            enemy.alive = False
            self.kills += 1

    def hit_blocker(self, blocker, damage):
        blocker.hit(damage, self.tick)
        if blocker.is_wall:
            self.changed[("w", blocker.key)] = [self.tick, "w", blocker.key, math.ceil(blocker.hp)]
        else:
            self.changed[("q", blocker.sid)] = [self.tick, "q", blocker.sid, math.ceil(blocker.hp)]

    def alive_blocker(self, cell):
        for blocker in self.blockers.get(cell, ()):
            if blocker.alive(self.tick):
                return blocker
        return None

    # --- one tick ---------------------------------------------------------------------------

    def spawn(self):
        while self.spawns and self.spawns[0][0] <= self.tick:
            _, _, kind, road = self.spawns.pop(0)
            self.add_enemy(kind, road)

    def fire_towers(self, alive):
        for tower in self.towers:
            if tower.stunned >= self.tick:
                continue
            if tower.timer > 0:
                tower.timer -= 1
                if tower.timer > 0:
                    continue
            in_range = []
            for enemy in alive:
                if not enemy.alive or not (tower.air if enemy.info["flying"] else tower.ground):
                    continue
                d = distance(enemy.xy, (tower.x, tower.y))
                if tower.min_range <= d <= tower.range + 1e-9:
                    in_range.append(enemy)
            if not in_range:
                continue
            target = min(in_range, key=lambda e: (e.remaining(), e.uid))
            if tower.area:
                hits = in_range
            elif tower.splash:
                hits = [target] + [e for e in alive if e is not target and e.alive and not e.info["flying"]
                                   and distance(e.xy, target.xy) <= tower.splash + 1e-9]
            else:
                hits = [target]
            for enemy in hits:
                self.hurt(enemy, tower.damage, tower.pierce)
            self.events.append([self.tick, "s", tower.x, tower.y, target.uid, tower.shot])
            tower.timer = tower.cooldown

    def traps(self, alive):
        for enemy in alive:
            if enemy.alive and not enemy.info["flying"]:
                damage = self.spikes.get(enemy.cell())
                if damage:
                    self.hurt(enemy, damage, pierce=True)

    def fight_squads(self, alive):
        for squad in self.squads:
            if not squad.alive(self.tick):
                if self.tick >= squad.back_at:
                    squad.hp = float(squad.max_hp)
                    squad.timer = 0
                    self.changed[("q", squad.sid)] = [self.tick, "q", squad.sid, math.ceil(squad.hp)]
                continue
            if squad.timer > 0:
                squad.timer -= 1
                if squad.timer > 0:
                    continue
            foes = [e for e in alive if e.alive and e.blocker is squad]
            if foes:
                self.hurt(min(foes, key=lambda e: (e.hp, e.uid)), squad.damage)
                squad.timer = squad.cooldown

    def specials(self, enemy, alive):
        info = enemy.info
        if info["regen"]:
            enemy.hp = min(enemy.max_hp, enemy.hp + info["regen"])
        heal = info["heal"]
        if heal and self._due(enemy, "heal", heal["every"]):
            for other in alive:
                if other is not enemy and other.alive and distance(other.xy, enemy.xy) <= heal["radius"]:
                    other.hp = min(other.max_hp, other.hp + heal["amount"])
        summon = info["summon"]
        if summon and enemy.summoned < summon["max"] and self._due(enemy, "summon", summon["every"]):
            enemy.summoned += 1
            raised = self.add_enemy(summon["enemy"], enemy.road, max(0.0, enemy.p - 0.3))
            raised.xy = raised.position()
        breath = info["breath"]
        if breath and self._due(enemy, "breath", breath["every"]):
            x, y = enemy.xy
            for tower in self.towers:
                if distance((tower.x, tower.y), enemy.xy) <= breath["radius"]:
                    tower.stunned = max(tower.stunned, self.tick + int(breath["stun"]))
            if breath["damage"]:
                for blocker in self.squads + self.walls:
                    if blocker.alive(self.tick) and distance(blocker.cell, enemy.xy) <= breath["radius"]:
                        self.hit_blocker(blocker, breath["damage"])
            self.events.append([self.tick, "b", round(x * 10), round(y * 10), round(breath["radius"] * 10),
                                int(breath["stun"])])

    def _due(self, enemy, name, every):
        enemy.timers[name] += 1
        if enemy.timers[name] >= every:
            enemy.timers[name] = 0
            return True
        return False

    def walk(self, enemy):
        info = enemy.info
        speed = info["speed"]
        if not info["flying"]:
            slow = self.tar.get(enemy.cell())
            if slow:
                speed *= max(0.0, 1 - slow / 100)
        target = enemy.p + speed
        enemy.blocker = None
        if not info["flying"]:
            for i in self.block_points[enemy.road]:
                stop = i - STOP
                if stop < enemy.p - 1e-9:
                    continue
                if stop >= target:
                    break
                blocker = self.alive_blocker(enemy.cells[i])
                if blocker:
                    target = stop
                    enemy.blocker = blocker
                    break
        enemy.p = target
        blocker = enemy.blocker
        if blocker:
            enemy.attack_timer -= 1
            if enemy.attack_timer <= 0:
                enemy.attack_timer = info["attackEvery"]
                if info["explode"]:
                    self.hit_blocker(blocker, info["explode"])
                    enemy.alive = False
                    self.events.append([self.tick, "x", enemy.uid])
                elif info["attack"]:
                    self.hit_blocker(blocker, info["attack"] * (info["siege"] if blocker.is_wall else 1))

    def step(self):
        self.spawn()
        alive = [e for e in self.enemies if e.alive]
        for enemy in alive:
            enemy.xy = enemy.position()
        self.fire_towers(alive)
        self.traps(alive)
        self.fight_squads(alive)
        for enemy in alive:
            if enemy.alive:
                self.specials(enemy, alive)
        for enemy in list(self.enemies):
            if enemy.alive and enemy not in alive:
                enemy.xy = enemy.position()  # summoned this tick: walks from next tick
            elif enemy.alive:
                self.walk(enemy)
                if enemy.remaining() <= 1e-9:
                    enemy.alive = False
                    self.leaked += 1
                    self.keep -= enemy.info["keep"]
                    self.events.append([self.tick, "k", enemy.uid, max(0, self.keep)])
        self.events.extend(self.changed.values())
        self.changed = {}
        self.enemies = [e for e in self.enemies if e.alive]
        frame = []
        for enemy in self.enemies:
            frame += [enemy.uid, round(enemy.p * 100), math.ceil(enemy.hp)]
        self.frames.append(frame)
        self.tick += 1

    def over(self):
        return self.keep <= 0 or (not self.spawns and not self.enemies) or self.tick >= MAX_TICKS


def run_siege(board, level, keep_hp, hp_scale, battle_id=0, level_number=0):
    walls_before = {key(s.x, s.y): [s.card, s.level, math.ceil(s.hp), s.max_hp()] for s in board.of_kind("wall")}
    siege = Siege(board, level, keep_hp, hp_scale)
    roster = {}
    while not siege.over():
        siege.step()
        for enemy in siege.enemies:
            roster.setdefault(str(enemy.uid), [enemy.kind, enemy.road, enemy.max_hp])
    if siege.tick >= MAX_TICKS and siege.enemies:  # stragglers storm the keep
        for enemy in siege.enemies:
            siege.leaked += 1
            siege.keep -= enemy.info["keep"]
    lost = [s for s in board.of_kind("wall") if s.hp <= 0]
    for structure in lost:
        del board.structures[(structure.x, structure.y)]
    summary = {"kills": siege.kills, "leaked": siege.leaked, "keepDamage": keep_hp - max(0, siege.keep),
               "wallsLost": len(lost), "ticks": siege.tick}
    replay = {
        "id": battle_id,
        "level": level_number,
        "ticks": siege.tick,
        "held": siege.keep > 0,
        "keep": [keep_hp, max(0, siege.keep)],
        "summary": summary,
        "enemies": roster,
        "frames": siege.frames,
        "events": siege.events,
        "walls": walls_before,
        "towers": {key(t.x, t.y): board.at(t.x, t.y).card for t in siege.towers},
        "squads": {str(s.sid): [s.cell[0], s.cell[1], s.max_hp, s.home[0], s.home[1]] for s in siege.squads},
    }
    return Result(siege.keep, replay, summary)
