/*
 * Hex Realms: every explanation players read, in one place: the rules, help and hint text, tooltips,
 * action descriptions and the descriptions of structures, units and advances (by content id).
 * Short labels (button names, stat names) stay in the code. Numbers come from the state, so text
 * that shows one is a function. Load before the other game scripts.
 */
window.HexText = {
  // Lobby "How to play": [heading, html] sections.
  rules: [
    ["Turns", `Everyone plans at the same time, in secret: place structures inside your territory, train units, order
      moves and attacks, research advances, then press <b>End turn</b>. When all players are done (or the timer runs
      out) every order resolves together. The last realm standing wins; if several survive to the turn limit, the
      highest score wins. Lose every Town Hall and you are out. The host can add bots in the settings.`],
    ["People and food", `Structures work while they have their workers (people). Food can't be stored: each turn,
      everyone eats 1 food and every unit eats its upkeep from that turn's production. Food left over becomes new people
      at once, as many as it feeds, while there's housing (units use housing too); the rest is lost. When production
      falls short, whoever can't be fed dies: idle people first, then units (newest first), then people at work. The food number at the top is what's left after everyone eats (below 0: someone starves).`],
    ["Goods", `Gold goes straight to your realm; wood, stone and metal go into your stores (Town
      Halls, Storage Yards). Faith and science aren't collected each turn: you have what your working structures give
      right now, minus what you've spent on advances (it can drop below 0 if structures stop; nothing else happens). What doesn't fit at the end of the turn is lost. A Market or Trading Hall can
      trade every turn: select it and <b>Enable trade</b>.`],
    ["Building", `Structures cost <b>hammers</b> 🔨: every person without a job builds 1 🔨 a turn, oldest site first.
      Placing a structure takes builders from your idle people at once (cancel to get them back). Switch structures off
      (or all at once with <b>Jobs off</b>) or demolish them to free people. Nothing is built where an enemy unit stands,
      and a site with an enemy unit on it gets no work.`],
    ["Land", `You build anywhere in your territory. Every Town Hall gives free land 2 cells around it: first come, first
      served, and cells two realms reach in the same turn go to nobody. To grow further, select a Town Hall and
      <b>Extend territory</b>: gold buys an explored cell next to your land, at once, for 1 gold a turn. Bought land is
      lost to an enemy unit on or next to it, when it's cut off from your Town Halls' land, or to another realm's Town
      Hall; unpaid cells are given up, farthest first.`],
    ["Units", `Units fight with dice wherever they meet: each die of 4 or more hits (5 or more against a unit in forest,
      hills or mountains, or on its own structure). Your own units pass through each other. Standing orders last until
      you give another: <b>Explore</b>, <b>Fight</b>, <b>Pillage</b>, or click a cell beyond a unit's reach to walk there
      over several turns. Units with orders are greyed out. New units appear on the structure that trains them.`],
    ["Controls", `Click a cell again to cycle through what's on it. Click a resource on the top bar for its
      <b>resource view</b>: what makes it (green) and what uses it (red) each turn. <b>Tech tree</b> shows the science
      and faith advances. After each turn a replay shows the fights you saw, one at a time: <b>Next</b> (or Enter) moves on,
      Esc skips the rest; Settings → Hex Realms sets its speed.`],
  ],

  structures: {
    barracks: "Trains infantry. Units on or next to it heal fully.",
    butcher: "Makes more food for each Hut or House next to it.",
    chapel: "Makes faith for each Hut or House next to it.",
    docks: "Built on water.",
    granary: "Every food structure next to it makes 2 more of what it makes.",
    house: "Housing.",
    hut: "Cheap housing.",
    lumbermill: "Makes 1 wood for each forest cell next to it with nothing built on it.",
    market: "Makes more gold for each Hut or House next to it. Can trade every turn.",
    mine: "Stone and metal from hills or mountains.",
    monument: "Worth a lot of score.",
    quarry: "Stone from hills. Cheaper and quicker to build than a Mine, but no metal.",
    shipyard: "Builds galleys.",
    smithy: "Makes metal. Builds catapults; swordsmen and knights need one too.",
    stable: "Trains knights.",
    storage_yard: "Stores wood, stone and metal. Every industrial structure next to it makes 1 more of what it makes.",
    tower: "Shoots the nearest enemy unit in range after movement.",
    town_hall: "Heart of a city: stores goods, gives free land around it, and is where you extend your territory. Lose every Town Hall and you are out.",
    trading_hall: "Trades at a better rate than a Market.",
    wall: "Blocks enemy units until knocked down.",
    windmill: "Makes nothing itself: every Farm next to it makes 2 more food while the Windmill works.",
  },
  units: {
    archer: "Shoots instead of moving; the target can't hit back.",
    catapult: "Hits structures hard.",
    galley: "Moves on water. Attacks units and structures on the shore.",
    scout: "Your starting explorer: fast, but it can't fight. Uses no people and eats nothing.",
    settlers: "Founds a new Town Hall where it stands, away from other cities. The new city starts with 2 people.",
    spearman: "Extra dice against mounted units.",
  },
  advances: {
    academics: "Universities.",
    archery: "Archers.",
    bronze_working: "Smithy and swordsmen.",
    divine_right: "More housing in every Hut and House.",
    engineering: "Catapults; towers roll 1 more die.",
    harvest_rites: "Every Farm makes more food.",
    holy_warriors: "Units defending in your territory roll 1 more die.",
    horsemanship: "Stables and knights.",
    masonry: "Walls and towers.",
    pilgrimage: "Every working Chapel makes gold.",
    sailing: "Docks, shipyards and galleys.",
    trade: "Trading halls.",
    zeal: "All units roll 1 more die when attacking.",
  },

  trade: {
    help: (rate) => `Every turn this structure gives ${rate} of one resource for 1 of another, while it works and you can afford it.`,
    on: "Trades this turn.",
    off: "Not this turn: it isn't working or you can't afford it.",
  },
  // Unit panel: actions (title = tooltip, desc = the line beside the button), standing and pending orders.
  unit: {
    empty: "Click one of your units or structures to command it, or any enemy to inspect it.",
    hold: { title: "Roll one extra defence die this turn instead of moving.", desc: "Stay put this turn and defend with +1 die." },
    explore: { title: "Walk around on its own every turn to clear the fog, until you give it another order.", desc: "Every turn: walk into the fog on its own." },
    fight: { title: "Every turn, attack the nearest enemy unit you can see (hold when there's none), until you give it another order.",
      desc: "Every turn: attack the nearest enemy unit in sight." },
    pillage: { title: "Every turn, attack the nearest enemy structure you can see, but fight enemy units that come close first (hold when there's nothing), until you give it another order.",
      desc: "Every turn: attack the nearest enemy structure in sight." },
    shoot: { title: (range) => `Shoot a unit or structure up to ${range} cells away.`, desc: (range) => `Pick a target up to ${range} cells away instead of moving.` },
    found: { title: "Found a Town Hall here.", desc: "Build a Town Hall where it stands.", none: "Can't found a city here." },
    clear: { desc: "Cancel this unit's orders (it stays put)." },
    disband: { desc: "Remove the unit; its people come home.", confirm: (name) => `Disband this ${name}?` },
    standing: {
      explore: "Exploring (walks on its own each turn)",
      fight: "Fighting (attacks the nearest enemy unit it sees; holds when none)",
      pillage: "Pillaging (attacks the nearest enemy structure it sees, fighting enemy units that come close first; holds when none)",
      travel: (goal) => `Travelling to ${goal} over several turns`,
      note: (text) => `${text}; any other order stops it`,
    },
    pending: { moving: (to) => `Moving to ${to}`, shooting: (at) => `Shooting at ${at}`, founding: "Founding a city", holding: "Holding position" },
    idle: "No orders",
    stats: { attack: "Attack: dice it rolls when it attacks", defense: "Defence: dice it rolls when attacked", move: "Movement: steps a turn", hp: "Health",
      range: "Range: shoots this far instead of moving", siege: "Siege: damage per hit on structures", food: "Food it eats each turn (from this turn's food production)" },
  },
  // Structure and construction-site panels.
  structure: {
    working: "Working.",
    off: "Switched off.",
    noWorkers: "Not working: no free workers.",
    switchTitle: "Switched-off structures don't use workers.",
    demolishTitle: "Remove it now (no refund).",
    demolishConfirm: (name) => `Demolish this ${name}? No refund, and goods stored in it are lost.`,
    siteHelp: "Each idle person (no job) builds 1 🔨 a turn, oldest site first. Switch structures off to free people.",
    siteDemolish: "Take the site down and get its cost back.",
    resTitle: "What it makes (+) and uses (−) a turn while it works; 👥 = the people working in it. In brackets: the base amounts; green / red = more / less than the base here.",
    // Bullets for neighbour bonuses (hover titles); max = how many neighbours count at most.
    adjacent: {
      tag: (sign, n, res, tag, max) => `${sign}${n} ${res} for each of your ${tag} structures next to it (up to ${max})`,
      type: (sign, n, res, name, max) => `${sign}${n} ${res} for each of your ${name}s next to it (up to ${max})`,
      terrain: (sign, n, res, terrain, max) => `${sign}${n} ${res} for each ${terrain} cell next to it with nothing built on it (up to ${max})`,
      free: (terrain) => `Needs no workers while it touches ${terrain}`,
      needs: (sign, n, res, needs, what) => `${sign}${n} ${res} while at least ${needs} ${what} are next to it`,
    },
  },
  // Orders panel and the build menu.
  hud: {
    noOrders: "Nothing queued.",
    cancelOrder: "Cancel and refund",
    cancelSite: "Demolish the site and get its cost back",
    pickCategory: "Pick a category, then a structure.",
    buildHelp: "Click the map to place it. R or right-click turns it, Esc cancels. It goes anywhere inside your territory and becomes a construction site that idle people build over a few turns. Goods go straight to your stores.",
    cantAfford: "Can't afford",
    jobsOff: "Switch off every structure with workers: they become idle and build your construction sites.",
    jobsOn: "Switch every structure with workers back on.",
    starving: "This turn's food production can't feed everyone: whoever can't eat dies at the end of the turn, idle people first, then units (newest first), then people at work.",
    people: (idle, pop, workers, builders, soldiers) => `Click: show on the map where your people are (green idle, red in jobs / units, blue building).\n${idle} idle. Population ${pop}: ${workers} in jobs, ${builders} building, ${soldiers} in units (and recruits), ${idle} idle.`,
    population: (pop, people, soldiers, net) => `Click: show on the map how many people live in each structure that gives housing (living / housing).\nPopulation ${pop}: ${people} people and ${soldiers} in units (and recruits).\nIt grows to match your food production: production left after everyone eats becomes new people at once while housing has room. When production falls short, whoever can't eat dies: idle people first, then units, then people at work.${net ? `\nEnd of this turn: ${net}.` : ""}`,
    housing: (cap, pop) => `Click: show on the map which structures give housing.\nHousing ${cap}: the population cap. Your people and the people in your units (${pop}) must fit in it: no new people join once it's full.`,
  },
  // Hint bar (placing, claiming, shooting, founding) and why a spot is refused.
  hint: {
    build: ": click to place · R to turn · Esc to cancel",
    shoot: "Click an enemy unit or structure in range. ",
    found: "Found a city here: R turns the footprint, click it (or Confirm) to place. ",
    problem: {
      offMap: "Part of it is off the map (or unexplored).",
      outside: "Part of it is outside your territory.",
      terrain: (name) => `It can't go on ${name}.`,
      built: "Something is already built there.",
      ordered: "You already ordered a build there.",
      enemy: "An enemy unit stands there.",
      coast: "It must touch water.",
    },
  },
  // Resource views: what the map shows when you click a resource on the top bar.
  resView: {
    people: "where your people are this turn: green = idle at home, red = in a job, a unit or a recruit ordered there, blue = building",
    population: "blue = people living there / the housing it gives (your people and the people in your units, filling the oldest homes first)",
    housing: "green = the housing each structure gives (your people and the people in your units must fit in it)",
    flow: "green = made there each turn, red = used each turn (units' upkeep; each person's food where they work, build or rest at home)",
    bar: (icon, name, text) => `${icon} ${name} view: ${text}. Faded = not working this turn. Click the resource again or Esc to leave. `,
  },
  // Tech tree popup and report tab.
  panels: {
    techOpen: "Open the tech tree (science and faith advances)",
    queued: "Queued: learnt as the turn resolves",
    needFirst: (names) => `Research ${names} first`,
    cantAfford: "Can't afford",
  },
  // Settings -> Hex Realms.
  replay: {
    speedHint: "How fast the end-of-turn combat replay pans to each fight and rolls the dice (press Next to move on).",
    skipHint: "Don't play the replay; combat cells just flash and the Report tab lists the dice.",
  },
  claim: {
    help: (claim) => `Buy an explored cell next to your land, one at a time; it's yours at once. Each bought cell costs ${claim.upkeep} gold a turn (unpaid cells are given up, farthest first), and it's lost to an enemy unit on or next to it, when it's cut off from your Town Halls' land, or to another realm's Town Hall.`,
    hint: (cost, claim) => `Extending territory: click a green cell to make it yours at once (${cost} each, no refund, ${claim.upkeep} gold a turn). Esc to stop. `,
  },
};
