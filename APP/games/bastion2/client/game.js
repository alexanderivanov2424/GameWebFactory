/*
 * Bastion 2: the game page's controller. Renders from the state and holds no rules: where you may
 * place comes from state.private.spots, why a card / action / purchase is refused from the `why`
 * strings the server sends. Panels are drawn by hud.js, the map by map.js.
 *
 * Sections: helpers; render (lobby / game layer, turn alert, centring the camera); map (hover tip
 * and ghost, clicks: setup piece or the selected structure card; right-click: take back a pending
 * build or cancel); hand (renderHand, clickCard: resources and actions play at once, structures
 * select for a map click, upkeep asks how to pay, picking cards for a discard payment or a bundle);
 * prompt line; End turn (with the cards marked 📌 to keep); windows.
 *
 * Interaction state: selection = null | {mode: "build", uid, card} | {mode: "upkeep", uid} |
 * {mode: "discard", uid, picks: [uid]} | {mode: "bundle", cell: "x,y", picks: [uid]}; cleared
 * when it's no longer your turn or the card is gone. keep: uids marked 📌 (per game number).
 */
(() => {
  const { $, el } = AppDom;
  let state = null;
  let selection = null;
  let keep = { game: null, uids: new Set() };
  let hover = null;
  let centred = "";

  const lobby = AppLobby.connect("bastion2", {
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
  const updateTurnAlert = AppLobbyUI.turnAlert($("bottom"), { text: "Your turn!" });

  // --- helpers ----------------------------------------------------------------------------

  const game = () => state.game;
  const you = () => state.you;
  const priv = () => state.private || null;
  const seat = () => (state.game && state.game.seats[state.you]) || null;
  const nameOf = (pid) => (state.game && state.game.names[pid]) || pid;
  const inGame = () => Boolean(state && state.game && (state.phase === "playing" || state.phase === "finished"));
  const myTurn = () => inGame() && state.phase === "playing" && Boolean(priv()) && !priv().turn;
  const send = (message) => lobby.sendGame(message);
  const cellOf = (key) => key.split(",").map(Number);
  const handCard = (uid) => (priv() ? priv().hand.find((c) => c.uid === uid) : null);

  const hud = Bastion2Hud.create({
    game, priv, you, seat, send, nameOf,
    selection: () => selection,
    startBundle(cell) {
      selection = selection && selection.mode === "bundle" && selection.cell === cell ? null : { mode: "bundle", cell, picks: [] };
      renderGame();
    },
    hoverCell(key) {
      if (key) map.setHover(...cellOf(key));
      else map.setHover(null, null);
    },
  });

  function focus() {
    const left = $("left").getBoundingClientRect();
    const right = $("right").getBoundingClientRect();
    const bottom = $("bottom").getBoundingClientRect();
    const map = $("map").getBoundingClientRect();
    return { x: (left.right + right.left) / 2 - map.left, y: (left.top + bottom.top) / 2 - map.top };
  }

  const map = Bastion2Map.create($("map"), $("world"), {
    focus,
    onHover(x, y, event) {
      hover = x === null ? null : [x, y];
      updateHover(event);
    },
    onClick: clickCell,
    onRightClick: rightClick,
  });

  // --- render -----------------------------------------------------------------------------

  function render() {
    if (!state) return;
    const playing = inGame();
    document.body.classList.toggle("in-game", playing);
    $("lobby").hidden = state.phase !== "lobby";
    $("game").hidden = !playing;
    renderButtons();
    if (state.phase === "lobby") {
      AppLobbyUI.renderPlayers($("players"), lobby);
      AppLobbyUI.renderStart($("start"), lobby);
      AppLobbyUI.renderSpectators($("spectators"), state);
      renderSettings();
      selection = null;
      hideTip();
      return;
    }
    if (playing) renderGame();
  }

  function renderGame() {
    const g = game();
    const p = priv();
    if (keep.game !== state.gameNumber) keep = { game: state.gameNumber, uids: new Set() };
    if (p) keep.uids = new Set([...keep.uids].filter((uid) => handCard(uid)));
    checkSelection();
    $("bottom").hidden = !p;
    map.build(g, you());
    recentre();
    renderStatus();
    hud.perm();
    hud.uses();
    hud.market();
    hud.seats();
    hud.log();
    hud.playArea();
    hud.actionsCircle();
    renderHand();
    renderPrompt();
    renderEnd();
    updateSpots();
    updateHover();
    $("result").hidden = state.phase !== "finished";
    $("result").textContent = state.phase === "finished" ? "The game is over." : "";
    let alertId = null;
    if (p && state.phase === "playing") {
      if (p.setup) alertId = `${state.gameNumber}:setup`;
      else if (!p.turn) alertId = `${state.gameNumber}:${g.round}`;
    }
    updateTurnAlert(alertId);
  }

  function checkSelection() {
    if (!selection) return;
    if (!myTurn()) selection = null;
    else if (selection.uid !== undefined && !handCard(selection.uid)) selection = null;
    else if (selection.mode === "bundle" && !(priv().uses[selection.cell] && !priv().uses[selection.cell].why)) selection = null;
    if (selection && selection.picks) selection.picks = selection.picks.filter((uid) => handCard(uid));
  }

  function recentre(force = false) {
    const g = game();
    const castle = Object.entries(g.structures).find(([, s]) => s.owner === you() && s.kind === "castle");
    const key = `${state.gameNumber}:${castle ? castle[0] : ""}`;
    if (!force && key === centred) return;
    centred = key;
    if (castle) map.centerOn(...cellOf(castle[0]));
    else {
      const [x0, y0, x1, y1] = g.bounds;
      map.centerOn(Math.floor((x0 + x1) / 2), Math.floor((y0 + y1) / 2));
    }
  }

  function renderStatus() {
    const g = game();
    const parts = [];
    if (g.stage === "setup") parts.push(el("span", { className: "round", textContent: "Setup" }));
    else parts.push(el("span", { className: "round", textContent: `Round ${g.round}` }));
    parts.push(el("span", { className: "muted", textContent: g.mode === "order" ? "one at a time" : "everyone at once" }));
    parts.push(el("span", { className: "todo", textContent: todo() }));
    $("status").replaceChildren(...parts);
  }

  function todo() {
    const g = game();
    const p = priv();
    if (state.phase === "finished") return "The game is over.";
    if (!p) return "You're watching.";
    if (g.stage === "setup") {
      if (p.setup) return `Place your ${g.cards[p.setup].name}: click a glowing tile.`;
      const waiting = g.order.filter((pid) => g.seats[pid].setup < g.setupPieces.length).map(nameOf);
      return `Waiting for ${AppDom.listNames(waiting)} to place their city.`;
    }
    if (!p.turn) return "Your turn: play cards, build, buy, then End turn.";
    if (g.mode === "order") return `${nameOf(g.current)}'s turn.`;
    const waiting = g.order.filter((pid) => !g.seats[pid].done).map(nameOf);
    return `Turn ended. Waiting for ${AppDom.listNames(waiting)}.`;
  }

  // --- map --------------------------------------------------------------------------------

  function placing() {
    const p = priv();
    if (!p || state.phase !== "playing") return null;
    if (p.setup) return { icon: game().cards[p.setup].icon, name: game().cards[p.setup].name };
    if (selection && selection.mode === "build") return { icon: game().cards[selection.card].icon, name: game().cards[selection.card].name };
    return null;
  }

  function updateSpots() {
    map.setSpots(placing() ? priv().spots : []);
  }

  function updateHover(event) {
    if (!hover) {
      map.setGhost(null);
      map.setHover(null, null);
      hideTip();
      return;
    }
    const key = `${hover[0]},${hover[1]}`;
    const g = game();
    const place = placing();
    const isSpot = place && priv().spots.includes(key);
    map.setGhost(isSpot ? hover[0] : null, hover[1], place ? place.icon : "");
    map.setHover(...hover);
    const s = g.structures[key];
    let tip = "";
    if (s) {
      const card = g.cards[s.kind];
      tip = `${card.icon} ${card.name} — ${nameOf(s.owner)}${s.pending ? " (being built)" : ""}\n${card.text}`;
      if (s.pending && s.owner === you() && !priv().turn) tip += "\nRight-click to take it back.";
    } else if (isSpot) {
      tip = `Place your ${place.name} here.`;
    }
    if (tip) showTip(tip, event);
    else hideTip();
  }

  function clickCell(x, y) {
    const p = priv();
    if (!p || state.phase !== "playing") return;
    const key = `${x},${y}`;
    if (p.setup) {
      if (p.spots.includes(key)) send({ action: "setup", x, y });
      return;
    }
    if (selection && selection.mode === "build") {
      if (!p.spots.includes(key)) return showError("Build next to one of your buildings (the glowing tiles).");
      send({ action: "play", uid: selection.uid, x, y });
      selection = null;
      renderGame();
    }
  }

  function rightClick(x, y) {
    const p = priv();
    const key = `${x},${y}`;
    if (p && p.pending[key]) {
      send({ action: "unbuild", x, y });
      return;
    }
    if (selection) {
      selection = null;
      renderGame();
    }
  }

  // --- hand -------------------------------------------------------------------------------

  function renderHand() {
    const p = priv();
    if (!p) return $("hand").replaceChildren();
    $("hand").replaceChildren(...p.hand.map((c) => {
      const picking = selection && selection.picks;
      const node = hud.cardEl(c.card, {
        off: Boolean(c.why) && !picking, temp: c.temp, why: c.why,
        selected: Boolean(selection && selection.uid === c.uid),
        picked: Boolean(picking && selection.picks.includes(c.uid)),
        kept: keep.uids.has(c.uid),
      });
      const pin = el("button", { className: "keep", textContent: "📌", title: "Keep this card in your hand when your turn ends", disabled: Boolean(p.turn) });
      pin.addEventListener("click", (e) => {
        e.stopPropagation();
        if (keep.uids.has(c.uid)) keep.uids.delete(c.uid);
        else keep.uids.add(c.uid);
        renderHand();
        renderEnd();
      });
      node.append(pin);
      node.addEventListener("click", () => clickCard(c));
      return node;
    }));
  }

  function clickCard(c) {
    if (!myTurn()) return;
    const card = game().cards[c.card];
    if (selection && selection.picks) {
      if (selection.mode === "discard" && c.uid === selection.uid) return;
      if (selection.mode === "bundle" && card.kind !== "resource") return showError("Only resource cards can be bundled.");
      const i = selection.picks.indexOf(c.uid);
      if (i >= 0) selection.picks.splice(i, 1);
      else selection.picks.push(c.uid);
      return renderGame();
    }
    if (selection && selection.uid === c.uid) {
      selection = null;
      return renderGame();
    }
    if (card.kind === "upkeep") {
      selection = { mode: "upkeep", uid: c.uid };
      return renderGame();
    }
    if (c.why) return showError(c.why);
    if (card.kind === "structure") {
      selection = { mode: "build", uid: c.uid, card: c.card };
      return renderGame();
    }
    selection = null;
    send({ action: "play", uid: c.uid });
  }

  // --- prompt line ------------------------------------------------------------------------

  function button(text, onClick, { why = "", cls = "" } = {}) {
    const b = el("button", { textContent: text, className: cls, disabled: Boolean(why), title: why });
    b.addEventListener("click", onClick);
    return b;
  }

  function cancel() {
    selection = null;
    renderGame();
  }

  function renderPrompt() {
    const g = game();
    const p = priv();
    const box = $("prompt");
    const parts = [];
    const cancelButton = () => button("Cancel", cancel, { cls: "plain" });
    if (selection && selection.mode === "build") {
      const card = g.cards[selection.card];
      parts.push(el("span", { textContent: `Building a ${card.name} (${hud.amounts(card.cost)}): click a glowing tile next to your buildings.` }), cancelButton());
    } else if (selection && selection.mode === "upkeep") {
      const c = handCard(selection.uid);
      const card = g.cards[c.card];
      parts.push(el("b", { textContent: `${card.icon} ${card.name}:` }));
      if (Object.keys(card.pay).length) {
        parts.push(button(`Pay ${hud.amounts(card.pay)}`, () => {
          send({ action: "play", uid: c.uid, option: "pay" });
          selection = null;
        }, { why: c.pay }));
      }
      if (card.discard) {
        parts.push(button(`Discard ${card.discard} other cards`, () => {
          selection = { mode: "discard", uid: c.uid, picks: [] };
          renderGame();
        }, { why: c.discard }));
      }
      parts.push(cancelButton());
    } else if (selection && selection.mode === "discard") {
      const card = g.cards[handCard(selection.uid).card];
      const n = selection.picks.length;
      parts.push(el("span", { textContent: `Pick ${card.discard} cards to discard for the ${card.name} (${n}/${card.discard}).` }));
      parts.push(button("Discard them", () => {
        send({ action: "play", uid: selection.uid, option: "discard", cards: selection.picks });
        selection = null;
      }, { why: n === card.discard ? "" : `Pick ${card.discard} cards.`, cls: "green" }), cancelButton());
    } else if (selection && selection.mode === "bundle") {
      const s = g.structures[selection.cell];
      const action = g.cards[s.kind].action;
      const totals = {};
      for (const uid of selection.picks) {
        const card = g.cards[handCard(uid).card];
        totals[card.resource] = (totals[card.resource] || 0) + card.value;
      }
      const kinds = Object.keys(totals);
      const total = kinds.length === 1 ? totals[kinds[0]] : 0;
      let why = "";
      if (!selection.picks.length) why = "Pick resource cards.";
      else if (kinds.length > 1) why = "Pick cards of one resource.";
      else if (!action.bundle.includes(total)) why = `They must add up to ${action.bundle.join(" or ")}.`;
      parts.push(el("span", { textContent: `${action.name}: pick resource cards of one kind worth ${action.bundle.join(" or ")}. Picked: ${hud.amounts(totals) || "nothing"}.` }));
      parts.push(button("Bundle", () => {
        const [x, y] = cellOf(selection.cell);
        send({ action: "use", x, y, cards: selection.picks });
        selection = null;
      }, { why, cls: "green" }), cancelButton());
    } else if (p && state.phase === "playing") {
      parts.push(el("span", { textContent: hint() }));
    }
    box.className = selection ? "" : "idle";
    box.replaceChildren(...parts);
  }

  function hint() {
    const p = priv();
    if (p.setup) return "Setup: place your city on the map. Drag to pan, wheel to zoom.";
    if (p.turn) return p.turn;
    return "Click cards to play them. 📌 keeps a card for next turn. Drag the map to pan, wheel to zoom.";
  }

  // --- end turn ---------------------------------------------------------------------------

  function renderEnd() {
    const p = priv();
    if (!p) return;
    const g = game();
    const end = $("end-turn");
    end.disabled = Boolean(p.turn) || Boolean(p.setup) || g.stage !== "play";
    end.textContent = p.turn && g.stage === "play" ? "Waiting…" : "End turn";
    const unpaid = p.hand.filter((c) => !keep.uids.has(c.uid) && g.cards[c.card].kind === "upkeep");
    const notes = [];
    if (!p.turn && unpaid.length) {
      const names = unpaid.map((c) => g.cards[c.card].name);
      notes.push(`Unpaid, will be discarded: ${names.join(", ")} (see the card for the cost).`);
    }
    const s = seat();
    $("end-note").replaceChildren(
      el("div", { textContent: notes.join(" ") }),
      el("div", { className: "muted", style: "color: var(--gwf-muted)", textContent: s ? `Draw ${s.draw} · discard ${s.discard}` : "" }),
    );
  }

  $("end-turn").addEventListener("click", () => {
    const p = priv();
    if (!p) return;
    send({ action: "end", keep: p.hand.filter((c) => keep.uids.has(c.uid)).map((c) => c.uid) });
    keep.uids = new Set();
    selection = null;
  });

  // --- tips, keys, windows ----------------------------------------------------------------

  function showTip(text, event) {
    const tip = $("tip");
    tip.hidden = false;
    tip.replaceChildren(...text.split("\n").map((line, i) => el(i ? "div" : "b", { textContent: line })));
    if (event) {
      tip.style.left = `${Math.min(event.clientX + 16, window.innerWidth - 310)}px`;
      tip.style.top = `${event.clientY + 16}px`;
    }
  }

  function hideTip() {
    $("tip").hidden = true;
  }

  document.addEventListener("keydown", (e) => {
    if (e.target.closest && e.target.closest("input, textarea, select")) return;
    if (e.key === "Escape" && selection) cancel();
    if ((e.key === "c" || e.key === "C") && inGame()) recentre(true);
  });

  $("center-button").addEventListener("click", () => recentre(true));
  $("deck-button").addEventListener("click", () => {
    hud.deckWindow();
    $("deck-window").showModal();
  });
  $("help-button").addEventListener("click", () => $("help-window").showModal());
  for (const close of document.querySelectorAll("[data-close]")) {
    close.addEventListener("click", () => close.closest("dialog").close());
  }
})();
