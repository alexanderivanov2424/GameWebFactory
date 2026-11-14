The user's spec for Bastion 2 (2026-11-10), kept verbatim:

Make a new version of Bastion game called Bastion 2. For this version, keep enemies hidden (its a work in progress) and remove unit placement. Instead the game will work like this:

Players start the game by placing a castle, a house, and a farm. In general structures will be build from the shop using resources. Resources are added to the players hand. Players draw 5 cards each turn (dominion style) and can spend the resources in their hand to build structures. Some structures are always available to build, others can only be built when they are available in the shop.

when building structures, they must be adjacent to structures already placed by the current player. When placing, change the highlight of squares where placement is allowed (slow pulsing).

Permanent resources are population, food

Starting deck will be 2 villager, 3 wheat, 3 stone, 4 wood, 1 king. Villagers are added to the deck after the starting hand is dealt.

Wheat can be played to gain 1 food. There is a food maximum which is 5 (given by castle)
Villager can be played for one food or by discarding two cards (does nothing). If a villager is decarded, add Hunger to the deck.
Hunger can be played for 2 food or by discarding three cards. If discarded, add starvation to the deck.
Starvation can be played for 3 food. If discarded, remove 1 population. When population is removed, a villager card is also removed from the player deck.

Structures to purchase are available in the market. When players buy a structure, that card is added to their discard.
When a player draws a structure, they can build it for the resources in their hand. Players should have a play area under the map where they can put down resource cards to increment little resource counters in the top right of the play area. They can then play cards that cost resources decrementing these resource counts. These are different from the permanent resources.
Buildings also take population to build. Available population for any given turn should be displayed as X / total in the permanent population resource.

Assuming the player was able to successfully play the bluilding and pay its costs/ population cost. It is built at the end of the turn.
Buildings can add a card to the players deck, instantly added to the discard. They can also give resource conversion options (temporary -> temp, temp -> perm, or perm to perm). They can also give actions that do other things
Actions given by structures should be shown in a list on the left. Each structure can only be used once per turn and if the player still has actions available.
Buying a card costs an action, players start with 1 action per turn (given by castle). Show the actions available as a big number in a circle to the left of cards in hand

Farm - Costs 2 wood, 1 pop. When built, you may add a wheat to your discard.
Hut - Costs 1 wood and 1 stone 1 pop, when built increases population by 1 and add a villager to discard
House - Costs 2 wood and 1 stone 2 pop, when built increases population by 2 and add 2 villagers to discard
Storage Yard - costs 1 wood and 3 pop, when built players get a 1 cost action to "bundle" Discard resource cards with combined value 3 to take a value 3 resource card. Or value 5 to take a value 5 resource card.
Quary - cost 2 wood, 1 pop. When built add a value 3 stone to your deck. Adds a free action to add 1 stone to your hand.
Lumber mill - cost 2 wood, 1 pop. When build adds a value 3 wood to your deck. Adds a free action to add 1 wood to your hand.

King - draw 2 cards, costs 1 action

At the end of a turn, players may keep any number of cards. Temporary resources are cleared. Population returns to the available population.

Design the game so that all the UI is tied to the player hud arount the perimiter and the map is a floating infinite grid in the middle. Prevent players from panning too far to the sides, fill the space outside the map with empty background color.

Set this up so that more structures and cards can be added in the future
