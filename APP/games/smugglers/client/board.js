/*
 * Smugglers: the SVG board (planets, routes with dots, cargo tokens, ships, Interpol pieces).
 *
 *   const board = SmugglersBoard.create(element, { onNode(node), onShip(shipId), onPiece(pieceId) });
 *   board.draw(game, you)    rebuild everything from the public game state (call when it changes)
 *   board.highlight({ reach: {node: stops?}, targets: [node], ship: id, piece: id })
 *                            toggle highlight classes on the existing elements (cheap; call on
 *                            every render): reach (green ring; yellow "stop" if it must stop
 *                            there: a patrol or checkpoint), targets (blue ring), the selected ship / piece
 *
 * Every clickable element carries data-node / data-ship / data-piece; styles live in index.html.
 * Planets are drawn from their "art" (just a color for now) so they're easy to find.
 */
(() => {
  const { svg } = AppDom;
  const PLANET_R = 20;
  const DOT_R = 4;

  function create(element, handlers) {
    let nodes = {};   // node id -> <g>
    let ships = {};   // ship id -> <g>
    let pieces = {};  // piece id -> <g>

    element.addEventListener("click", (event) => {
      const ship = event.target.closest("[data-ship]");
      if (ship) return handlers.onShip?.(ship.dataset.ship);
      const piece = event.target.closest("[data-piece]");
      if (piece) return handlers.onPiece?.(piece.dataset.piece);
      const node = event.target.closest("[data-node]");
      if (node) handlers.onNode?.(node.dataset.node);
    });

    function draw(game, you) {
      const board = game.board;
      const root = svg("svg", { viewBox: `0 0 ${board.width} ${board.height}`, class: "board-svg" });
      root.append(defs(), svg("rect", { width: board.width, height: board.height, class: "space" }));
      root.append(stars(board));
      nodes = {}; ships = {}; pieces = {};

      const edges = svg("g", { class: "edges" });
      for (const [a, b] of board.edges) {
        const [x1, y1] = board.nodes[a];
        const [x2, y2] = board.nodes[b];
        edges.append(svg("line", { x1, y1, x2, y2 }));
      }
      root.append(edges);

      const layer = svg("g", { class: "nodes" });
      for (const [id, [x, y]] of Object.entries(board.nodes)) {
        const planet = board.planets[id];
        const g = svg("g", { class: planet ? "node planet" : "node dot", "data-node": id });
        const r = planet ? PLANET_R : DOT_R;
        g.append(svg("circle", { cx: x, cy: y, r: r + 7, class: "ring" }));
        if (planet) {
          g.append(
            svg("circle", { cx: x, cy: y, r, fill: planet.color, class: "globe" }),
            svg("circle", { cx: x, cy: y, r, fill: "url(#shade)", class: "shade" }),
            svg("text", { x, y: y + r + 16, class: "planet-name" }, planet.name),
            svg("title", {}, planet.name),
          );
        } else {
          g.append(svg("circle", { cx: x, cy: y, r: 12, class: "hit" }), svg("circle", { cx: x, cy: y, r, class: "pip" }));
        }
        nodes[id] = g;
        layer.append(g);
      }
      root.append(layer);

      // Cargo tokens on their source planets (contracts nobody has picked up yet).
      const tokens = svg("g", { class: "tokens" });
      const waiting = {};
      for (const cid of game.row) {
        if (game.holders[cid]) continue;
        const planet = game.contracts[cid].from;
        (waiting[planet] ||= []).push(cid);
      }
      for (const [planet, cids] of Object.entries(waiting)) {
        const [x, y] = board.nodes[planet];
        cids.forEach((cid, i) => {
          const tx = x + PLANET_R - 4 + i * 18;
          const ty = y - PLANET_R - 12;
          tokens.append(svg("g", { class: "token" },
            svg("rect", { x: tx, y: ty, width: 16, height: 14, rx: 3 }),
            svg("text", { x: tx + 8, y: ty + 11 }, cid.slice(1)),
            svg("title", {}, `Cargo for contract #${cid.slice(1)}`)));
        });
      }
      root.append(tokens);

      // Things standing on nodes: barriers and checkpoints sit on the node itself; ships and
      // patrols share the space around it.
      const around = {};
      const police = game.police;
      const pieceLayer = svg("g", { class: "pieces" });
      for (const piece of Object.values(police.pieces)) {
        if (!piece.at) continue;
        const [x, y] = board.nodes[piece.at];
        if (piece.kind === "patrol") {
          (around[piece.at] ||= []).push({ piece });
          continue;
        }
        const g = svg("g", { class: `piece ${piece.kind}`, "data-piece": piece.id });
        if (piece.kind === "barrier") {
          g.append(
            svg("circle", { cx: x, cy: y, r: 10 }),
            svg("path", { d: `M${x - 6} ${y - 6}L${x + 6} ${y + 6}M${x + 6} ${y - 6}L${x - 6} ${y + 6}` }),
            svg("title", {}, "Barrier: ships can't enter or pass"),
          );
        } else {
          const s = board.planets[piece.at] ? PLANET_R + 4 : 11;
          g.append(svg("rect", { x: x - s, y: y - s, width: 2 * s, height: 2 * s, rx: 4 }),
            svg("title", {}, "Checkpoint: loaded ships that enter stop and may be inspected"));
        }
        pieces[piece.id] = g;
        pieceLayer.append(g);
      }
      root.append(pieceLayer);

      for (const [sid, ship] of Object.entries(game.ships)) (around[ship.at] ||= []).push({ sid, ship });
      const shipLayer = svg("g", { class: "ships" });
      for (const [at, things] of Object.entries(around)) {
        const [x, y] = board.nodes[at];
        const radius = board.planets[at] ? PLANET_R + 10 : 13;
        things.forEach((thing, i) => {
          const angle = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(things.length, 1) + (things.length > 1 ? 0 : Math.PI / 4);
          const cx = x + radius * Math.cos(angle);
          const cy = y + radius * Math.sin(angle);
          if (thing.piece) {
            const g = svg("g", { class: "piece patrol", "data-piece": thing.piece.id },
              svg("path", { d: `M${cx} ${cy - 10}L${cx + 9} ${cy - 5}L${cx + 7} ${cy + 6}L${cx} ${cy + 11}L${cx - 7} ${cy + 6}L${cx - 9} ${cy - 5}Z` }),
              svg("text", { x: cx, y: cy + 4 }, "P"),
              svg("title", {}, "Interpol patrol"));
            pieces[thing.piece.id] = g;
            shipLayer.append(g);
          } else {
            shipLayer.append(drawShip(game, thing.sid, thing.ship, cx, cy, you));
          }
        });
      }
      root.append(shipLayer);
      element.replaceChildren(root);
    }

    function drawShip(game, sid, ship, x, y, you) {
      const color = game.smugglers[ship.owner]?.color || "#ccc";
      const mine = ship.owner === you;
      const g = svg("g", { class: `ship${mine ? " mine" : ""}${ship.acted ? " acted" : ""}`, "data-ship": sid },
        svg("circle", { cx: x, cy: y, r: 13, class: "select-ring" }),
        svg("path", { d: `M${x} ${y - 10}L${x + 8} ${y + 8}L${x} ${y + 4}L${x - 8} ${y + 8}Z`, fill: color }));
      if (ship.cargo) g.append(svg("rect", { x: x - 3, y: y - 1, width: 6, height: 5, class: "cargo-box" }));
      const owner = game.names[ship.owner] || "?";
      const cargo = ship.cargo ? `${ship.cargo} goods (declared ${game.goods[ship.declared]?.name || "?"})` : "empty";
      g.append(svg("title", {}, `${ship.name} (${owner}), speed ${ship.speed}, ${cargo}`));
      ships[sid] = g;
      return g;
    }

    function highlight({ reach = {}, targets = [], ship = null, piece = null } = {}) {
      const targetSet = new Set(targets);
      for (const [id, g] of Object.entries(nodes)) {
        g.classList.toggle("reach", id in reach);
        g.classList.toggle("stop", reach[id] === true);
        g.classList.toggle("target", targetSet.has(id));
      }
      for (const [id, g] of Object.entries(ships)) g.classList.toggle("selected", id === ship);
      for (const [id, g] of Object.entries(pieces)) g.classList.toggle("selected", id === piece);
    }

    return { draw, highlight };
  }

  function defs() {
    return svg("defs", {},
      svg("radialGradient", { id: "shade", cx: "35%", cy: "30%", r: "75%" },
        svg("stop", { offset: "0%", "stop-color": "#fff", "stop-opacity": "0.55" }),
        svg("stop", { offset: "45%", "stop-color": "#fff", "stop-opacity": "0" }),
        svg("stop", { offset: "100%", "stop-color": "#000", "stop-opacity": "0.45" })));
  }

  function stars(board) {
    // The same sky every time for a board: a small seeded generator.
    let seed = [...board.id].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
    const random = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
    const g = svg("g", { class: "stars" });
    for (let i = 0; i < 140; i++) {
      g.append(svg("circle", { cx: random() * board.width, cy: random() * board.height, r: random() < 0.15 ? 1.4 : 0.7 }));
    }
    return g;
  }

  window.SmugglersBoard = { create };
})();
