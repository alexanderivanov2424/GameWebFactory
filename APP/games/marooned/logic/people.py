"""Marooned: day actions with items, the camp and other players.

deposit / take (piles), build (camp projects; may start a build check), craft, eat, heal,
give, attack, launch. Same conventions as actions.py: Match does the turn checks, these
check the rules, spend energy and apply.
"""

from gamekit import LobbyError

from .checks import Check
from .survivor import TOOLS

BUILD_COST = 1
CRAFT_COST = 1
ATTACK_COST = 2
EAT_HUNGER = 1
STAGE_POINTS = 2


def _at_camp(m, s):
    if s.pos != m.island.camp:
        raise LobbyError("You need to be at camp.")


def _count(count):
    if count < 1:
        raise LobbyError("Pick at least one.")
    return count


def deposit(m, pid, item, count):
    s = m.people[pid]
    _at_camp(m, s)
    s.remove(item, _count(count))
    pile = m.island.pile(s.pos)
    pile[item] = pile.get(item, 0) + count


def take(m, pid, item, count):
    s = m.people[pid]
    pile = m.island.pile(s.pos)
    if pile.get(item, 0) < _count(count):
        raise LobbyError(f"There aren't {count} {item} here.")
    if s.space() < count:
        raise LobbyError("Your backpack doesn't have room.")
    s.add(item, count)
    pile[item] -= count
    if not pile[item]:
        del pile[item]


def build(m, pid, key):
    """Put every material from the backpack that the project's current stage still needs."""
    s = m.people[pid]
    _at_camp(m, s)
    project = m.camp.project(key)
    if project.done():
        raise LobbyError(f"The {project.name.lower()} is finished.")
    useful = {item: min(count, project.missing(item)) for item, count in s.pack.items()}
    useful = {item: count for item, count in useful.items() if count}
    if not useful:
        raise LobbyError(f"You carry nothing the {project.name.lower()} needs right now.")
    s.spend(BUILD_COST)
    for item, count in useful.items():
        project.put(item, count)
        s.remove(item, count)
        s.stats["built"] += count
        if key == "raft" and item == "wood":
            s.stats["raftWood"] += count
    stage = project.stage()["name"]
    m.log(f"{m.names[pid]} built {', '.join(f'{n} {i}' for i, n in useful.items())} into the {stage}.")
    if project.full():
        if project.patched:
            finish_stage(m, project, pid)
        else:
            m.check = Check(key, pid)
            m.log(f"The {stage} is ready for a build check: {m.names[pid]} picks a helper.")


def finish_stage(m, project, pid):
    stage = project.stage()["name"]
    project.finish()
    m.people[pid].stats["stages"] += 1
    m.log(f"The {stage} is finished!")


def craft(m, pid, tool):
    s = m.people[pid]
    if tool in s.tools:
        raise LobbyError("You already have one.")
    cost = TOOLS[tool]["cost"]
    for item, count in cost.items():
        if not s.has(item, count):
            raise LobbyError(f"A {TOOLS[tool]['name']} needs " + ", ".join(f"{n} {i}" for i, n in cost.items()) + ".")
    s.spend(CRAFT_COST)
    for item, count in cost.items():
        s.remove(item, count)
    s.tools.add(tool)
    m.log(f"{m.names[pid]} crafted a {TOOLS[tool]['name']}.")


def eat(m, pid, source):
    s = m.people[pid]
    if not s.hunger:
        raise LobbyError("You aren't hungry.")
    if source == "camp":
        _at_camp(m, s)
        pile = m.island.pile(s.pos)
        if not pile.get("food"):
            raise LobbyError("There's no food in the stockpile.")
        pile["food"] -= 1
        if not pile["food"]:
            del pile["food"]
    else:
        s.remove("food")
    s.eat_hunger(EAT_HUNGER)
    m.log(f"{m.names[pid]} ate{' from the stockpile' if source == 'camp' else ''}.")


def heal(m, pid):
    s = m.people[pid]
    if not s.sick and not s.wounds:
        raise LobbyError("You're healthy.")
    s.remove("herbs")
    if s.sick:
        s.sick = False
        m.log(f"{m.names[pid]} used herbs and is no longer sick.")
    else:
        s.wounds -= 1
        m.log(f"{m.names[pid]} used herbs on a wound.")


def _other_here(m, pid, target):
    if target == pid:
        raise LobbyError("Pick someone else.")
    other = m.people.get(target)
    if other is None or target not in m.order:
        raise LobbyError("That player isn't in the game.")
    if other.pos != m.people[pid].pos:
        raise LobbyError("They need to be on your square.")
    return other


def give(m, pid, target, item):
    s = m.people[pid]
    other = _other_here(m, pid, target)
    if not s.has(item):
        raise LobbyError(f"You don't have any {item}.")
    if not other.space():
        raise LobbyError("Their backpack is full.")
    s.remove(item)
    other.add(item, 1)
    s.stats["given"] += 1
    m.log(f"{m.names[pid]} gave {m.names[target]} 1 {item}.")


def attack(m, pid, target, steal):
    s = m.people[pid]
    other = _other_here(m, pid, target)
    if steal is not None:
        if not other.has(steal):
            raise LobbyError(f"They don't have any {steal}.")
        if not s.space():
            raise LobbyError("Your backpack is full: you couldn't carry it off.")
    s.spend(ATTACK_COST)
    other.wounds += 1
    other.stats["woundsTaken"] += 1
    s.stats["attacks"].append(target)
    text = f"{m.names[pid]} attacked {m.names[target]}"
    if steal is not None:
        other.remove(steal)
        s.add(steal, 1)
        text += f" and took 1 {steal}"
    m.log(text + "!")


def launch(m, pid):
    s = m.people[pid]
    _at_camp(m, s)
    if not m.camp.raft_done():
        raise LobbyError("The raft isn't finished.")
    if m.launch_day is not None:
        raise LobbyError("The raft is already set to leave.")
    m.launch_day = min(m.day + 1, m.monsoon)
    when = "tonight" if m.launch_day == m.day else "at the end of tomorrow"
    m.log(f"{m.names[pid]} readied the raft: it leaves {when}. Be at camp!")
