/*
 * Marooned: the island board (a CSS grid of squares).
 *
 *   const board = MaroonedBoard.create(element, { onSquare(key, how) })
 *   board.draw(game, priv, you, { canAct, selected, colors })
 *       Rebuilds the grid from the state: explored tiles (colour, icon, resources, pile),
 *       fog on unexplored squares, player tokens, and while it's your free turn the squares
 *       you can move to (with their energy cost) or explore. Clicking calls
 *       onSquare(key, "move" | "explore" | "select").
 *
 * Square keys are "row,col" strings, as in game.tiles.
 */
(() => {
  const { el } = AppDom;

  const ITEM_ICONS = {
    wood: "🪵", fiber: "🌿", food: "🥥", water: "💧", stone: "🪨", scrap: "🧵", herbs: "🌱", relic: "🗿",
  };

  function initials(name) {
    return (name || "?").trim().slice(0, 2);
  }

  function create(element, { onSquare }) {
    function draw(game, priv, you, { canAct, selected, colors }) {
      const size = game.size;
      const moves = (canAct && priv.moves) || {};
      const explorable = new Set((canAct && priv.explorable) || []);
      const exploring = game.pending && game.pending.kind === "explore" ? game.pending.cell : null;
      const here = {};
      for (const pid of game.order) {
        const pos = game.people[pid].pos;
        (here[`${pos[0]},${pos[1]}`] ||= []).push(pid);
      }
      const grid = el("div", { className: "island" });
      grid.style.gridTemplateColumns = `repeat(${size}, var(--square))`;
      for (let row = 0; row < size; row++) {
        for (let col = 0; col < size; col++) {
          const key = `${row},${col}`;
          const tile = game.tiles[key];
          const square = el("div", { className: "square" });
          if (tile) {
            const kind = game.tileTypes[tile.type];
            square.style.background = kind.color;
            square.title = `${kind.name}: ${kind.text}`;
            square.append(el("span", { className: "tile-icon" }, kind.icon || ""));
            const res = Object.entries(tile.res || {})
              .map(([item, n]) => `${ITEM_ICONS[item] || item}${n < 0 ? "∞" : n}`).join(" ");
            if (res) square.append(el("span", { className: "tile-res" }, res));
            if (tile.pile && Object.keys(tile.pile).length) {
              square.append(el("span", { className: "tile-pile", title: "Items on the ground" }, "📦"));
            }
            if (tile.type === "camp") square.classList.add("camp");
          } else {
            square.classList.add("fog");
            square.title = "Unexplored";
          }
          if (key in moves) {
            square.classList.add("can-move");
            square.append(el("span", { className: "cost" }, `⚡${moves[key]}`));
            square.title = `Move here (${moves[key]} energy)\n${square.title}`;
          } else if (explorable.has(key)) {
            square.classList.add("can-explore");
            square.append(el("span", { className: "cost" }, "🔍"));
            square.title = "Explore (1 energy)";
          }
          if (key === exploring) square.classList.add("exploring");
          if (key === selected) square.classList.add("selected");
          const tokens = el("span", { className: "tokens" });
          for (const pid of here[key] || []) {
            const token = el("span", { className: "token", title: game.names[pid] }, initials(game.names[pid]));
            token.style.background = colors[pid];
            if (pid === you) token.classList.add("me");
            if (pid === game.turn) token.classList.add("acting");
            tokens.append(token);
          }
          square.append(tokens);
          square.addEventListener("click", () => {
            onSquare(key, key in moves ? "move" : explorable.has(key) ? "explore" : "select");
          });
          grid.append(square);
        }
      }
      element.replaceChildren(grid);
    }
    return { draw };
  }

  window.MaroonedBoard = { create, ITEM_ICONS };
})();
