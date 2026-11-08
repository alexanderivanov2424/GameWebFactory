/*
 * Block Blast: one player's board (a grid of cells) and the previews drawn on it: the hover ghost,
 * the "would clear" outline and the clear flash. Holds no page state: game.js owns the selection
 * and the hover, and passes in what each call needs. Previews only toggle classes on the existing
 * cells; a board is rebuilt only when a new state arrives. Styles live in index.html.
 *
 *   const { element, cells } = BlockBlastBoard.build(catalog, layers, { big, size, handlers })
 *       catalog = state.game; layers = a seat's board; size = rules.boardSize (sets --size);
 *       cells = the cell elements, row by row (cells[r * size + c]). handlers (omit for a board
 *       you can't drop on): onHover(r, c), onLeave(), onClick(r, c), onRotate() -> true if it
 *       rotated (then the right-click / wheel event is used up)
 *   BlockBlastBoard.placement(catalog, piece, occupied, size, r, c)
 *       piece (layers of one rotation) with its middle on (r, c) of a board whose tile layer is
 *       `occupied`: {row, col (its top-left corner, what the server takes), fits,
 *       tiles: [{r, c, tile, symbol, inside}]}
 *   BlockBlastBoard.clearPreview(cells)             removes every ghost / would-clear class
 *   BlockBlastBoard.showGhost(cells, size, occupied, place)
 *       draws `place` (from placement()) and, if it fits, outlines the lines it would complete
 *   BlockBlastBoard.flash(cells, size, cleared)     animates the cleared [[r, c], ...] cells
 */
(() => {
  const { el } = AppDom;
  const { EMPTY, SYMBOL_ICONS, tileEl, tileName, symbolName } = BlockBlastDraw;
  const PREVIEW_CLASSES = ["ghost", "bad", "would-clear", "gsym"];

  function build(catalog, layers, { big, size, handlers }) {
    const cells = [];
    const element = el("div", { className: `board ${big ? "big" : "small"}` });
    element.style.setProperty("--size", size);
    layers.tiles.forEach((row, r) => {
      [...row].forEach((_, c) => {
        const cell = tileEl(catalog, "div", "cell", layers, r, c);
        if (handlers) {
          cell.addEventListener("mouseenter", () => handlers.onHover(r, c));
          cell.addEventListener("click", () => handlers.onClick(r, c));
        }
        cells.push(cell);
        element.append(cell);
      });
    });
    if (handlers) {
      element.addEventListener("mouseleave", () => handlers.onLeave());
      const rotate = (event) => {
        if (handlers.onRotate()) event.preventDefault();
      };
      element.addEventListener("contextmenu", rotate);
      element.addEventListener("wheel", rotate, { passive: false });
    }
    return { element, cells };
  }

  // The cell under the mouse is the shape's middle.
  function placement(catalog, piece, occupied, size, r, c) {
    const row = r - Math.floor((piece.tiles.length - 1) / 2);
    const col = c - Math.floor((piece.tiles[0].length - 1) / 2);
    const tiles = [];
    let fits = true;
    piece.tiles.forEach((line, dr) => [...line].forEach((code, dc) => {
      if (code === EMPTY) return;
      const tr = row + dr;
      const tc = col + dc;
      const inside = tr >= 0 && tr < size && tc >= 0 && tc < size;
      if (!inside || occupied[tr][tc] !== EMPTY) fits = false;
      tiles.push({ r: tr, c: tc, tile: tileName(catalog, code), symbol: symbolName(catalog, piece.symbols[dr][dc]), inside });
    }));
    return { row, col, tiles, fits };
  }

  function clearPreview(cells) {
    for (const cell of cells) {
      const symbolClasses = [...cell.classList].filter((name) => name.startsWith("gsym-"));
      cell.classList.remove(...PREVIEW_CLASSES, ...symbolClasses);
      delete cell.dataset.ghost;
    }
  }

  function showGhost(cells, size, occupied, place) {
    for (const tile of place.tiles) {
      if (!tile.inside) continue;
      const cell = cells[tile.r * size + tile.c];
      cell.classList.add("ghost");
      if (!place.fits) cell.classList.add("bad");
      if (tile.symbol) {
        cell.classList.add("gsym", `gsym-${tile.symbol}`);
        cell.dataset.ghost = SYMBOL_ICONS[tile.symbol] || "?";
      }
    }
    if (!place.fits) return;
    // Outline the rows and columns this placement would complete.
    const filled = (r, c) => occupied[r][c] !== EMPTY || place.tiles.some((t) => t.r === r && t.c === c);
    for (let i = 0; i < size; i++) {
      let fullRow = true;
      let fullCol = true;
      for (let j = 0; j < size; j++) {
        if (!filled(i, j)) fullRow = false;
        if (!filled(j, i)) fullCol = false;
      }
      for (let j = 0; j < size; j++) {
        if (fullRow) cells[i * size + j].classList.add("would-clear");
        if (fullCol) cells[j * size + i].classList.add("would-clear");
      }
    }
  }

  function flash(cells, size, cleared) {
    for (const [r, c] of cleared) cells[r * size + c].classList.add("flash");
  }

  window.BlockBlastBoard = { build, placement, clearPreview, showGhost, flash };
})();
