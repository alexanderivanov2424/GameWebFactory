"""Metro Lanes weekly rewards: the road delivery everyone gets and the two upgrades to pick from.

At the start of every week each player gets WEEKLY (same for all) and the game pauses while
everyone picks one of the same two offers (drawn at random from UPGRADES). Each player picks for
themselves; whoever hasn't picked when the pick timer runs out gets the first offer.
"""

WEEKLY = {"roads": 5}

UPGRADES = {
    "roads": {"name": "+5 roads", "text": "Five more road tiles.", "gives": {"roads": 5}},
    "bridge": {"name": "Bridge", "text": "Cross up to 4 water tiles in a straight line.", "gives": {"bridges": 1}},
    "tunnel": {"name": "Tunnel", "text": "Dig straight through a mountain, however wide.", "gives": {"tunnels": 1}},
    "roundabout": {"name": "Roundabout", "text": "A junction that lets 4 cars through at once at full speed.",
                   "gives": {"roundabouts": 1}},
    "lights": {"name": "2 traffic lights", "text": "A junction that lets 2 cars through at once, one direction at a time.",
               "gives": {"lights": 2}},
}


def offers(rng):
    """Two different upgrade ids for this week."""
    return rng.sample(sorted(UPGRADES), 2)


def give(player, gives):
    for item, n in gives.items():
        player.refund(item, n)
