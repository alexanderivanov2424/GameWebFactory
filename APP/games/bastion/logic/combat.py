"""Bastion: fighting enemies: soldier strikes, razing enemy tiles, units fighting, damage, cures.

Enemies with defeat.soldiers take 1 damage per that many soldiers. A fighting unit counts as 1
soldier: each one resolved adds a strike to the enemy (foe.strikes), and every defeat.soldiers
strikes deal 1 damage; leftover strikes carry over on that enemy, and the soldier counter's
Strike uses them up first. Enemy tiles work the same way: a blight takes 1 (a lair tile
foe.raze) soldiers or unit strikes to raze (blight["strikes"] carries over). Razing a lair tile
deals 1 damage. A beaten enemy's blights and plague go; beating every enemy wins. Units placed on
an enemy or tile that is gone are dropped (Match.clear_gone).

    active_foe(match, index) -> Foe (LobbyError unless it's active)
    strike(match, pid, index, way, times=1)   soldier counter ("soldiers") or resources ("resources")
    raze(match, pid, x, y)          spend soldiers to raze an enemy tile
    unit_fight(match, seat, foe) -> log text      one fighting unit resolves
    unit_raze(match, seat, cell) -> log text      one unit on an enemy tile resolves
    raze_cost(match, blight) -> strikes it takes in all
    hurt(match, foe, amount)        damage; a beaten enemy's tiles and plague go; all beaten wins
    cure(match, structure) -> text  lift its plague (hurts a foe with defeat.cure)
"""

from gamekit import LobbyError


def active_foe(match, index):
    if not 0 <= index < len(match.foes) or not match.foes[index].active:
        raise LobbyError("That enemy isn't here.")
    return match.foes[index]


def strike(match, pid, index, way, times=1):
    seat = match.acting(pid)
    foe = active_foe(match, index)
    times = min(times, foe.hp)
    if way == "soldiers" and foe.fightable:
        need = max(0, foe.defeat["soldiers"] * times - foe.strikes)
        if match.soldiers < need:
            raise LobbyError(f"That takes {need} soldiers; you have {match.soldiers}.")
        match.soldiers -= need
        foe.strikes = 0
    elif way == "resources" and foe.defeat.get("resources"):
        match.pay({k: n * times for k, n in foe.defeat["resources"].items()}, "That")
    else:
        raise LobbyError(f"The {foe.name} can't be hurt that way.")
    match.write(f"{seat.name} hit the {foe.name} for {times}.", pid)
    hurt(match, foe, times)


def raze_cost(match, blight):
    return match.foes[blight["foe"]].raze if blight["lair"] else 1


def razed(match, cell, blight):
    match.board.remove_blight(cell)
    if blight["lair"]:
        hurt(match, match.foes[blight["foe"]], 1)
    match.clear_gone()


def raze(match, pid, x, y):
    seat = match.acting(pid)
    blight = match.board.blights.get((x, y))
    if not blight:
        raise LobbyError("There's no enemy tile there.")
    cost = raze_cost(match, blight) - blight["strikes"]
    if match.soldiers < cost:
        raise LobbyError(f"Razing that takes {cost} soldier{'s' if cost > 1 else ''}; you have {match.soldiers}.")
    match.soldiers -= cost
    match.write(f"{seat.name} razed a {blight['name']}.", pid)
    razed(match, (x, y), blight)


def unit_fight(match, seat, foe):
    foe.strikes += 1
    per = foe.defeat["soldiers"]
    if foe.strikes < per:
        return f"struck the {foe.name} ({foe.strikes} of {per} toward the next damage)"
    foe.strikes -= per
    hurt(match, foe, 1)
    return f"hit the {foe.name} for 1"


def unit_raze(match, seat, cell):
    blight = match.board.blights[cell]
    blight["strikes"] += 1
    match.board.version += 1
    cost = raze_cost(match, blight)
    if blight["strikes"] < cost:
        return f"struck the {blight['name']} ({blight['strikes']} of {cost} toward razing it)"
    razed(match, cell, blight)
    return f"razed a {blight['name']}"


def hurt(match, foe, amount):
    if not foe.hit(amount):
        return
    for cell in [c for c, b in match.board.blights.items() if b["foe"] == foe.index]:
        match.board.remove_blight(cell)
    for s in match.board.structures.values():
        if s.plague == foe.index:
            s.plague = None
    foe.strikes = 0
    match.board.version += 1
    match.write(f"{foe.enemy['icon']} The {foe.name} is beaten!")
    match.clear_gone()
    if all(f.state == "defeated" for f in match.foes):
        match.end(True, "Every enemy is beaten: the city stands!")


def cure(match, s):
    foe = match.foes[s.plague]
    s.plague = None
    match.board.version += 1
    if foe.defeat.get("cure"):
        hurt(match, foe, 1)
    return f"cured the {s.spec['name']}"
