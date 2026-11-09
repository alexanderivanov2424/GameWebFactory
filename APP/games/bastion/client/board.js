/*
 * Bastion: BastionBoard draws the shared board (terrain, roads, walls, enemy blights, buildings
 * with merged borders and their badges, and the units placed this round as small tokens in their
 * player's colour) and reports the mouse. No rules here: outputs, links, flags and placements all
 * come from the state.
 *
 *   const board = BastionBoard.create(element, { onHover(x, y), onLeave(), onClick(x, y, event),
 *                                                onRightClick(), onWheel(direction) })
 *   board.build(game, you)     rebuild every cell from game (catalog terrain + structures +
 *                              placements); `you`'s tokens get a ring
 *   board.structureAt(x, y)    uid (string) of the building there, or null
 *   board.clearMarks()         remove hover marks (ghost, bad, target, hl, spot)
 *   board.mark(cells, cls)     add `cls` to each [x, y] that is on the board
 *   board.cellRect(x, y)       the cell's viewport rectangle (getBoundingClientRect, for tips)
 * The board is rebuilt only on a new state; hover marks are toggled on the existing cells.
 */
const BastionBoard = (() => {
  const { el } = AppDom;
  const TERRAIN_CLASS = { ".": "grass", F: "forest", M: "mountain", "~": "water" };
  const MARKS = ["ghost", "bad", "target", "hl", "spot"];

  function create(element, handlers) {
    let cells = [];
    let width = 0;
    let height = 0;
    let owner = {}; // "x,y" -> structure uid

    const pos = (target) => {
      const cell = target.closest(".cell");
      return cell ? [Number(cell.dataset.x), Number(cell.dataset.y)] : null;
    };
    element.addEventListener("mouseover", (e) => {
      const p = pos(e.target);
      if (p) handlers.onHover(p[0], p[1]);
    });
    element.addEventListener("mouseleave", () => handlers.onLeave());
    element.addEventListener("click", (e) => {
      const p = pos(e.target);
      if (p) handlers.onClick(p[0], p[1], e);
    });
    element.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      handlers.onRightClick();
    });
    element.addEventListener("wheel", (e) => {
      if (handlers.onWheel(e.deltaY > 0 ? 1 : -1)) e.preventDefault();
    }, { passive: false });

    function build(game, you) {
      width = game.width;
      height = game.height;
      element.style.setProperty("--w", width);
      element.style.setProperty("--h", height);
      owner = {};
      cells = [];
      const roads = new Set(game.roads);
      const walls = new Set(game.walls);
      for (let y = 0; y < height; y++) {
        const row = [];
        for (let x = 0; x < width; x++) {
          const key = `${x},${y}`;
          const blight = game.blights[key];
          // Occupied cells get no terrain class: .cell.grass.alt would outrank .cell.road etc.
          let base = TERRAIN_CLASS[game.terrain[y][x]] || "grass";
          if (roads.has(key)) base = "road";
          else if (walls.has(key)) base = "wall";
          else if (blight) base = "blight";
          const cell = el("div", { className: `cell ${base}` });
          if (base === "grass" && (x + y) % 2) cell.classList.add("alt");
          cell.dataset.x = x;
          cell.dataset.y = y;
          if (blight) {
            cell.classList.add("razeable");
            if (blight.lair) cell.classList.add("lair");
            cell.textContent = blight.icon || "☠";
            if (blight.strikes) cell.append(el("span", { className: "badge strikes", textContent: `${blight.strikes}✕` }));
          }
          row.push(cell);
        }
        cells.push(row);
      }
      for (const [uid, s] of Object.entries(game.structures)) drawStructure(game, uid, s);
      drawUnits(game, you);
      element.replaceChildren(...cells.flat());
    }

    function firstCell(list) {
      return [...list].sort((a, b) => a[1] - b[1] || a[0] - b[0])[0];
    }

    function drawStructure(game, uid, s) {
      const info = game.kinds[s.kind];
      const own = new Set(s.cells.map(([x, y]) => `${x},${y}`));
      const ruined = new Set(s.ruined.map(([x, y]) => `${x},${y}`));
      const first = firstCell(s.cells);
      for (const [x, y] of s.cells) {
        const cell = cells[y] && cells[y][x];
        if (!cell) continue;
        owner[`${x},${y}`] = uid;
        cell.classList.remove("grass", "alt");
        cell.classList.add("bld", `k-${s.kind}`);
        if (own.has(`${x},${y - 1}`)) cell.classList.add("nt");
        if (own.has(`${x},${y + 1}`)) cell.classList.add("nb");
        if (own.has(`${x - 1},${y}`)) cell.classList.add("nl");
        if (own.has(`${x + 1},${y}`)) cell.classList.add("nr");
        if (s.worked) cell.classList.add("worked");
        if (info.depot) cell.classList.add("depot");
        if (s.plague) cell.classList.add("sick");
        if (s.frozen) cell.classList.add("frozen");
        if (ruined.has(`${x},${y}`)) cell.classList.add("ruined");
      }
      const cell = cells[first[1]] && cells[first[1]][first[0]];
      if (!cell) return;
      cell.append(info.icon || "🏠");
      if ("output" in s && info.work) {
        const key = Object.keys(info.work.makes)[0];
        cell.append(el("span", { className: `badge out${s.output ? "" : " none"}`, textContent: `+${s.output}${game.icons[key] || ""}` }));
      }
      const stored = Object.entries(s.store).map(([k, n]) => `${game.icons[k] || k}${n}`).join(" ");
      if (stored) cell.append(el("span", { className: "badge store", textContent: stored }));
      const flags = (s.plague ? "🦠" : "") + (s.frozen ? "❄️" : "") + (s.link === "none" && info.work ? "⛓️‍💥" : "");
      if (flags) cell.append(el("span", { className: "badge flags", textContent: flags }));
      if (s.worked) cell.append(el("span", { className: "badge done", textContent: "✓" }));
    }

    // One-unit targets: "s<uid>" (on the building's first cell) and "raze<x>,<y>" (on that tile).
    function drawUnits(game, you) {
      for (const [target, who] of Object.entries(game.placements || {})) {
        if (typeof who !== "string") continue; // pools (haul, fight) are drawn off the board
        let at = null;
        if (target.startsWith("raze")) at = target.slice(4).split(",").map(Number);
        else if (target.startsWith("s") && game.structures[target.slice(1)]) at = firstCell(game.structures[target.slice(1)].cells);
        const cell = at && cells[at[1]] && cells[at[1]][at[0]];
        if (!cell) continue;
        const token = el("span", { className: `badge unit${who === you ? " mine" : ""}`, title: game.names[who] || who });
        token.style.background = game.colors[who] || "#888";
        cell.append(token);
      }
    }

    function clearMarks() {
      for (const cls of MARKS) element.querySelectorAll(`.${cls}`).forEach((c) => c.classList.remove(cls));
    }

    function mark(list, cls) {
      for (const [x, y] of list) {
        if (x >= 0 && y >= 0 && x < width && y < height) cells[y][x].classList.add(cls);
      }
    }

    function cellRect(x, y) {
      const cell = cells[y] && cells[y][x];
      return cell ? cell.getBoundingClientRect() : null;
    }

    return {
      build,
      clearMarks,
      mark,
      cellRect,
      structureAt: (x, y) => owner[`${x},${y}`] || null,
    };
  }

  return { create };
})();
