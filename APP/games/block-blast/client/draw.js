/*
 * Block Blast: drawing tiles, symbols and cards from the layers the server sends. Pure helpers:
 * they hold no page state and take the game state's catalog (`catalog` = state.game, which has
 * tileTypes, symbolTypes and cards) as an argument.
 *
 * Layers: boards and card rotations arrive as {tiles: [rows of tile codes], symbols: [rows of
 * symbol codes]} ("." = none); catalog.tileTypes is code -> {name, ...}, catalog.symbolTypes is
 * code -> name. Colours are the .tile-<name> / .sym-<name> styles in index.html.
 *
 *   BlockBlastDraw.EMPTY                                "." (no tile / no symbol)
 *   BlockBlastDraw.SYMBOL_ICONS                         symbol name -> icon text
 *   BlockBlastDraw.tileName(catalog, code)              tile type name, or null for "."
 *   BlockBlastDraw.symbolName(catalog, code)            symbol name, or null for "."
 *   BlockBlastDraw.symbolEl(name)                       a symbol's rounded square
 *   BlockBlastDraw.tileEl(catalog, tag, className, layers, r, c)
 *                                                       one cell: the tile as a class, its symbol on top
 *   BlockBlastDraw.miniShape(catalog, layers)           a small drawing of one rotation
 *   BlockBlastDraw.symbolsText(card)                    "⚔ 1  ● 2" (+ "↗ opponent's board")
 *   BlockBlastDraw.cardFace(catalog, cardId, rotation = 0, extra = [])
 *                                                       a card (.pcard): name, shape, symbols, 🗑 if exile
 */
(() => {
  const { el } = AppDom;
  const EMPTY = ".";
  const SYMBOL_ICONS = { coin: "●", attack: "⚔", shield: "🛡", chapel: "✝", siege: "⚙", goblin: "👺" };

  const tileName = (catalog, code) => (code === EMPTY ? null : (catalog.tileTypes[code] || {}).name || "unknown");
  const symbolName = (catalog, code) => (code === EMPTY ? null : catalog.symbolTypes[code] || "unknown");

  function symbolEl(name) {
    return el("span", { className: `sym sym-${name}`, title: name }, SYMBOL_ICONS[name] || "?");
  }

  function tileEl(catalog, tag, className, layers, r, c) {
    const tile = tileName(catalog, layers.tiles[r][c]);
    const symbol = symbolName(catalog, layers.symbols[r][c]);
    const classes = [className, tile && `t tile-${tile}`].filter(Boolean).join(" ");
    const node = el(tag, { className: classes });
    if (symbol) node.append(symbolEl(symbol));
    return node;
  }

  function miniShape(catalog, layers) {
    const grid = el("div", { className: "mini" });
    grid.style.gridTemplateColumns = `repeat(${layers.tiles[0].length}, 16px)`;
    layers.tiles.forEach((row, r) => [...row].forEach((_, c) => {
      grid.append(tileEl(catalog, "span", "", layers, r, c));
    }));
    return grid;
  }

  function symbolsText(card) {
    const parts = Object.entries(card.symbols).map(([name, n]) => `${SYMBOL_ICONS[name] || name} ${n}`);
    if (card.playOn === "opponent") parts.unshift("↗ opponent's board");
    return parts.join("  ");
  }

  function cardFace(catalog, cardId, rotation = 0, extra = []) {
    const card = catalog.cards[cardId];
    return el("div", { className: `pcard card-${card.tile}` },
      card.exile ? el("div", { className: "exile", title: "Leaves your deck for good once played" }, "🗑") : "",
      el("div", { className: "cname" }, card.name),
      miniShape(catalog, card.rotations[rotation]),
      el("div", { className: "csyms" }, symbolsText(card)),
      ...extra);
  }

  window.BlockBlastDraw = { EMPTY, SYMBOL_ICONS, tileName, symbolName, symbolEl, tileEl, miniShape, symbolsText, cardFace };
})();
