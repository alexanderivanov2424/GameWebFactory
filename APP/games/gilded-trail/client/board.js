/*
 * Gilded Trail: the SVG hex map (terrain, value pips, blockades, golden city, explorers).
 *
 *   const map = TrailBoard.create(element, { onHex(hexKey), onExplorer(pid, index) });
 *   map.draw(game, you)     rebuild everything from the public game state (call when it changes)
 *   map.highlight({ targets: {hex: "go" | "step"}, explorer: index | null, you })
 *                           toggle classes on the existing elements (cheap; call on every render):
 *                           "go" = this click moves/pays now, "step" = legal but needs another card
 *                           or a choice; the selected explorer of `you` gets a dashed ring
 *
 * Hexes are pointy-top axial "q,r" keys; every clickable element carries data-hex or
 * data-pid + data-explorer. Styles live in index.html.
 */
(() => {
  const { svg } = AppDom;
  const SIZE = 22;
  const SQ3 = Math.sqrt(3);
  const TERRAIN_LABEL = {
    machete: "Jungle", paddle: "Water", coin: "Village", rubble: "Rubble", camp: "Base camp",
    mountain: "Mountain", start: "Start",
  };

  const pixel = (h) => [SIZE * SQ3 * (h.q + h.r / 2), SIZE * 1.5 * h.r];
  const corners = (x, y, size = SIZE) => Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 180) * (60 * i - 30);
    return `${(x + size * Math.cos(a)).toFixed(1)},${(y + size * Math.sin(a)).toFixed(1)}`;
  }).join(" ");

  function hexTitle(h) {
    if (h.goal) return `Golden city (${h.v} ${h.t})`;
    if (h.t === "rubble") return `Rubble: discard ${h.v} card${h.v > 1 ? "s" : ""}`;
    if (h.t === "camp") return `Base camp: remove ${h.v} card${h.v > 1 ? "s" : ""} from the game`;
    if (h.t === "mountain" || h.t === "start") return TERRAIN_LABEL[h.t];
    return `${TERRAIN_LABEL[h.t]}: ${h.v} ${h.t}${h.v > 1 ? "s" : ""}`;
  }

  function create(element, handlers) {
    let hexes = {};      // hex key -> <polygon>
    let explorers = {};  // "pid:index" -> <circle>

    element.addEventListener("click", (event) => {
      const ex = event.target.closest("[data-explorer]");
      if (ex) return handlers.onExplorer?.(ex.dataset.pid, Number(ex.dataset.explorer));
      const hex = event.target.closest("[data-hex]");
      if (hex) handlers.onHex?.(hex.dataset.hex);
    });

    function draw(game) {
      const board = game.board;
      const all = Object.entries(board.hexes);
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const [, h] of all) {
        const [x, y] = pixel(h);
        minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      }
      const pad = SIZE * 1.6;
      const root = svg("svg", {
        viewBox: `${minX - pad} ${minY - pad} ${maxX - minX + 2 * pad} ${maxY - minY + 2 * pad}`, class: "map-svg",
      });
      hexes = {}; explorers = {};

      const tiles = svg("g", {});
      const marks = svg("g", { class: "marks" });
      for (const [k, h] of all) {
        const [x, y] = pixel(h);
        const poly = svg("polygon", {
          class: `hex t-${h.t}${h.goal ? " goal" : ""}`, points: corners(x, y), "data-hex": k,
        }, svg("title", {}, hexTitle(h)));
        hexes[k] = poly;
        tiles.append(poly);
        if (h.goal) {
          marks.append(svg("polygon", { class: `goal-ring t-${h.t}`, points: corners(x, y, SIZE * 0.72) }),
            svg("text", { class: "goal-label", x, y: y + 13 }, "GOLD"));
        }
        if (h.t === "mountain") {
          marks.append(svg("path", { class: "peak", d: `M${x - 10},${y + 7} L${x - 3},${y - 7} L${x + 1},${y} L${x + 5},${y - 4} L${x + 11},${y + 7} Z` }));
        }
        for (let i = 0; i < h.v; i++) {
          const px = x + (i - (h.v - 1) / 2) * 7.5;
          const py = h.goal ? y - 2 : y;
          marks.append(h.t === "camp"
            ? svg("rect", { class: "pip", x: px - 2.8, y: py - 2.8, width: 5.6, height: 5.6, transform: `rotate(45 ${px} ${py})` })
            : svg("circle", { class: `pip${h.t === "coin" || h.goal ? " dark" : ""}`, cx: px, cy: py, r: 2.8 }));
        }
      }
      root.append(tiles, marks);

      // Blockades: a thick line along each border edge, with the value in a disc.
      for (const [id, b] of Object.entries(game.blockades)) {
        const lines = svg("g", { class: b.takenBy ? "border-open" : `border t-${b.t}` });
        let mx = 0, my = 0;
        for (const [a, c] of b.edges) {
          const [x1, y1] = pixel(board.hexes[a]);
          const [x2, y2] = pixel(board.hexes[c]);
          const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2, len = Math.hypot(x2 - x1, y2 - y1);
          const ux = (-(y2 - y1) / len) * SIZE / 2, uy = ((x2 - x1) / len) * SIZE / 2;
          lines.append(svg("line", { x1: cx - ux, y1: cy - uy, x2: cx + ux, y2: cy + uy }));
          mx += cx; my += cy;
        }
        if (b.takenBy) lines.setAttribute("stroke", game.players[b.takenBy]?.color || "#999");
        root.append(lines);
        if (!b.takenBy && b.edges.length) {
          const x = mx / b.edges.length, y = my / b.edges.length;
          root.append(svg("g", { class: "blockade" },
            svg("circle", { class: `t-${b.t}`, cx: x, cy: y, r: 11 }),
            svg("text", { x, y }, String(b.v)),
            svg("title", {}, `Blockade ${Number(id) + 1}: ${b.t === "rubble" ? `discard ${b.v}` : `${b.v} ${b.t}`}`)));
        }
      }

      const pieces = svg("g", {});
      for (const [pid, p] of Object.entries(game.players)) {
        p.explorers.forEach((k, i) => {
          if (!k) return;
          const [x, y] = pixel(board.hexes[k]);
          const c = svg("circle", {
            class: "explorer", cx: x, cy: y, r: SIZE * 0.55, fill: p.color, "data-pid": pid, "data-explorer": i,
          }, svg("title", {}, game.names[pid] + (p.explorers.length > 1 ? ` (explorer ${i + 1})` : "")));
          explorers[`${pid}:${i}`] = c;
          pieces.append(c);
        });
      }
      root.append(pieces);
      element.replaceChildren(root);
    }

    function highlight({ targets = {}, explorer = null, you = null }) {
      for (const [k, poly] of Object.entries(hexes)) {
        poly.classList.toggle("go", targets[k] === "go");
        poly.classList.toggle("step", targets[k] === "step");
      }
      for (const [id, c] of Object.entries(explorers)) {
        c.classList.toggle("active", id === `${you}:${explorer}`);
        c.classList.toggle("mine", id.startsWith(`${you}:`));
      }
    }

    return { draw, highlight };
  }

  window.TrailBoard = { create };
})();
