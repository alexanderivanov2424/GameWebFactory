/*
 * Block Blast client: the game page. Renders the state from the server (rules in ../server.py)
 * and sends place / patch / buy / market_remove / aim / remove / end_turn. Holds no rules: card rotations, the
 * patch piece and the rule numbers come from the state (game.cards, game.rules), and the hover
 * ghost / "would clear" outline are only previews (the server decides).
 *
 * Files: draw.js (BlockBlastDraw: tiles, symbols, cards from layers), board.js (BlockBlastBoard:
 * one board's cells, the hover ghost, the clear flash), this file (the page).
 * Sections: setup, selection + keyboard, auto end turn, render (lobby / game), boards (seat
 * panels, drop targets, hover ghost, clear animation), market and log, hand bar, windows (deck
 * viewer, help legend, the ? button).
 */
(() => {
  const { $, el } = AppDom;
  const Draw = BlockBlastDraw;
  const Board = BlockBlastBoard;
  let state = null;

  // --- Setup ---------------------------------------------------------------------

  const lobby = AppLobby.connect("block-blast", {
    onState(newState) {
      state = newState;
      render();
    },
    onError: (message) => showError(message),
    onConnection(status) {
      $("connection").textContent = AppLobbyUI.connectionText(status, lobby.roomId);
    },
  });
  const showError = AppLobbyUI.errorBox($("error"));
  const renderButtons = AppLobbyUI.lobbyButtons(lobby, {
    join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back"),
  });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);
  const updateTurnAlert = AppLobbyUI.turnAlert($("main-board"));

  // --- Selection (which hand card is being placed) and keyboard ------------------

  let selection = null; // { uid, rotation, patch, turn } while placing a card
  let hover = null; // { pid, r, c } under the mouse on a board

  const game = () => state && state.game;
  const isMyTurn = () => Boolean(state && state.phase === "playing" && game() && game().turn === state.you);
  const hand = () => (state && state.private && state.private.hand) || [];
  const handCard = (uid) => hand().find((card) => card.uid === uid);
  const name = (pid) => game().names[pid] || pid;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  function select(uid) {
    if (!isMyTurn() || !handCard(uid)) return;
    selection = selection && selection.uid === uid ? null : { uid, rotation: 0, patch: false, turn: game().turnNumber };
    renderHand();
    updateGhost();
  }

  function rotate() {
    if (!selection || selection.patch) return;
    selection.rotation = (selection.rotation + 1) % 4;
    renderHand();
    updateGhost();
  }

  function togglePatch() {
    if (!selection) return;
    selection.patch = !selection.patch;
    renderHand();
    updateGhost();
  }

  function cancel() {
    selection = null;
    renderHand();
    updateGhost();
  }

  // Drop the selection when it no longer applies (turn passed, card gone).
  function checkSelection() {
    if (selection && (!isMyTurn() || selection.turn !== game().turnNumber || !handCard(selection.uid))) selection = null;
  }

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    if (target.closest && target.closest("input, textarea, select, [contenteditable]")) return;
    if (document.querySelector("dialog[open]")) return; // a window is open: Esc closes it natively
    if (!isMyTurn() || event.ctrlKey || event.metaKey || event.altKey) return;
    const key = event.key.toLowerCase();
    if (key === "r") rotate();
    else if (key === "p") togglePatch();
    else if (key === "escape") cancel();
    else if (/^[1-9]$/.test(key) && hand()[Number(key) - 1]) select(hand()[Number(key) - 1].uid);
    else return;
    event.preventDefault();
  });

  $("rotate").addEventListener("click", rotate);
  $("patch").addEventListener("click", togglePatch);
  $("cancel").addEventListener("click", cancel);
  $("end-turn").addEventListener("click", () => {
    selection = null;
    lobby.sendGame({ action: "end_turn" });
  });

  // --- Auto end turn -------------------------------------------------------------
  // A browser-only preference (sessionStorage, never sent). When it's on, the turn ends by itself
  // once your hand is empty and you can't afford anything in the market (after a short pause so the
  // last move shows).

  const AUTO_KEY = "block-blast:autoEnd";
  const AUTO_DELAY = 600; // ms
  let autoEndTurn = null; // turnNumber we already ended automatically
  try {
    $("auto-end").checked = sessionStorage.getItem(AUTO_KEY) === "1";
  } catch (error) { /* storage unavailable: starts off */ }
  $("auto-end").addEventListener("change", () => {
    try {
      sessionStorage.setItem(AUTO_KEY, $("auto-end").checked ? "1" : "0");
    } catch (error) { /* not remembered */ }
    maybeAutoEnd();
  });

  const canBuy = () => game().buysLeft > 0 && game().market.slots.some((slot) => slot && slot.price <= game().seats[state.you].gold);
  const nothingLeft = () => isMyTurn() && hand().length === 0 && !canBuy();
  const autoEndDue = () => $("auto-end").checked && nothingLeft() && autoEndTurn !== game().turnNumber;

  function maybeAutoEnd() {
    if (!autoEndDue()) return;
    const turn = game().turnNumber;
    autoEndTurn = turn;
    setTimeout(() => {
      // Re-check: the switch may be off now, or the turn may have moved on.
      if ($("auto-end").checked && nothingLeft() && game().turnNumber === turn) {
        selection = null;
        lobby.sendGame({ action: "end_turn" });
      } else {
        autoEndTurn = null;
      }
    }, AUTO_DELAY);
  }

  // --- Render --------------------------------------------------------------------

  let firstGameRender = true; // no animation on the first render after a reload
  let seenClear = 0; // lastClear.step already shown (per gameNumber)
  let seenGame = null;

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    $("help-open").hidden = inLobby;
    renderButtons();
    if (inLobby) {
      firstGameRender = true;
      selection = null;
      hover = null;
      $("hand-bar").hidden = true;
      $("main").classList.remove("with-hand");
      closeWindows();
      renderLobby();
    } else {
      if (seenGame !== state.gameNumber) {
        seenGame = state.gameNumber;
        firstGameRender = true;
      }
      renderGame();
      firstGameRender = false;
    }
  }

  function renderLobby() {
    updateTurnAlert(null);
    AppLobbyUI.renderPlayers($("players"), lobby, { afterName: () => null });
    AppLobbyUI.renderStart($("start"), lobby);
    AppLobbyUI.renderSpectators($("spectators"), state);
    renderSettings();
  }

  function renderGame() {
    const g = game();
    const finished = state.phase === "finished";
    const myTurn = isMyTurn();
    checkSelection();
    updateTurnAlert(myTurn ? `${state.gameNumber}:${g.turnNumber}` : null);

    $("result").hidden = !finished;
    if (finished) {
      const result = state.result || {};
      const winner = result.winner ? (result.winner === state.you ? "You win!" : `${name(result.winner)} wins!`) : "No winner.";
      $("result").textContent = `${winner} ${result.reason || ""}`;
    }
    if (finished) $("status-text").textContent = "Game over.";
    else if (myTurn) $("status-text").textContent = "Your turn: play cards, buy from the market, then End turn.";
    else if (g.seats[state.you] && g.seats[state.you].out) $("status-text").textContent = `You're out. ${name(g.turn)}'s turn.`;
    else $("status-text").textContent = `${name(g.turn)}'s turn.`;

    renderBoards();
    renderMarket();
    renderLog();
    renderHand();
    renderDeckWindow();
    updateGhost();
    maybeAutoEnd();
  }

  // --- Boards --------------------------------------------------------------------

  let boardCells = {}; // pid -> cell elements of that board (this render)
  let boardEls = {}; // pid -> board element

  function renderBoards() {
    const g = game();
    const mine = Boolean(g.seats[state.you]);
    const featured = mine ? state.you : g.turn || g.order[0];
    const start = g.order.indexOf(featured);
    const others = g.order.slice(start + 1).concat(g.order.slice(0, start));
    boardCells = {};
    boardEls = {};
    $("main-board").replaceChildren(seatPanel(featured, true));
    $("other-boards").replaceChildren(...others.map((pid) => seatPanel(pid, false)));
    flashClear();
  }

  function seatPanel(pid, big) {
    const g = game();
    const seat = g.seats[pid];
    const me = g.seats[state.you];
    const you = pid === state.you;
    const tags = [];
    if (pid === g.turn) tags.push(el("span", { className: "tag turn" }, "▶ Turn"));
    if (seat.left) tags.push(el("span", { className: "tag outtag" }, "Left"));
    else if (seat.out) tags.push(el("span", { className: "tag outtag" }, "Out"));
    if (me && !me.out && !you && me.target === pid) tags.push(el("span", { className: "tag target" }, "🎯 Your target"));
    if (me && !me.out && !you && !seat.out && me.target !== pid && state.phase === "playing") {
      const aim = el("button", { className: "aim small", textContent: "🎯 Aim here", title: "Your attacks hit this player" });
      aim.addEventListener("click", () => lobby.sendGame({ action: "aim", player: pid }));
      tags.push(aim);
    }
    const head = el("div", { className: "seat-head" },
      el("span", { className: "seat-name" }, name(pid) + (you ? " (you)" : "")),
      el("span", { className: "stat health", title: "Health" }, `♥ ${seat.health}`),
      el("span", { className: "stat gold", title: "Gold" }, `💰 ${seat.gold}`),
      // Optional resources only show once the player has some.
      seat.shield ? el("span", { className: "stat shield", title: "Shield: absorbs that much damage, then it's used up; drops by 1 at the start of their turn" }, `🛡 ${seat.shield}`) : "",
      seat.chapels ? el("span", { className: "stat chapels", title: "Card removals (from chapels)" }, `✝ ${seat.chapels}`) : "",
      seat.siege ? el("span", { className: "stat siege", title: `Siege: every ${g.rules.siegePerStrength} cleared give +1 strength` }, `⚙ ${seat.siege}`) : "",
      seat.strength ? el("span", { className: "stat strength", title: "Strength: adds this much to the total damage of each attack" }, `💪 ${seat.strength}`) : "",
    );
    const sub = el("div", { className: "seat-sub" },
      ...tags,
      seat.out ? "" : el("span", {}, seat.target ? `aims at ${seat.target === state.you ? "you" : name(seat.target)}` : ""),
      el("span", { title: "Hand · draw pile · discard pile" }, `✋${seat.hand} · ▤${seat.draw} · ♻${seat.discard}`),
      deckButton(pid),
    );
    // Players can drop cards on their own board, and playOn "opponent" cards on opponents' boards.
    const interactive = Boolean(me) && (you || !seat.out);
    const { element, cells } = Board.build(g, seat.board, {
      big,
      size: g.rules.boardSize,
      handlers: interactive ? boardHandlers(pid) : null,
    });
    boardCells[pid] = cells;
    boardEls[pid] = element;
    const classes = ["seat"];
    if (pid === g.turn) classes.push("current");
    if (seat.out) classes.push("out");
    return el("div", { className: classes.join(" ") }, head, sub, element);
  }

  function boardHandlers(pid) {
    return {
      onHover(r, c) {
        hover = { pid, r, c };
        updateGhost();
      },
      onLeave() {
        hover = null;
        updateGhost();
      },
      onClick: (r, c) => placeAt(pid, r, c),
      onRotate() {
        if (!selection || !dropsOn(pid)) return false;
        rotate();
        return true;
      },
    };
  }

  // Cards with playOn "opponent" (goblins) go on an opponent's board.
  function playsOnOpponent() {
    const card = selection && !selection.patch && handCard(selection.uid);
    return Boolean(card && game().cards[card.card].playOn === "opponent");
  }

  // Whether the selected card goes on pid's board: on opponents still in, or on yours.
  function dropsOn(pid) {
    if (!selection || !game() || !game().seats[pid]) return false;
    return playsOnOpponent() ? pid !== state.you && !game().seats[pid].out : pid === state.you;
  }

  // The selected card's layers in its current rotation (a patch is the server's 1x1 piece).
  function currentPiece() {
    if (!selection) return null;
    if (selection.patch) return game().rules.patch;
    const card = handCard(selection.uid);
    return card ? game().cards[card.card].rotations[selection.rotation] : null;
  }

  function placementOn(pid, r, c) {
    const g = game();
    return Board.placement(g, currentPiece(), g.seats[pid].board.tiles, g.rules.boardSize, r, c);
  }

  // Hover preview and the hint under the hand: toggles classes on the existing cells.
  function updateGhost() {
    for (const [pid, cells] of Object.entries(boardCells)) {
      Board.clearPreview(cells);
      boardEls[pid].classList.toggle("drop", dropsOn(pid));
    }
    const hint = $("hand-hint");
    if (!game()) {
      hint.textContent = "";
      return;
    }
    const card = selection && handCard(selection.uid);
    if (!card || !game().seats[state.you]) {
      hint.textContent = isMyTurn() ? `Pick a card (click or 1–${game().rules.handSize}), then click your board.` : "";
      return;
    }
    const cardName = game().cards[card.card].name;
    const label = selection.patch ? `a 1×1 tile (discarding ${cardName})` : cardName;
    if (!hover || !dropsOn(hover.pid)) {
      hint.textContent = playsOnOpponent()
        ? `${label}: click an opponent's board to drop it there. R / right-click / wheel rotates.`
        : `Placing ${label}. R / right-click / wheel rotates.`;
      return;
    }
    const place = placementOn(hover.pid, hover.r, hover.c);
    Board.showGhost(boardCells[hover.pid], game().rules.boardSize, game().seats[hover.pid].board.tiles, place);
    const where = hover.pid === state.you ? "" : ` on ${name(hover.pid)}'s board`;
    hint.textContent = place.fits ? `Click to place ${label}${where}.` : "It doesn't fit there.";
  }

  function placeAt(pid, r, c) {
    if (!selection || !isMyTurn() || !dropsOn(pid) || !currentPiece()) return;
    const { row, col, fits } = placementOn(pid, r, c);
    if (!fits) {
      showError("It doesn't fit there.");
      return;
    }
    let message;
    if (selection.patch) message = { action: "patch", uid: selection.uid, row, col };
    else {
      message = { action: "place", uid: selection.uid, rotation: selection.rotation, row, col };
      if (pid !== state.you) message.player = pid;
    }
    selection = null;
    lobby.sendGame(message);
  }

  // Clear animation: flash lastClear's cells once (not on the first render after a reload).
  function flashClear() {
    const clear = game().lastClear;
    const step = clear ? clear.step : 0;
    if (firstGameRender) {
      seenClear = step;
      return;
    }
    if (!clear || step <= seenClear) return;
    seenClear = step;
    const cells = boardCells[clear.pid];
    if (cells) Board.flash(cells, game().rules.boardSize, clear.cells);
  }

  // --- Market and log ------------------------------------------------------------
  // game.market: {type, label, canRemove, slots: [null | {uid, card, price}], deck}. The price is
  // the server's (slot position on the Conveyor Market, the card's cost on the Cost Market).
  // With canRemove, a card can be removed from the market instead of buying (uses the buy).

  function renderMarket() {
    const g = game();
    const market = g.market;
    const me = g.seats[state.you];
    const myTurn = isMyTurn();
    const used = g.buysLeft <= 0;
    const action = market.canRemove ? `${plural(g.rules.buysPerTurn, "buy")} or removal` : plural(g.rules.buysPerTurn, "buy");
    $("market-type").textContent = `· ${market.label}`;
    $("market-info").textContent = `${action} per turn · bonus deck: ${market.deck}`;
    $("market").replaceChildren(...market.slots.map((slot, i) => {
      if (!slot) {
        return el("div", { className: "market-empty" }, market.deck ? "Empty: refills when the turn ends" : "Empty (the bonus deck is used up)");
      }
      const cardName = g.cards[slot.card].name;
      const price = el("div", { className: "price" }, `💰 ${slot.price}`);
      const buy = el("button", { className: "small green", textContent: "Buy" });
      buy.disabled = !myTurn || !me || used || me.gold < slot.price;
      buy.title = !myTurn ? "Only on your turn"
        : used ? (market.canRemove ? "You've already bought or removed a card this turn" : `You've already bought ${plural(g.rules.buysPerTurn, "card")} this turn`)
        : me && me.gold < slot.price ? "Not enough gold" : "Goes to your discard pile";
      buy.addEventListener("click", () => lobby.sendGame({ action: "buy", slot: i }));
      const buttons = [buy];
      if (market.canRemove) {
        const remove = el("button", { className: "small plain remove", textContent: "Remove" });
        remove.disabled = !myTurn || !me || used;
        remove.title = !myTurn ? "Only on your turn"
          : used ? "You've already bought or removed a card this turn"
          : "Instead of buying: this card leaves the market and the game";
        remove.addEventListener("click", () => {
          if (!confirm(`Remove ${cardName} from the market? It leaves the game, and it uses your buy this turn.`)) return;
          lobby.sendGame({ action: "market_remove", slot: i });
        });
        buttons.push(remove);
      }
      return el("div", { className: "market-slot" }, Draw.cardFace(g, slot.card), price, ...buttons);
    }));
  }

  function renderLog() {
    const entries = game().log.slice().reverse();
    $("log").replaceChildren(...entries.map((entry) =>
      el("li", { className: entry.pid === state.you ? "mine" : "" }, entry.text)));
  }

  // --- Hand bar ------------------------------------------------------------------

  function renderHand() {
    const g = game();
    const seat = g && g.seats[state.you];
    const show = Boolean(state.private && state.private.hand) && state.phase === "playing" && Boolean(seat) && !seat.out;
    $("hand-bar").hidden = !show;
    $("main").classList.toggle("with-hand", show);
    if (!show) return;
    const myTurn = isMyTurn();
    $("pile-counts").textContent = `Draw pile ${seat.draw} · discard ${seat.discard}`;
    $("pile-counts").title = state.private.drawPile.length
      ? `In your draw pile: ${state.private.drawPile.map((id) => g.cards[id].name).join(", ")}`
      : "Your draw pile is empty: the discard pile is shuffled in when you next draw.";
    $("removals").textContent = seat.chapels ? `✝ ${plural(seat.chapels, "card removal")}` : "";
    $("hand").replaceChildren(...hand().map((card, i) => {
      const selected = selection && selection.uid === card.uid;
      const face = selected && selection.patch
        ? el("div", { className: "pcard" }, el("div", { className: "cname" }, "Patch 1×1"), Draw.miniShape(g, g.rules.patch),
            el("div", { className: "csyms" }, `discarding ${g.cards[card.card].name}`))
        : Draw.cardFace(g, card.card, selected ? selection.rotation : 0);
      face.append(el("div", { className: "key" }, myTurn ? `key ${i + 1}` : ""));
      if (selected) face.classList.add("selected");
      if (!myTurn) face.classList.add("disabled");
      face.addEventListener("click", () => select(card.uid));
      const slot = el("div", { className: "hand-slot" }, face);
      // Card removal (from chapels): usable any time, also on other players' turns.
      if (seat.chapels > 0) {
        const remove = el("button", { className: "delete small red", textContent: "✝ Delete",
          title: `Spend a card removal: ${g.cards[card.card].name} leaves your deck for good` });
        remove.addEventListener("click", () => {
          if (!confirm(`Remove ${g.cards[card.card].name} from your deck for good?`)) return;
          if (selection && selection.uid === card.uid) selection = null;
          lobby.sendGame({ action: "remove", uid: card.uid });
        });
        slot.append(remove);
      }
      return slot;
    }));
    if (!hand().length) $("hand").append(el("span", { className: "muted" }, `No cards left. End your turn to draw ${g.rules.handSize}.`));
    $("rotate").disabled = !selection || selection.patch;
    $("patch").disabled = !selection;
    $("patch").classList.toggle("on", Boolean(selection && selection.patch));
    $("cancel").disabled = !selection;
    $("end-turn").disabled = !myTurn;
  }

  // --- Windows: deck viewer, help legend -----------------------------------------
  // Native <dialog>s (index.html): Esc, the Close button or a click outside the window closes them.

  let deckOwner = null; // pid whose deck the deck window shows (kept up to date while open)

  for (const dialog of document.querySelectorAll("dialog.window")) {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog || event.target.closest("[data-close]")) dialog.close();
    });
  }
  $("deck-window").addEventListener("close", () => { deckOwner = null; });

  function closeWindows() {
    for (const dialog of document.querySelectorAll("dialog[open]")) dialog.close();
  }

  function deckButton(pid) {
    const button = el("button", { className: "small plain", textContent: "🂠 Deck",
      title: "See every card in this deck (sorted by cost)" });
    button.addEventListener("click", () => {
      deckOwner = pid;
      renderDeckWindow();
      $("deck-window").showModal();
    });
    return button;
  }

  // seats[pid].deck is every card the player owns, already sorted by the server (cost, then name);
  // copies of one card show once with ×n.
  function renderDeckWindow() {
    const g = game();
    if (deckOwner === null || !g || !g.seats[deckOwner]) return;
    const deck = g.seats[deckOwner].deck;
    $("deck-title").textContent = deckOwner === state.you ? "Your deck" : `${name(deckOwner)}'s deck`;
    $("deck-info").textContent = plural(deck.length, "card");
    const groups = [];
    for (const id of deck) {
      const last = groups[groups.length - 1];
      if (last && last.id === id) last.copies += 1;
      else groups.push({ id, copies: 1 });
    }
    $("deck-cards").replaceChildren(...groups.map(({ id, copies }) =>
      Draw.cardFace(g, id, 0, copies > 1 ? [el("div", { className: "copies" }, `×${copies}`)] : [])));
    if (!deck.length) $("deck-cards").append(el("span", { className: "muted" }, "No cards."));
  }

  // The legend comes from the state: tileTypes[code].help and symbolHelp[name].
  function renderHelp() {
    const g = game();
    if (!g) return;
    const row = (swatch, label, text) => el("div", { className: "legend-row" },
      swatch, el("span", { className: "legend-name" }, label), el("span", {}, text));
    $("legend-tiles").replaceChildren(...Object.values(g.tileTypes).map((type) =>
      row(el("span", { className: `legend-swatch t tile-${type.name}` }), type.name, type.help || "")));
    $("legend-symbols").replaceChildren(...Object.values(g.symbolTypes).map((symbol) =>
      row(el("span", { className: "legend-swatch" }, Draw.symbolEl(symbol)), symbol, (g.symbolHelp || {})[symbol] || "")));
  }

  $("help-open").addEventListener("click", () => {
    renderHelp();
    $("help-window").showModal();
  });

  // Keep the ? button just above the hand bar (its height changes with the hand and the window).
  const placeHelpButton = () => {
    const bar = $("hand-bar");
    $("help-open").style.bottom = `${(bar.hidden ? 0 : bar.offsetHeight) + 16}px`;
  };
  new ResizeObserver(placeHelpButton).observe($("hand-bar"));
})();
