"""Bastion 2: loading the content files (content/) when the game is imported, and their card text.

Fields are documented in content/README.md. Bad files are logged (logger "bastion2") and skipped;
references to missing cards are dropped with a log line.

    RESOURCES   {id: {"id", "name", "icon", "temporary"}} in file order (content/resources.json).
                Temporary ones (wood, stone...) are counters in the play area, cleared at the end of
                every turn. "food" and "population" are permanent and must be there.
    TEMPORARY   ids of the temporary resources
    COST_KEYS   what a cost may name: temporary resources, "food", "population" (available
                population this turn)
    GAIN_KEYS   what an effect may give: temporary resources and "food" (capped by food storage)
    ICONS       {resource id or "actions": icon}
    STRUCTURES  {id: {"id", "name", "icon", "text", "cost", "provides": {"food_cap", "actions"},
                      "on_build": {"population", "add": [{"card", "count", "optional"}]},
                      "action": effect or None, "market", "copies"}}
    CARDS       {id: card} from content/cards/ plus one card per structure (same id, kind
                "structure"). card = {"id", "name", "icon", "kind", "text", "market", "copies"} plus
                  resource:  "resource", "value"
                  upkeep:    "pay" {cost}, "discard" n (0: can't), "paid_off" (leaves the deck once
                             paid), "discarded" {"add": card id or "", "population": n, "remove"}
                  action:    effect fields
                  structure: "structure" (its id)
    effect      {"name", "actions" (action points it costs), "pay" {cost}, "gain" {gain},
                 "card" (a temporary card into your hand, or ""), "draw" n,
                 "bundle" [values] (trade resource cards of one kind adding up to a value for that
                 kind's card of that value)}
    STARTING_DECK  {"deck": {card id: copies}, "after_first_hand": {card id: copies}}
    MARKET_ALWAYS  card ids always for sale; MARKET_SHOP {card id: copies} in the shop deck
    resource_card(resource, value) -> card id or None (the bundle result)
    load(folder) -> (RESOURCES, STRUCTURES, CARDS, STARTING_DECK) (tests feed other folders)
"""

import logging
from pathlib import Path

from gamekit.data import flag, load_json, load_json_dir, text, whole

log = logging.getLogger("bastion2")

CONTENT = Path(__file__).resolve().parent.parent / "content"
PERMANENT = ("food", "population")
KINDS = ("resource", "upkeep", "action")
MARKETS = ("", "always", "shop")
MAX = 20


def _amounts(data, key, allowed):
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    out = {}
    for name, n in value.items():
        if name not in allowed:
            raise ValueError(f"{key}: unknown resource {name!r}")
        if type(n) is not int or not 0 <= n <= MAX:
            raise ValueError(f"{key}.{name} must be a whole number 0-{MAX}")
        if n:
            out[name] = n
    return out


def _card_id(data, key):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a card id")
    return value


class Loader:
    """One load of a content folder; the module-level names below come from load(CONTENT)."""

    def __init__(self, folder):
        self.resources = load_json(folder / "resources.json", self.parse_resources, log, default={}) or {}
        for name in PERMANENT:
            self.resources.setdefault(name, {"id": name, "name": name.title(), "icon": "", "temporary": False})
            self.resources[name]["temporary"] = False
        self.temporary = [r for r, info in self.resources.items() if info["temporary"]]
        self.cost_keys = self.temporary + list(PERMANENT)
        self.gain_keys = self.temporary + ["food"]
        self.structures = load_json_dir(folder / "structures", self.parse_structure, log)
        cards = load_json_dir(folder / "cards", self.parse_card, log)
        for sid, s in self.structures.items():
            if sid in cards:
                log.error("Card %s has the same id as a structure; the card is skipped", sid)
            cards[sid] = {"id": sid, "name": s["name"], "icon": s["icon"], "kind": "structure", "text": "",
                          "structure": sid, "market": s["market"], "copies": s["copies"]}
        self.cards = cards
        self.check_references()
        self.starting = load_json(folder / "starting-deck.json", self.parse_starting, log,
                                  default={"deck": {}, "after_first_hand": {}})

    # --- parsers ----------------------------------------------------------------------------

    def parse_resources(self, data):
        if not isinstance(data, dict):
            raise ValueError("resources.json must be an object")
        out = {}
        for rid, info in data.items():
            if not isinstance(info, dict) or not isinstance(rid, str) or not rid.isidentifier():
                raise ValueError(f"bad resource {rid!r}")
            out[rid] = {"id": rid, "name": text(info, "name", 30) or rid.title(), "icon": text(info, "icon", 8),
                        "temporary": flag(info, "temporary") and rid not in PERMANENT}
        return out

    def parse_effect(self, data, name=""):
        if not isinstance(data, dict):
            raise ValueError("an action must be an object")
        bundle = data.get("bundle", [])
        if not isinstance(bundle, list) or any(type(v) is not int or not 2 <= v <= MAX for v in bundle):
            raise ValueError("bundle must be a list of values 2-20")
        return {"name": text(data, "name", 30) or name, "actions": whole(data, "actions", 0, 5, default=1),
                "pay": _amounts(data, "pay", self.cost_keys), "gain": _amounts(data, "gain", self.gain_keys),
                "card": _card_id(data, "card"), "draw": whole(data, "draw", 0, 10, default=0),
                "bundle": sorted(set(bundle))}

    def parse_market(self, data, out):
        market = data.get("market", "")
        if market not in MARKETS:
            raise ValueError(f"market must be one of {MARKETS}")
        out["market"] = market
        out["copies"] = whole(data, "copies", 1, 20, default=1)

    def parse_structure(self, sid, data):
        provides = data.get("provides", {})
        on_build = data.get("on_build", {})
        if not isinstance(provides, dict) or not isinstance(on_build, dict):
            raise ValueError("provides and on_build must be objects")
        adds = on_build.get("add", [])
        if not isinstance(adds, list) or not all(isinstance(a, dict) for a in adds):
            raise ValueError("on_build.add must be a list of objects")
        out = {
            "id": sid, "name": text(data, "name", 30, required=True), "icon": text(data, "icon", 8) or "🏠",
            "text": text(data, "text", 300), "cost": _amounts(data, "cost", self.cost_keys),
            "provides": {"food_cap": whole(provides, "food_cap", 0, 50, default=0),
                         "actions": whole(provides, "actions", 0, 5, default=0)},
            "on_build": {"population": whole(on_build, "population", 0, 10, default=0),
                         "add": [{"card": _card_id(a, "card"), "count": whole(a, "count", 1, 5, default=1),
                                  "optional": flag(a, "optional")} for a in adds]},
            "action": self.parse_effect(data["action"]) if "action" in data else None,
        }
        self.parse_market(data, out)
        return out

    def parse_card(self, cid, data):
        kind = data.get("kind", "action")
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        out = {"id": cid, "name": text(data, "name", 30, required=True), "icon": text(data, "icon", 8),
               "kind": kind, "text": text(data, "text", 300)}
        if kind == "resource":
            resource = data.get("resource")
            if resource not in self.gain_keys:
                raise ValueError(f"resource must be one of {self.gain_keys}")
            out |= {"resource": resource, "value": whole(data, "value", 1, MAX, default=1)}
        elif kind == "upkeep":
            discarded = data.get("discarded", {})
            if not isinstance(discarded, dict):
                raise ValueError("discarded must be an object")
            out |= {"pay": _amounts(data, "pay", self.cost_keys), "discard": whole(data, "discard", 0, 10, default=0),
                    "paid_off": flag(data, "paid_off"),
                    "discarded": {"add": _card_id(discarded, "add"),
                                  "population": whole(discarded, "population", -5, 0, default=0),
                                  "remove": flag(discarded, "remove")}}
        else:
            out |= self.parse_effect(data, out["name"])
            out["name"] = text(data, "name", 30, required=True)
        self.parse_market(data, out)
        return out

    def parse_starting(self, data):
        def counts(key):
            value = data.get(key, {})
            if not isinstance(value, dict):
                raise ValueError(f"{key} must be an object")
            out = {}
            for cid, n in value.items():
                if cid not in self.cards:
                    log.error("starting-deck.json: unknown card %s", cid)
                elif type(n) is int and 0 < n <= MAX:
                    out[cid] = n
            return out
        return {"deck": counts("deck"), "after_first_hand": counts("after_first_hand")}

    # --- cross-references -----------------------------------------------------------------------

    def check_references(self):
        def known(cid, where):
            if cid and cid not in self.cards:
                log.error("%s: unknown card %s (ignored)", where, cid)
                return False
            return True

        for sid, s in self.structures.items():
            s["on_build"]["add"] = [a for a in s["on_build"]["add"] if a["card"] and known(a["card"], sid)]
            if s["action"] and not known(s["action"]["card"], sid):
                s["action"]["card"] = ""
        for cid, c in self.cards.items():
            if c["kind"] == "action" and not known(c["card"], cid):
                c["card"] = ""
            if c["kind"] == "upkeep" and not known(c["discarded"]["add"], cid):
                c["discarded"]["add"] = ""


def load(folder):
    loaded = Loader(folder)
    return loaded.resources, loaded.structures, loaded.cards, loaded.starting


RESOURCES, STRUCTURES, CARDS, STARTING_DECK = load(CONTENT)
TEMPORARY = [r for r, info in RESOURCES.items() if info["temporary"]]
COST_KEYS = TEMPORARY + list(PERMANENT)
GAIN_KEYS = TEMPORARY + ["food"]
ICONS = {**{r: info["icon"] for r, info in RESOURCES.items()}, "actions": "⚡"}
MARKET_ALWAYS = [cid for cid, c in CARDS.items() if c["market"] == "always"]
MARKET_SHOP = {cid: c["copies"] for cid, c in CARDS.items() if c["market"] == "shop"}


def resource_card(resource, value):
    """The resource card of that kind and value (bundling), or None."""
    for cid, card in CARDS.items():
        if card["kind"] == "resource" and card["resource"] == resource and card["value"] == value:
            return cid
    return None


# --- card text --------------------------------------------------------------------------------

def amounts(cost):
    return " ".join(f"{n}{ICONS.get(k, k)}" for k, n in cost.items())


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def effect_text(effect):
    parts = []
    if effect["pay"] and effect["gain"]:
        parts.append(f"turn {amounts(effect['pay'])} into {amounts(effect['gain'])}")
    elif effect["pay"]:
        parts.append(f"pay {amounts(effect['pay'])}")
    elif effect["gain"]:
        parts.append(f"gain {amounts(effect['gain'])}")
    if effect["card"]:
        parts.append(f"take a {CARDS[effect['card']]['name']} into your hand (gone once used)")
    if effect["draw"]:
        parts.append(f"draw {plural(effect['draw'], 'card')}")
    if effect["bundle"]:
        values = " or ".join(str(v) for v in effect["bundle"])
        parts.append(f"bundle resource cards of one kind worth {values} into one card of that value")
    cost = "Free" if not effect["actions"] else plural(effect["actions"], "action")
    return f"{cost}: {', '.join(parts) or 'nothing'}."


def card_text(card):
    if card["text"]:
        return card["text"]
    kind = card["kind"]
    if kind == "resource":
        if card["resource"] == "food":
            return f"Play: +{card['value']}{ICONS['food']} (kept, up to your food storage)."
        return f"Play: +{card['value']}{ICONS[card['resource']]} this turn."
    if kind == "upkeep":
        ways = []
        if card["pay"]:
            ways.append(f"pay {amounts(card['pay'])}")
        if card["discard"]:
            ways.append(f"discard {plural(card['discard'], 'other card')}")
        out = f"Play: {' or '.join(ways) or 'nothing'}."
        if card["paid_off"]:
            out += " Then it leaves your deck."
        hit = card["discarded"]
        harm = []
        if hit["add"]:
            harm.append(f"add a {CARDS[hit['add']]['name']} to your deck")
        if hit["population"]:
            harm.append(f"lose {-hit['population']}{ICONS['population']} and a Villager")
        if hit["remove"]:
            harm.append("it leaves your deck")
        if harm:
            out += f" If discarded unplayed: {' and '.join(harm)}."
        return out
    if kind == "structure":
        return structure_text(STRUCTURES[card["structure"]])
    return effect_text(card)


def structure_text(s):
    if s["text"]:
        return s["text"]
    parts = [f"Build: {amounts(s['cost']) or 'free'}, next to your buildings."]
    built = []
    if s["on_build"]["population"]:
        built.append(f"+{s['on_build']['population']}{ICONS['population']}")
    for a in s["on_build"]["add"]:
        name = CARDS[a["card"]]["name"]
        what = f"{a['count']} {name}s" if a["count"] > 1 else f"a {name}"
        built.append(f"{'you may add' if a['optional'] else 'add'} {what} to your discard")
    if built:
        parts.append(f"When built: {', '.join(built)}.")
    if s["provides"]["food_cap"]:
        parts.append(f"Food storage +{s['provides']['food_cap']}.")
    if s["provides"]["actions"]:
        parts.append(f"+{plural(s['provides']['actions'], 'action')} every turn.")
    if s["action"]:
        parts.append(f"{s['action']['name']} (once a turn) — {effect_text(s['action'])}")
    return " ".join(parts)
