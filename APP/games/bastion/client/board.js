/*
 * Bastion: BastionBoard draws the shared map: terrain, roads (tinted in their owner's colour),
 * structures (one tile each, framed in their owner's colour; planned ones greyed out with a
 * 🔨n build-token badge) and units (a 🧍 worker or ⚔️ soldier badge in their owner's colour, one
 * per tile; ringed when it's yours). It reports the mouse. No rules here: everything comes from
 * the state.
 *
 *   const board = BastionBoard.create(element, { onHover(x, y), onLeave(), onClick(x, y, event),
 *                                                onRightClick(x, y, event) })
 *   board.build(game, you)     rebuild every cell from the state
 *   board.clearMarks()         remove hover marks (spot, hl, ghost, bad, prompt)
 *   board.mark(cells, cls)     add `cls` to each [x, y] on the board
 *   board.cellRect(x, y)       the cell's viewport rectangle (for tips)
 * The board is rebuilt only on a new state; hover marks are toggled on the existing cells.
 */
const BastionBoard = (() => {
  const { el } = AppDom;
  const TERRAIN_CLASS = { ".": "grass", F: "forest", M: "mountain", "~": "water" };
  const MARKS = ["spot", "hl", "ghost", "bad", "prompt"];

  function create(element, handlers) {
    let cells = [];
    let width = 0;
    let height = 0;

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
      const p = pos(e.target);
      handlers.onRightClick(p ? p[0] : null, p ? p[1] : null, e);
    });

    function build(game, you) {
      width = game.width;
      height = game.height;
      element.style.setProperty("--w", width);
      element.style.setProperty("--h", height);
      cells = [];
      for (let y = 0; y < height; y++) {
        const row = [];
        for (let x = 0; x < width; x++) {
          const key = `${x},${y}`;
          let base = TERRAIN_CLASS[game.terrain[y][x]] || "grass";
          const road = game.roads[key];
          if (road !== undefined) base = "road";
          const cell = el("div", { className: `cell ${base}` });
          if (base === "grass" && (x + y) % 2) cell.classList.add("alt");
          if (road !== undefined) cell.style.boxShadow = `inset 0 0 0 2px ${game.colors[road] || "#888"}`;
          cell.dataset.x = x;
          cell.dataset.y = y;
          row.push(cell);
        }
        cells.push(row);
      }
      for (const s of Object.values(game.structures)) {
        const cell = cells[s.y] && cells[s.y][s.x];
        if (!cell) continue;
        const info = game.kinds[s.kind] || {};
        cell.className = `cell bld k-${s.kind}${s.tokens ? " plan" : ""}`;
        cell.style.borderColor = game.colors[s.owner] || "#888";
        cell.append(el("span", { className: "ico", textContent: info.icon || "🏠" }));
        if (s.tokens) cell.append(el("span", { className: "badge tokens", textContent: `🔨${s.tokens}` }));
      }
      for (const [key, unit] of Object.entries(game.units || {})) {
        const [x, y] = key.split(",").map(Number);
        const cell = cells[y] && cells[y][x];
        if (!cell) continue;
        const badge = el("span", {
          className: `badge unit${unit.pid === you ? " mine" : ""}${unit.new ? " new" : ""}`,
          textContent: unit.soldier ? "⚔️" : "🧍",
          title: `${game.names[unit.pid] || unit.pid}'s ${unit.soldier ? "soldier" : "unit"}`,
        });
        badge.style.background = game.colors[unit.pid] || "#888";
        cell.append(badge);
      }
      element.replaceChildren(...cells.flat());
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

    return { build, clearMarks, mark, cellRect };
  }

  return { create };
})();
