"""Smugglers: inspections. Whenever a loaded ship is on a spot where Interpol has a piece
(a patrol or a checkpoint), it's inspected: a ship flying in stops there; Interpol moving or
placing a piece onto ships inspects each loaded one; loading cargo on such a spot does too.
Empty ships are never inspected (there's nothing to search).

check(m, ship_ids) queues those ships; they're inspected one at a time (m.inspection_queue),
each a stage inside play, in two steps, while the turn itself stays where it was:
    1. "bribe":  the ship's owner offers a bribe (0 up to their credits).
    2. "decide": Interpol lets the ship pass (and takes the bribe) or inspects it.
Inspecting: every card that isn't the ship's declared good is seized (illegal goods never
match). The owner pays m.legal_fine per seized legal good plus each seized illegal good's
penalty (never going below 0 credits). Interpol scores the bribe, or the seized goods' value
plus the fine actually paid. A ship left with no cargo loses its contract token, which goes
back to the contract's source planet.

    presence(m, ship)            "checkpoint" / "patrol" if a loaded ship is on one, else None
    check(m, ship_ids)           queue inspections for those of the ships on Interpol's spots
    next_inspection(m)           start the next queued one, if none is running
    start(m, ship_id, by)        by: "checkpoint" or "patrol"
    bribe(m, pid, amount)
    decide(m, pid, search)       search: True = inspect, False = let it pass
    cancel(m)                    the owner left the game (then call next_inspection)
    m.inspection                 None or {"ship", "owner", "by", "stage", "bribe"?}
"""

from gamekit import LobbyError


def presence(m, ship):
    if not ship["cargo"]:
        return None
    for kind in ("checkpoint", "patrol"):
        if ship["at"] in m.interpol.nodes(kind):
            return kind
    return None


def check(m, ship_ids):
    for sid in ship_ids:
        busy = m.inspection is not None and m.inspection["ship"] == sid
        if not busy and sid not in m.inspection_queue and presence(m, m.ships[sid]):
            m.inspection_queue.append(sid)
    next_inspection(m)


def next_inspection(m):
    while m.inspection is None and m.inspection_queue:
        ship = m.ships.get(m.inspection_queue.pop(0))
        by = ship and presence(m, ship)  # still loaded and still there?
        if by:
            owner = ship["owner"]
            m.add_log(owner, f"Interpol's {by} stops {m.names[owner]}'s {ship['name']} at "
                             f"{m.label(ship['at'])} for inspection.")
            start(m, ship["id"], by)


def start(m, ship_id, by):
    ship = m.ships[ship_id]
    m.inspection = {"ship": ship_id, "owner": ship["owner"], "by": by, "stage": "bribe"}


def bribe(m, pid, amount):
    current = m.inspection
    if current is None or current["stage"] != "bribe" or current["owner"] != pid:
        raise LobbyError("You can't offer a bribe now.")
    if not 0 <= amount <= m.smugglers[pid]["credits"]:
        raise LobbyError(f"You can offer 0 to {m.smugglers[pid]['credits']} credits.")
    current["bribe"] = amount
    current["stage"] = "decide"
    ship = m.ships[current["ship"]]
    offer = f"offers a bribe of {amount} credits" if amount else "offers no bribe"
    m.add_log(pid, f"{m.names[pid]} {offer} for {ship['name']}.")


def decide(m, pid, search):
    current = m.inspection
    if current is None or current["stage"] != "decide" or pid != m.interpol.pid:
        raise LobbyError("There's nothing to decide now.")
    ship = m.ships[current["ship"]]
    owner = current["owner"]
    smuggler = m.smugglers[owner]
    m.inspection = None
    if not search:
        amount = current.get("bribe", 0)
        smuggler["credits"] -= amount
        m.interpol.score += amount
        m.add_log(pid, f"Interpol let {ship['name']} pass" + (f" and took {amount} credits." if amount else "."))
        return
    declared = ship["declared"]
    kept = [card for card in ship["cargo"] if card["card"] == declared]
    seized = [card for card in ship["cargo"] if card["card"] != declared]
    defs = m.goods_defs
    fine = sum(m.legal_fine if defs[c["card"]]["legal"] else defs[c["card"]]["penalty"] for c in seized)
    paid = min(fine, smuggler["credits"])
    smuggler["credits"] -= paid
    m.interpol.score += paid + sum(defs[c["card"]]["value"] for c in seized)
    m.goods.discard(seized)
    ship["cargo"] = kept
    names = [c["card"] for c in seized]
    if not seized:
        m.add_log(pid, f"Interpol inspected {ship['name']}: all {len(kept)} goods were "
                       f"{defs[declared]['name']}, as declared.")
        return
    lost = ""
    if not kept:
        cid = ship["contract"]
        m.holder.pop(cid, None)
        m.clear_cargo(ship)
        lost = f" The cargo token for #{m.number(cid)} goes back to {m.label(m.contracts[cid]['from'])}."
    m.add_log(pid, f"Interpol inspected {ship['name']} and seized {len(seized)} goods; "
                   f"{m.names[owner]} paid a {paid} credit fine.{lost}", cards=names)


def cancel(m):
    m.inspection = None
