/*
 * Bastion: the game page's controller. Renders from the state and holds no rules: where your
 * setup piece may go comes from state.private.setup, where a unit may go (and what it would do)
 * from .places, where a card may go from .targets, your current resolution prompt from .prompt.
 * Panels (status, details, prompt / Trade form, players, market, chronicle, card faces, deck
 * window) are drawn by panels.js, the board by board.js.
 *
 * Sections: helpers (+ the context panels.js gets); render (lobby / game, turn alert); board
 * (hover: outlines for legal tiles, the hovered tile in the details panel and a tip; clicks:
 * setup piece, place / take back a unit, play the selected blueprint or Orders card;
 * right-click: take back a unit or cancel the selection); hand bar (renderHand, clickCard:
 * blueprints and Orders select a card for a board click, Trade opens the Trade form, the rest
 * play at once); Done button; windows (deck, help).
 *
 * Interaction state: selection (a hand card: {uid, card} plus trade: true, to, give for Trade),
 * cleared outside your planning; hover [x, y].
 */
(() => {
  const { $, el } = AppDom;
  let state = null;
  let selection = null;
  let hover = null;

  const lobby = AppLobby.connect("bastion", {
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
  const updateTurnAlert = AppLobbyUI.turnAlert($("board-wrap"), { text: "Your move!" });
  const board = BastionBoard.create($("board"), {
    onHover(x, y) { hover = [x, y]; updateHover(); },
    onLeave() { hover = null; updateHover(); },
    onClick: clickCell,
    onRightClick: rightClick,
  });

  // --- helpers ----------------------------------------------------------------------------

  const game = () => state.game;
  const you = () => state.you;
  const mySeat = () => (state.game && state.game.seats[state.you]) || null;
  const priv = () => state.private || null;
  const cardOf = (id) => game().cards[id];
  const icon = (key) => game().icons[key] || "";
  const amounts = (obj) => Object.entries(obj || {}).filter(([, n]) => n).map(([k, n]) => `${n}${icon(k)}`).join(" ");
  const nameOf = (pid) => (state.game && state.game.names[pid]) || pid;
  const playing = () => state.phase === "playing" && Boolean(mySeat()) && Boolean(priv());
  const placing = () => playing() && game().phase === "place" && !mySeat().ready;
  const planning = () => playing() && game().phase === "plan" && !mySeat().ready;
  const mySetup = () => playing() && game().phase === "setup" && game().setup && game().setup.pid === you();
  const toCells = (keys) => keys.map((k) => k.split(",").map(Number));
  const targetsOf = (uid) => (priv() && (priv().targets || {})[String(uid)]) || null;
  const canPay = (cost) => {
    const seat = mySeat();
    return Object.entries(cost || {}).every(([k, n]) => (k === "decrees" ? seat.decrees : seat.stock[k] || 0) >= n);
  };
  const costOf = (id) => (cardOf(id).kind === "curse" ? cardOf(id).pay : cardOf(id).cost);

  function send(message) {
    lobby.sendGame(message);
  }

  const panels = BastionPanels.create({
    state: () => state, game, priv, you, icon, amounts, nameOf, send, playing,
    selection: () => selection,
    setTrade(trade) {
      selection = trade;
      refresh();
    },
    showDeck(pid) {
      panels.deckWindow(pid);
      $("deck-window").dataset.pid = pid;
      $("deck-window").showModal();
    },
  });

  // --- render -------------------------------------------------------------------------------

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    renderButtons();
    if (inLobby) {
      selection = null;
      $("bar").hidden = true;
      $("help-button").hidden = true;
      $("main").classList.remove("with-bar");
      updateTurnAlert(null);
      document.querySelectorAll("dialog[open]").forEach((d) => d.close());
      AppLobbyUI.renderPlayers($("players"), lobby, { afterName: () => null });
      AppLobbyUI.renderStart($("start"), lobby);
      AppLobbyUI.renderSpectators($("spectators"), state);
      renderSettings();
      return;
    }
    renderGame();
  }

  function renderGame() {
    const g = game();
    const finished = state.phase === "finished";
    checkSelection();
    board.build(g, you());
    $("result").hidden = !finished;
    if (finished && state.result) $("result").textContent = state.result.reason || "The game is over.";
    panels.status();
    panels.seats();
    panels.market();
    panels.log();
    renderDone();
    renderHand();
    updateHover();
    if ($("deck-window").open) panels.deckWindow($("deck-window").dataset.pid);
    $("help-button").hidden = false;
    const p = priv();
    const needed = mySetup() || placing() || planning() || Boolean(p && p.prompt);
    updateTurnAlert(!finished && needed ? `${state.gameNumber}:${g.step}` : null);
  }

  // Drop a selection that no longer applies (new state).
  function checkSelection() {
    if (!selection) return;
    if (!planning() || !priv().hand.some((c) => c.uid === selection.uid)) selection = null;
  }

  function refresh() {
    renderHand();
    updateHover();
  }

  // --- board ---------------------------------------------------------------------------------

  function showTip(text) {
    const tip = $("tip");
    const r = text && hover ? board.cellRect(hover[0], hover[1]) : null;
    if (!r) {
      tip.hidden = true;
      return;
    }
    tip.textContent = text;
    tip.hidden = false;
    const wide = tip.offsetWidth;
    const left = r.right + 6 + wide > window.innerWidth ? r.left - 6 - wide : r.right + 6;
    tip.style.left = `${Math.max(4, left)}px`;
    tip.style.top = `${r.top - 2}px`;
  }

  function updateHover() {
    board.clearMarks();
    if (!state || !state.game) return;
    const g = game();
    const p = priv();
    const key = hover ? `${hover[0]},${hover[1]}` : null;
    let tip = null;
    if (mySetup()) {
      const spots = new Set(p.setup);
      board.mark(toCells(p.setup), "spot");
      if (hover) {
        board.mark([hover], spots.has(key) ? "hl" : "bad");
        tip = spots.has(key) ? `Place your ${g.kinds[g.setup.kind].name} here` : null;
      }
    } else if (placing()) {
      const seat = mySeat();
      const places = p.places || {};
      const open = Object.entries(places).filter(([, j]) => (j.soldier ? seat.freeSoldiers : seat.free) > 0).map(([k]) => k);
      board.mark(toCells(open), "spot");
      const unit = key ? (g.units || {})[key] : null;
      if (hover && unit && unit.pid === you() && unit.new) tip = "Your unit · click or right-click: take it back";
      else if (hover && places[key]) {
        const place = places[key];
        const left = place.soldier ? seat.freeSoldiers : seat.free;
        tip = left > 0 ? `Click: ${place.text}` : `No ${place.soldier ? "soldiers" : "units"} left to place`;
        board.mark([hover], "hl");
      }
    } else if (selection && !selection.trade) {
      const targets = targetsOf(selection.uid);
      const keys = Array.isArray(targets) ? targets : Object.keys(targets || {});
      board.mark(toCells(keys), "spot");
      if (hover) {
        const ok = keys.includes(key);
        board.mark([hover], ok ? "ghost" : "bad");
        if (ok) tip = Array.isArray(targets) ? `Plan the ${g.kinds[cardOf(selection.card).structure].name} here` : targets[key];
      }
    }
    if (p && p.prompt && g.phase === "resolve") board.mark([[p.prompt.x, p.prompt.y]], "prompt");
    showTip(tip);
    panels.details(hover ? hover[0] : null, hover ? hover[1] : null);
    panels.prompt();
  }

  function clickCell(x, y) {
    if (!state || !state.game || !playing()) return;
    const g = game();
    const p = priv();
    const key = `${x},${y}`;
    if (g.phase === "setup") {
      if (!mySetup()) return showError(g.setup ? `${nameOf(g.setup.pid)} is placing.` : "Setup is over.");
      if (!p.setup.includes(key)) return showError("Pick one of the outlined tiles.");
      return send({ action: "setup", x, y });
    }
    if (g.phase === "place") {
      if (!placing()) return showError("You're done: click Not done to change your placements.");
      const unit = (g.units || {})[key];
      if (unit && unit.pid === you() && unit.new) return send({ action: "unplace", x, y });
      const place = (p.places || {})[key];
      if (!place) return showError(unit ? "There's already a unit there." : "Units go on the outlined tiles.");
      const seat = mySeat();
      if ((place.soldier ? seat.freeSoldiers : seat.free) <= 0) return showError(`You have no ${place.soldier ? "soldiers" : "units"} left to place.`);
      return send({ action: "place", x, y });
    }
    if (selection && !selection.trade) {
      const targets = targetsOf(selection.uid);
      const keys = Array.isArray(targets) ? targets : Object.keys(targets || {});
      if (!keys.includes(key)) return showError("Pick one of the outlined tiles.");
      send({ action: "play", uid: selection.uid, x, y });
      selection = null;
      refresh();
    }
  }

  function rightClick(x, y) {
    if (selection) return cancel();
    if (!state || !state.game || x === null || !placing()) return;
    const unit = (game().units || {})[`${x},${y}`];
    if (unit && unit.pid === you() && unit.new) send({ action: "unplace", x, y });
  }

  function cancel() {
    if (!selection) return;
    selection = null;
    refresh();
  }

  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea, select")) return;
    if (e.key === "Escape" && state && state.game) cancel();
  });

  // --- hand bar ---------------------------------------------------------------------------------

  function renderHand() {
    const seat = mySeat();
    const p = priv();
    const show = Boolean(seat && p);
    $("bar").hidden = !show;
    $("main").classList.toggle("with-bar", show);
    if (!show) return;
    const g = game();
    $("bar-info").textContent = planning()
      ? `${icon("decrees")} ${seat.decrees} decree${seat.decrees === 1 ? "" : "s"} left. Click a card to play it.`
      : g.phase === "plan" ? "Done: waiting for the others." : "Cards are played in the planning phase.";
    $("cards").replaceChildren(...p.hand.map((c) => {
      const card = cardOf(c.card);
      const targets = targetsOf(c.uid);
      const empty = (card.kind === "build" || card.targeted) && !(targets && (Array.isArray(targets) ? targets.length : Object.keys(targets).length));
      const off = !planning() || !canPay(costOf(c.card)) || empty;
      const node = panels.cardEl(c.card, { off, selected: Boolean(selection && selection.uid === c.uid) });
      if (planning() && empty) node.title = card.kind === "build" ? "No room for it within your reach" : "None of your buildings has a unit on it";
      node.addEventListener("click", () => clickCard(c));
      return node;
    }));
  }

  function clickCard(instance) {
    if (!planning()) {
      if (playing()) showError(game().phase === "plan" ? "You're done: click Not done to keep planning." : "Cards are played in the planning phase.");
      return;
    }
    const card = cardOf(instance.card);
    if (selection && selection.uid === instance.uid) return cancel();
    if (!canPay(costOf(instance.card))) return showError(`${card.name} needs ${amounts(costOf(instance.card))}.`);
    if (card.trade) selection = { uid: instance.uid, card: instance.card, trade: true, to: null, give: {} };
    else if (card.kind === "build" || card.targeted) selection = { uid: instance.uid, card: instance.card };
    else {
      selection = null;
      send({ action: "play", uid: instance.uid });
    }
    refresh();
  }

  // --- Done -----------------------------------------------------------------------------------

  function renderDone() {
    const button = $("done");
    const g = game();
    const seat = mySeat();
    button.hidden = !seat || state.phase !== "playing";
    if (button.hidden) return;
    if (g.phase === "place" || g.phase === "plan") {
      const label = g.phase === "place" ? "placing" : "planning";
      button.textContent = seat.ready ? "Not done" : `Done ${label}`;
      button.className = seat.ready ? "plain" : "green";
      button.disabled = false;
    } else {
      button.textContent = g.phase === "setup" ? "Setup" : seat.prompts ? "Answer your prompts" : "Waiting for the others";
      button.className = "plain";
      button.disabled = true;
    }
  }

  $("done").addEventListener("click", () => {
    if (!playing()) return;
    const g = game();
    if (g.phase === "place" || g.phase === "plan") {
      selection = null;
      send({ action: "ready", done: !mySeat().ready });
    }
  });

  // --- windows --------------------------------------------------------------------------------

  $("help-button").addEventListener("click", () => $("help-window").showModal());
  document.querySelectorAll("dialog [data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));
})();
