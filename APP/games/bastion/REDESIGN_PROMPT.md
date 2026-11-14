Complete Bastion Game Redesign:
- remove enemies, keep all the logic for them but just make them not happen and remove that UI. the game will go forrever thats okay, this is for testing.
- Each player will managet their own city and the focus will be on cooperative trading

At the start of the game, players take turns placing their castle (1x1), 1 house (1x1), and 1 farm (1x1). Each player has their own resources
The keep gives the player 1 unit and the house 2 units. Each unit consumes 1 food each round. Units that are not fed are lost.
Each round, the keep produces 1 food and 1 gold (so the last unit is never lost).

First is the unit placement phase, each player can allocate units to any structure in their city or to "building". Structures are first added to the map "greyed out" with X build tokens on them. Each building unit assigned to that structure removes a building unit. Once all are removed the structure is built and goes into effect. For structures that are already build, players may choose to perform the action of that structure. Structures that produce resources happen automatically just happen. Structures that convert resources prompt. Units can only be allocated within 3 tiles of a players existing structure.

How does this look? During unit placement, players click on tiles on the map to allocate units to those structures/locations. On the tile, a little person icon is added and increments. On the right, the top panel is details about the current structure (hovered) and below that the list of players. For each player show their resource bar, and a button to view their deck as a pop up. For now, only 1 unit can be allocated to a given tile. Units can also be allocated to houses (does nothing for now). Units can be allocated to forest or mountain to gather 1 wood / stone. The done button is on the right below the player board.

After unit placement phase is unit resolution. Things that resolve automatically resolve instantly. For the rest, the player is prompted one by one if they want the unit to perform the action (Do you want to spend X to make Y?). The prompt should be on the right in a section below details but above the player list. Units allocated to tiles without structures can build roads on those tiles. Prompt for building roads, the other option is to scavage for resources where a dice is rolled (1/3 nothing, 1/3 for 1 wood, 1/3 for 1 stone). Units that are assigned to temporary jobs like building a structure (or a road) return to the pool imediately. Other units stay on their assigned structures meaning that players may not be able to do anything during unit placement in some cases (this is fine).

After unit resolution is the planning phase. Players play cards to lay the plans for their city. Players start each phase with 3 royal decrees (energy like resource) which is given to them by their castle. Cards that they play may spend a decree and/or other resources. They can also buy cards from the market (below the board maybe?). This phase, like the other two phases happens for all players at the same time.

Remove all the cards from the market that are there currently. The market should have two halves, blueprints and actions. Each market persists between rounds but players can pay 1 gold to reshuffle it once per round. Make each card spend 1 decree for now, this will change later.

Have only the following cards:
Blueprints:
Farm: 1 decree, 1 wood, 1 build turn - produces food when worked
House: 1 decree, 1 stone, 1 build turn - adds 2 units to the unit pool
Lumber Mill: 1 decree, 2 wood and 1 stone, 1 build - produce 3 wood when worked (placed adjacent to forest)
Quarry: 1 decree, 2 wood and 1 stone, 1 build - produces 3 stone when worked (can be placed anywhere)
Mine: 1 decree, 3 wood and 1 stone, 2 build - produces 1 metal or 3 stone when worked  - pick (placed next to mountain)
Workshop: 1 decree, 1 wood and 1 stone, 1 build - convert 3 wood into 1 tool (there will be multiple things the workshop can build in the future)
Barracks: 1 decree, 2 stone, 1 build - units placed here are converted into soldiers. Soldiers are another kind of unit that is placed during unit placement but is forever split from the regular unit pool. It always returns to pool at the end of a round.
Tower: 1 decree, 3 wood 1 stone, 2 build - soldiers placed here "attack at range" for now don't implenent any logic for this, have it do nothing.

Action Cards:
Tax card gives 1 gold but adds unrest to the deck. Spends a decree
Orders - unassign one unit from a building and return it to the pool (it has already done its work for this turn, this is just for next turn)
Trade - give another player 3 different resources or 2 of the same resource.


The starting player hand should have tax, 2 orders, 1 trade

Do not update the bots for this refactor. Just disable them for now. Save this entire prompt as is to a file and check that each item was completed at the end via a review sub agent.
