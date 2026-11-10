"""Bastion: the game's rules, kept apart from the lobby (server.py).

Modules:
    match.py       Match: one game's flow (setup, then rounds: place -> resolve -> plan -> end of
                   round with income and upkeep), the market, leaving; thin wrappers over the
                   modules below. Endless: enemies are switched off.
    setup.py       The setup phase: players in turn place their keep, a house and a farm.
    units.py       Units (worker placement): what a unit does on a tile (job), where you may place
                   (within REACH of your buildings and roads, one unit per tile), placing / taking
                   back, stationed units, starving.
    resolution.py  When everyone is ready: automatic jobs at once (build tokens, gathering,
                   producing, training soldiers), then each player's prompts one by one (convert,
                   pick an output, road or scavenge).
    playing.py     Playing a hand card: blueprints plan structures (greyed out with build tokens),
                   actions (gain, draw, adds, Orders' recall, Trade's gift), curses paid off.
    views.py       What clients see: public state (with the cached catalog), private hand, unit
                   targets, setup spots, card targets and the current prompt.
    board.py       Board + Structure: terrain, owned one-tile structures and roads, placement
                   checks, "next to" counts, each player's reach.
    seat.py        Seat: one player's resources, units, soldiers, decrees, deck, hand, ready flag
                   and prompts.
    market.py      Market: one half of the shared market (blueprints or actions), persistent,
                   reshuffled for gold once per round per player.
    structures.py  STRUCTURES loader (content/structures/), resources, terrain, condition text.
    cards.py       CARDS (content/cards/ + a blueprint per structure with a price) and
                   STARTING_DECK (content/starting-deck.json), card text.
    maps.py        MAPS loader (content/maps/): terrain rows.
  Dormant (enemies are switched off; nothing imports these from Match, and they still expect the
  old shared stockpile, match.keep and match.soldiers, so they need rewiring before enemies come back):
    foes.py        The enemies of one game: lineup, health scaling, arrival (lairs), damage, strikes.
    attacks.py     What an enemy attack does (steal, loot, ruin, keep damage, blights, curses,
                   plague, freeze, kill soldiers).
    combat.py      Soldier strikes, razing enemy tiles, units fighting, damage, cures.
    enemies.py     ENEMIES loader (content/enemies/), attack and defeat text.

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests can drive it directly (see tests/). It may import
gamekit, never `server`. Import sibling modules relatively.
"""
