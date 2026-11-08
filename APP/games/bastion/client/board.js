/*
 * Bastion: drawing the board (no page state, no rules). Load before game.js.
 *
 *   BastionBoard.build(boardEl, game, handlers) -> {cells: {"x,y": cellEl}, hide(set of keys)}
 *       Rebuilds the grid from game.map (terrain, roads, keep, entrances) and game.structures
 *       (icon, owner color from game.seats, level pips, wall health). handlers: onHover(x, y) /
 *       onLeave(), onClick(x, y), onCancel() (right click).
 *   BastionBoard.center(x, y)           pixel center of a cell inside the board (for the overlay)
 *   BastionBoard.CELL                   cell size in px (matches --cell in index.html)
 *   BastionBoard.roadUse(game)          {cellKey: true} cells of roads used by any level so far or next
 *   BastionBoard.hpBar(hp, max)         a small health bar element
 */
(() => {
  const { el } = AppDom;
  const CELL = 46;
  const BORDER = 3;
  const TERRAIN = { ".": "grass", "^": "rocks", "~": "water", T: "forest" };
  const TERRAIN_ICON = { "^": "🪨", T: "🌲" };
  const ROAD_KINDS = new Set(["wall", "spikes", "tar"]);

  function center(x, y) {
    return { x: x * CELL + CELL / 2, y: y * CELL + CELL / 2 };
  }

  function hpBar(hp, max) {
    const ratio = max > 0 ? Math.max(0, Math.min(1, hp / max)) : 0;
    const bar = el("div", { className: "hpbar" + (ratio < 0.35 ? " low" : "") }, el("span"));
    bar.firstChild.style.width = `${Math.round(ratio * 100)}%`;
    return bar;
  }

  // Roads that matter so far: any road used by a level up to the next one coming.
  function roadUse(game) {
    const upTo = Math.min(game.levels.length, game.level + (game.stage === "market" ? 1 : 0));
    const used = new Set();
    game.levels.slice(0, upTo).forEach((level) => level.roads.forEach((r) => used.add(r)));
    const cells = {};
    for (const [name, road] of Object.entries(game.map.roads)) {
      if (!used.has(name)) continue;
      road.forEach(([x, y]) => { cells[`${x},${y}`] = true; });
    }
    return cells;
  }

  function structureEl(game, info) {
    const card = game.cards[info.card];
    const seat = info.owner && game.seats[info.owner];
    const node = el("div", { className: "structure" + (ROAD_KINDS.has(card.kind) ? " road-kind" : "") }, card.icon);
    node.style.setProperty("--owner", seat ? seat.color : "#8a8a8a");
    if (card.maxLevel > 1) node.append(el("span", { className: "lvl" }, "★".repeat(info.level)));
    if (info.maxHp) node.append(hpBar(info.hp, info.maxHp));
    return node;
  }

  function build(boardEl, game, handlers) {
    const map = game.map;
    boardEl.style.setProperty("--w", map.width);
    boardEl.style.setProperty("--h", map.height);
    const roadCells = {};
    const entrances = {};
    for (const [name, road] of Object.entries(map.roads)) {
      road.forEach(([x, y]) => { roadCells[`${x},${y}`] = true; });
      entrances[road[0].join(",")] = name === "main" ? "MAIN" : "FLANK";
    }
    const used = roadUse(game);
    const cells = {};
    const nodes = [];
    for (let y = 0; y < map.height; y++) {
      for (let x = 0; x < map.width; x++) {
        const k = `${x},${y}`;
        const ground = map.terrain[y][x];
        const cell = el("div", { className: "cell" });
        cell.dataset.key = k;
        if (map.keep[0] === x && map.keep[1] === y) {
          cell.classList.add("keep");
          cell.textContent = "🏰";
          cell.id = "keep-cell";
        } else if (roadCells[k]) {
          cell.classList.add("road");
          if (ground === "~") cell.classList.add("bridge");
          if (!used[k]) cell.classList.add("unused");
          if (entrances[k]) {
            cell.classList.add("entrance");
            cell.append(el("span", { className: "entry" }, entrances[k]));
          }
        } else {
          cell.classList.add(TERRAIN[ground] || "grass");
          if (ground === "." && (x + y) % 2) cell.classList.add("alt");
          if (TERRAIN_ICON[ground]) cell.append(el("span", { className: "terrain" }, TERRAIN_ICON[ground]));
        }
        const info = game.structures[k];
        if (info) cell.append(structureEl(game, info));
        cell.addEventListener("mouseenter", () => handlers.onHover(x, y));
        cell.addEventListener("click", () => handlers.onClick(x, y));
        cells[k] = cell;
        nodes.push(cell);
      }
    }
    boardEl.replaceChildren(...nodes);
    boardEl.onmouseleave = () => handlers.onLeave();
    boardEl.oncontextmenu = (event) => { event.preventDefault(); handlers.onCancel(); };
    return {
      cells,
      // Hide the structures in these cells (the replay draws its own walls there).
      hide(keys) {
        for (const k of keys) {
          const s = cells[k] && cells[k].querySelector(".structure");
          if (s) s.style.visibility = "hidden";
        }
      },
      showAll() {
        for (const cell of Object.values(cells)) {
          const s = cell.querySelector(".structure");
          if (s) s.style.visibility = "";
        }
      },
    };
  }

  window.BastionBoard = { build, center, hpBar, roadUse, CELL, BORDER };
})();
