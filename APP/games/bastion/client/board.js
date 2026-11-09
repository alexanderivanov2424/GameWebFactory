/*
 * Bastion: BastionBoard draws the shared board (terrain, roads with the goods a haul left on
 * them, walls, enemy blights and buildings with their badges) and reports the mouse. No rules here: outputs, links and flags
 * all come from the state.
 *
 *   const board = BastionBoard.create(element, { onHover(x, y), onLeave(), onClick(x, y),
 *                                                onRightClick(), onWheel(direction) })
 *   board.build(game)          rebuild every cell from game (catalog terrain + structures)
 *   board.structureAt(x, y)    uid (string) of the building there, or null
 *   board.clearMarks()         remove hover marks (ghost, bad, target, hl)
 *   board.mark(cells, cls)     add `cls` to each [x, y] that is on the board
 *   board.cellRect(x, y)       {left, top} of a cell inside the board's parent (for tips)
 * The board is rebuilt only on a new state; hover marks are toggled on the existing cells.
 */
const BastionBoard = (() => {
  const { el } = AppDom;
  const TERRAIN_CLASS = { ".": "grass", F: "forest", M: "mountain", "~": "water" };
  const MARKS = ["ghost", "bad", "target", "hl"];

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
      if (p) handlers.onClick(p[0], p[1]);
    });
    element.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      handlers.onRightClick();
    });
    element.addEventListener("wheel", (e) => {
      if (handlers.onWheel(e.deltaY > 0 ? 1 : -1)) e.preventDefault();
    }, { passive: false });

    function build(game) {
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
          const cargo = (game.cargo || {})[key];
          if (cargo) {
            const n = Object.values(cargo.goods).reduce((a, b) => a + b, 0);
            cell.append(el("span", { className: `badge cargo${cargo.safe ? " safe" : ""}`, textContent: `📦${n}` }));
          }
          if (blight) {
            cell.classList.add("razeable");
            if (blight.lair) cell.classList.add("lair");
            cell.textContent = blight.icon || "☠";
          }
          row.push(cell);
        }
        cells.push(row);
      }
      for (const [uid, s] of Object.entries(game.structures)) drawStructure(game, uid, s);
      element.replaceChildren(...cells.flat());
    }

    function drawStructure(game, uid, s) {
      const info = game.kinds[s.kind];
      const own = new Set(s.cells.map(([x, y]) => `${x},${y}`));
      const ruined = new Set(s.ruined.map(([x, y]) => `${x},${y}`));
      const first = [...s.cells].sort((a, b) => a[1] - b[1] || a[0] - b[0])[0];
      const color = s.owner ? game.colors[s.owner] || "#999" : "transparent";
      for (const [x, y] of s.cells) {
        const cell = cells[y] && cells[y][x];
        if (!cell) continue;
        owner[`${x},${y}`] = uid;
        cell.classList.remove("grass", "alt");
        cell.classList.add("bld", `k-${s.kind}`);
        cell.style.setProperty("--owner", color);
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
      const cell = cells[first[1]][first[0]];
      cell.append(info.icon || "🏠");
      if ("output" in s) {
        const key = Object.keys(info.work.makes)[0];
        cell.append(el("span", { className: `badge out${s.output ? "" : " none"}`, textContent: `+${s.output}${game.icons[key] || ""}` }));
      }
      const stored = Object.values(s.store).reduce((a, b) => a + b, 0);
      if (stored) cell.append(el("span", { className: "badge store", textContent: `📦${stored}` }));
      const flags = (s.plague ? "🦠" : "") + (s.frozen ? "❄️" : "") + (s.link === "none" && info.work ? "⛓️‍💥" : "");
      if (flags) cell.append(el("span", { className: "badge flags", textContent: flags }));
      if (s.worked) cell.append(el("span", { className: "badge done", textContent: "✓" }));
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
      return cell ? { left: cell.offsetLeft, top: cell.offsetTop } : { left: 0, top: 0 };
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
