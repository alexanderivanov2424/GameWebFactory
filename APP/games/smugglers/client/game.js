/*
 * Smugglers: the game page. The board itself is drawn by board.js (SmugglersBoard).
 *
 * render() -> renderLobby() or renderGame(), which calls one render* per area: status bar,
 * prompt (loading cargo, inspections, Interpol's targeting steps), contract tiles (above the map;
 * click one to pick up its cargo), scoreboard + round (side), player boards (below the map, in
 * turn order: ship tiles for smugglers, play area + market for Interpol), log, hand bar; then
 * board.highlight() for the current mode.
 * Modes (reset when they no longer apply): selectedShip (a smuggler picked a ship to move),
 * targeting (Interpol playing a piece or Repeat card: copy -> piece -> spot),
 * loadMarks (the cards marked load/discard while loading cargo). Escape cancels.
 * The server sends the rules' answers (where each ship can go, where each piece may go), so
 * this file only shows them and sends choices.
 */
(() => {
  const { $, el, listNames } = AppDom;
  let state = null;
  let lastGame = null;
  let selectedShip = null;
  let targeting = null;   // { uid, cardId, copy?, piece?, to? }
  let loadMarks = {};     // uid -> "load" | "discard"
  let loadKey = null;     // which pickup loadMarks belong to
  let declared = null;

  const lobby = AppLobby.connect("smugglers", {
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
  const updateTurnAlert = AppLobbyUI.turnAlert($("board"));
  const board = SmugglersBoard.create($("board"), { onNode, onShip, onPiece });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && (selectedShip || targeting)) cancel();
  });

  function send(message) {
    lobby.sendGame(message);
  }

  function cancel() {
    selectedShip = null;
    targeting = null;
    if (state) render();
  }

  // --- Helpers ------------------------------------------------------------------------------

  const game = () => state.game;
  const playing = () => state.phase === "playing";
  const isCop = () => game().interpol === state.you;
  // My normal turn: no inspection or loading waiting.
  const myTurn = () => playing() && game().turn === state.you && !game().inspection && !game().loading;

  function placeName(node) {
    const planet = game().board.planets[node];
    return planet ? planet.name : "deep space";
  }

  function planetChip(node) {
    const planet = game().board.planets[node];
    if (!planet) return el("span", { className: "muted" }, "deep space");
    return el("span", { className: "planet-chip" },
      el("span", { className: "disc", style: `background:${planet.color}` }), planet.name);
  }

  function goodChip(goodId) {
    const good = game().goods[goodId];
    if (!good) return el("span", {}, "?");
    return el("span", {
      className: `good-chip${good.legal ? "" : " illegal"}`, style: `background:${good.color}`,
      title: good.legal ? `${good.name}: ${good.value} per card` : `${good.name}: illegal, worth ${good.value}, penalty ${good.penalty}`,
    }, `${good.name} ${good.value}`);
  }

  function who(pid) {
    const g = game();
    const color = pid === g.interpol ? "#2962ff" : g.smugglers[pid]?.color || "#999";
    const label = (g.names[pid] || "?") + (pid === state.you ? " (you)" : "");
    return el("span", { className: "who" }, el("span", { className: "swatch", style: `background:${color}` }), label);
  }

  function goodCard(card, extraClass = "") {
    const good = game().goods[card.card];
    return el("div", {
      className: `gcard${good.legal ? "" : " illegal"} ${extraClass}`, style: `background:${good.color}`, title: good.text,
    },
    el("div", { className: "title" }, good.name),
    el("div", { className: "value" }, String(good.value)));
  }

  function copCard(cardId, props = {}, foot = null) {
    const card = game().cards[cardId];
    return el(props.onclick ? "button" : "div", { className: `icard ${card.kind}`, ...props },
      el("div", { className: "title" }, el("span", {}, card.name), el("span", { className: "cost" }, String(card.cost))),
      el("div", {}, card.text),
      foot || "");
  }

  // --- Render -------------------------------------------------------------------------------

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    renderButtons();
    if (inLobby) renderLobby();
    else renderGame();
  }

  function renderLobby() {
    updateTurnAlert(null);
    lastGame = null;
    selectedShip = targeting = null;
    $("hand-bar").hidden = true;
    document.querySelector("main").classList.remove("with-hand");
    AppLobbyUI.renderPlayers($("players"), lobby, { afterName: () => null });
    AppLobbyUI.renderStart($("start"), lobby);
    AppLobbyUI.renderSpectators($("spectators"), state);
    renderSettings();
  }

  function renderGame() {
    const g = game();
    resetModes();
    if (g !== lastGame) {
      board.draw(g, state.you);
      lastGame = g;
    }
    const inspection = g.inspection;
    updateTurnAlert(playing() && g.actor === state.you
      ? `${state.gameNumber}:${g.turnNumber}:${inspection ? inspection.ship + inspection.stage : ""}` : null);
    renderResult();
    renderStatus();
    renderPrompt();
    renderContracts();
    renderPeople();
    renderPlayerBoards();
    renderLog();
    renderHand();
    renderHighlights();
  }

  function resetModes() {
    const reach = state.private?.reach || {};
    if (selectedShip && (!myTurn() || !reach[selectedShip])) selectedShip = null;
    if (targeting) {
      const stillThere = (state.private?.hand || []).some((c) => c.uid === targeting.uid);
      if (!myTurn() || !isCop() || !stillThere) targeting = null;
    }
    const loading = game().loading;
    const key = loading && loading.pid === state.you ? `${state.gameNumber}:${game().turnNumber}:${loading.ship}` : null;
    if (key !== loadKey) {
      loadKey = key;
      loadMarks = {};
      declared = loading ? game().contracts[loading.contract]?.good : null;
    }
  }

  function renderHighlights() {
    const reach = selectedShip ? state.private.reach[selectedShip] || {} : {};
    let targets = [];
    if (targeting?.piece && !targeting.to) targets = state.private.targets[targeting.cardId]?.[targeting.piece] || [];
    board.highlight({ reach, targets, ship: selectedShip, piece: targeting?.piece || null });
  }

  function renderResult() {
    const result = state.result;
    $("result").hidden = !result;
    if (!result) return;
    const g = game();
    const winners = result.winners || [];
    const headline = winners.length === 0 ? "Nobody wins."
      : winners.includes(g.interpol) ? `Interpol (${g.names[g.interpol]}) wins!`
        : `${listNames(winners.map((p) => g.names[p]))} win${winners.length === 1 ? "s" : ""}!`;
    const scores = Object.entries(result.credits || {}).sort((a, b) => b[1] - a[1])
      .map(([pid, credits]) => `${g.names[pid]} ${credits}`);
    $("result").replaceChildren(
      el("div", {}, el("b", {}, headline), " ", result.reason || ""),
      el("div", { className: "small muted" }, `Credits: ${scores.join(", ")} · Interpol's score: ${result.interpolScore}`));
  }

  function renderStatus() {
    const g = game();
    const parts = [];
    if (playing()) parts.push(el("span", {}, "Turn: ", who(g.turn)));
    if (state.private?.role) parts.push(el("span", {}, "You are ", el("b", {}, isCop() ? "Interpol" : "a smuggler")));
    let hint = "";
    if (myTurn() && !isCop()) {
      hint = selectedShip ? "Click a highlighted spot (yellow dashes: a patrol or checkpoint stops you there for inspection). Esc cancels."
        : "Click one of your ships to move it, or a glowing contract to pick up its cargo.";
    } else if (myTurn()) {
      hint = targeting ? "" : "Play cards from your hand, buy one card from the market, then end your turn.";
    }
    parts.push(el("span", { className: "hint" }, hint), el("span", { className: "spacer" }));
    if (myTurn()) {
      parts.push(el("button", { className: "green", onclick: () => send({ action: "endTurn" }) }, "End turn"));
    }
    $("status").replaceChildren(...parts);
  }

  // --- Prompts: loading cargo, inspections, Interpol targeting -------------------------------

  function renderPrompt() {
    const g = game();
    const box = $("prompt");
    if (!playing()) return box.replaceChildren();
    if (g.inspection) return box.replaceChildren(...inspectionPrompt(g.inspection));
    if (g.loading) return box.replaceChildren(...loadingPrompt(g.loading));
    if (targeting) return box.replaceChildren(...targetingPrompt());
    box.replaceChildren();
  }

  function inspectionPrompt(inspection) {
    const g = game();
    const ship = g.ships[inspection.ship];
    const where = inspection.by === "checkpoint" ? "at a checkpoint" : "by a patrol";
    const about = el("p", {}, who(inspection.owner), ` — ${ship.name} was stopped ${where} at ${placeName(ship.at)}. `,
      `Declared: `, goodChip(ship.declared), `, ${ship.cargo} goods aboard.`);
    if (inspection.stage === "bribe" && inspection.owner === state.you) {
      const credits = g.smugglers[state.you].credits;
      const input = el("input", { type: "number", min: 0, max: credits, value: 0, style: "width: 90px" });
      return [el("h3", {}, "Inspection!"), about,
        el("div", { className: "row" }, `Offer Interpol a bribe (0–${credits} credits):`, input,
          el("button", { onclick: () => send({ action: "bribe", amount: Math.max(0, Math.floor(Number(input.value) || 0)) }) }, "Offer"))];
    }
    if (inspection.stage === "decide" && isCop()) {
      const bribe = inspection.bribe || 0;
      return [el("h3", {}, "Inspect this ship?"), about,
        el("p", {}, bribe ? `They offer you ${bribe} credits to let them pass.` : "They offer no bribe."),
        el("div", { className: "row" },
          el("button", { className: "red", onclick: () => send({ action: "decide", inspect: true }) }, "Inspect"),
          el("button", { className: "green", onclick: () => send({ action: "decide", inspect: false }) },
            bribe ? `Let it pass (take ${bribe})` : "Let it pass"))];
    }
    const waiting = inspection.stage === "bribe" ? g.names[inspection.owner] : g.names[g.interpol];
    const extra = inspection.stage === "decide" ? ` Bribe offered: ${inspection.bribe || 0}.` : "";
    return [el("h3", {}, "Inspection"), about, el("p", { className: "muted" }, `Waiting for ${waiting}.${extra}`)];
  }

  function loadingPrompt(loading) {
    const g = game();
    const contract = g.contracts[loading.contract];
    const ship = g.ships[loading.ship];
    if (loading.pid !== state.you) {
      return [el("p", {}, who(loading.pid), ` is loading cargo #${loading.contract.slice(1)} onto ${ship?.name || "a ship"}…`)];
    }
    const hand = state.private.hand;
    const loads = hand.filter((c) => loadMarks[c.uid] === "load").length;
    const discards = hand.filter((c) => loadMarks[c.uid] === "discard").length;
    const need = Math.max(0, hand.length - loads - 5);
    const cards = hand.map((card) => {
      const mark = loadMarks[card.uid];
      const node = goodCard(card, `pickable${mark ? ` mark-${mark}` : ""}`);
      node.append(el("div", { className: "mark" }, mark === "load" ? "LOAD" : mark === "discard" ? "DISCARD" : "keep"));
      node.onclick = () => {
        loadMarks[card.uid] = mark === undefined ? "load" : mark === "load" ? "discard" : undefined;
        render();
      };
      return node;
    });
    const legal = Object.entries(g.goods).filter(([, good]) => good.legal);
    const select = el("select", { onchange: () => { declared = select.value; } },
      ...legal.map(([id, good]) => el("option", { value: id, selected: id === declared }, good.name)));
    if (!declared) declared = select.value;
    const ready = loads >= 1 && discards === need;
    return [
      el("h3", {}, `Loading cargo #${loading.contract.slice(1)} onto ${ship.name}`),
      el("p", { className: "small" }, "Click cards to cycle keep → load → discard. The contract wants ", goodChip(contract.good),
        ` (+${contract.bonus}). Load at least one card; you may keep 5 in hand.`),
      el("div", { className: "cards-row" }, ...cards),
      el("div", { className: "row", style: "margin-top: 10px" },
        el("span", {}, `Loading ${loads}, discarding ${discards}` + (need ? ` (must discard ${need})` : "")),
        el("span", {}, "Declare:"), select,
        el("button", {
          className: "green", disabled: !ready,
          onclick: () => send({
            action: "load", declare: declared,
            load: hand.filter((c) => loadMarks[c.uid] === "load").map((c) => c.uid),
            discard: hand.filter((c) => loadMarks[c.uid] === "discard").map((c) => c.uid),
          }),
        }, "Load ship"))];
  }

  function targetingPrompt() {
    const g = game();
    const card = g.cards[targeting.cardId];
    const cancelButton = el("button", { className: "plain", onclick: cancel }, "Cancel");
    if (!targeting.cardId) {  // Repeat: pick the card to copy
      const options = g.police.played
        .map((cardId, i) => ({ cardId, uid: playedUid(i) }))
        .filter(({ cardId }) => g.cards[cardId].kind === "action" && !g.cards[cardId].effects.repeat);
      return [el("h3", {}, "Repeat which card?"),
        el("div", { className: "cards-row" }, ...options.map(({ cardId, uid }) =>
          copCard(cardId, { onclick: () => chooseCopy(uid, cardId) }))),
        el("div", { className: "row", style: "margin-top: 8px" }, cancelButton)];
    }
    const kind = card.effects.piece;
    if (!targeting.piece) {
      const options = Object.keys(state.private.targets[targeting.cardId] || {});
      return [el("h3", {}, `${card.name}: which ${kind}?`),
        el("div", { className: "row" }, ...options.map((pieceId) => {
          const piece = g.police.pieces[pieceId];
          return el("button", { onclick: () => { targeting.piece = pieceId; render(); } },
            `${kind} ${pieceId.replace(kind, "")} (${piece.at ? placeName(piece.at) : "off the board"})`);
        }), cancelButton)];
    }
    return [el("h3", {}, `${card.name}: click a highlighted spot for the ${kind}.`),
      el("div", { className: "row" },
        el("span", { className: "muted" }, kind === "barrier" ? "Esc cancels." : "Loaded ships on that spot will be inspected. Esc cancels."),
        cancelButton)];
  }

  // Public police.played lists card ids; Repeat names a played copy by uid, from private.played
  // (same order).
  function playedUid(index) {
    return state.private.played?.[index]?.uid;
  }

  // --- Contracts, players, log, market, hand ------------------------------------------------

  // Contract tiles above the map: route on the top half, the order on the bottom half. A tile
  // glows and is clickable when one of your ships can pick up its cargo.
  function renderContracts() {
    const g = game();
    const pickups = myTurn() && !isCop() ? state.private?.pickups || {} : {};
    const tiles = g.row.map((cid) => {
      const c = g.contracts[cid];
      const holder = g.holders[cid];
      const ships = Object.keys(pickups).filter((sid) => pickups[sid].includes(cid));
      let status;
      if (holder) {
        const ship = g.ships[holder];
        status = el("div", { className: "small" }, "On ", ship?.name || "a ship", ship ? el("span", {}, " (", who(ship.owner), ")") : "");
      } else if (ships.length) {
        status = el("div", { className: "small pick" }, "Click to pick up");
      } else {
        status = el("div", { className: "small muted" }, "Waiting at ", placeName(c.from));
      }
      const tile = el("div", { className: `contract-tile${ships.length ? " pickable" : ""}${holder ? " taken" : ""}` },
        el("div", { className: "half route" },
          el("span", { className: "num" }, cid.slice(1)),
          planetStop(c.from), el("div", { className: "arrow" }, "↓"), planetStop(c.to)),
        el("div", { className: "half order" },
          goodChip(c.good), el("div", {}, el("b", {}, `+${c.bonus}`), " bonus"), status));
      if (ships.length) tile.onclick = () => pickUp(cid, ships);
      return tile;
    });
    tiles.push(el("div", { className: "contract-tile deck", title: "Contracts still to come" },
      el("div", { className: "big" }, String(g.contractsLeft)), el("div", { className: "small" }, "in the deck")));
    $("contracts").replaceChildren(...tiles);
  }

  function planetStop(node) {
    const planet = game().board.planets[node];
    return el("div", { className: "stop" },
      el("span", { className: "disc big", style: `background:${planet.color}` }), el("span", {}, planet.name));
  }

  function pickUp(cid, ships) {
    const sid = ships.includes(selectedShip) ? selectedShip : ships.length === 1 ? ships[0] : null;
    if (!sid) return showError("Two of your ships can pick this up: click the ship first, then the contract.");
    selectedShip = null;
    send({ action: "pickup", ship: sid, contract: cid });
  }

  // Scoreboard on the side: cards in hand and score for everyone, then the round.
  function renderPeople() {
    const g = game();
    const row = (pid, cards, score, note) => el("tr", { className: g.turn === pid ? "current" : "" },
      el("td", {}, who(pid), note ? el("span", { className: "small muted" }, ` ${note}`) : ""),
      el("td", {}, String(cards)), el("td", {}, String(score)));
    const rows = Object.entries(g.smugglers).map(([pid, s]) => row(pid, s.hand, s.credits, s.left ? "left" : ""));
    rows.push(row(g.interpol, g.police.hand, g.police.score, "Interpol"));
    $("people").replaceChildren(el("table", { className: "scores" },
      el("thead", {}, el("tr", {}, el("th", {}, ""), el("th", {}, "Cards"), el("th", {}, "Score"))),
      el("tbody", {}, ...rows)));
    $("round").textContent = `Round ${Math.min(g.round, g.roundLimit)} of ${g.roundLimit}`;
  }

  // Player boards below the map: one outlined area per player, in turn order (whoever's turn
  // it is comes first). Smugglers' boards hold their ship tiles; Interpol's holds its play area
  // and the market.
  function renderPlayerBoards() {
    const g = game();
    const boards = g.turnOrder.map((pid) => pid === g.interpol ? interpolBoard() : smugglerBoard(pid));
    $("player-boards").replaceChildren(...boards);
  }

  function playerBoard(pid, extraClass, ...children) {
    const g = game();
    const color = pid === g.interpol ? "#2962ff" : g.smugglers[pid]?.color || "#999";
    const name = (g.names[pid] || "?") + (pid === state.you ? " (you)" : "") + (pid === g.interpol ? " · Interpol" : "");
    return el("fieldset", { className: `pboard ${extraClass}${g.turn === pid && playing() ? " current" : ""}` },
      el("legend", {}, el("span", { className: "swatch", style: `background:${color}` }), name),
      ...children);
  }

  function smugglerBoard(pid) {
    const tiles = Object.entries(game().ships).filter(([, ship]) => ship.owner === pid)
      .map(([sid, ship]) => shipTile(sid, ship));
    return playerBoard(pid, "smuggler", el("div", { className: "tiles" }, ...tiles));
  }

  // A ship tile: name and the cargo slot (the contract number when loaded) on top, stats below,
  // then the cargo as a vertical stack of cards (face down unless they're yours or the game is over).
  function shipTile(sid, ship) {
    const g = game();
    const mine = ship.owner === state.you;
    const canAct = mine && myTurn() && !!state.private?.reach?.[sid];
    const done = ship.acted && g.turn === ship.owner && playing();
    const contract = ship.contract ? g.contracts[ship.contract] : null;
    const tile = el("div", {
      className: `ship-tile${canAct ? " can-act" : ""}${sid === selectedShip ? " selected" : ""}${done ? " acted" : ""}`,
    },
    el("div", { className: "top" }, el("b", {}, ship.name),
      el("span", { className: `slot${ship.contract ? " filled" : ""}`, title: ship.contract ? `Carrying cargo for contract #${ship.contract.slice(1)}` : "No cargo" },
        ship.contract ? ship.contract.slice(1) : "")),
    el("div", { className: "stats" },
      el("div", {}, `Speed ${ship.speed}`, done ? el("span", { className: "muted" }, " · done") : ""),
      el("div", {}, "At ", planetChip(ship.at)),
      contract ? el("div", {}, "To ", planetChip(contract.to)) : ""));
    // The declaration is public: everyone (Interpol above all) sees it right above the cargo.
    if (ship.declared) tile.append(el("div", { className: "declared" }, "Declared", goodChip(ship.declared)));
    const cards = mine ? state.private?.cargo?.[sid] || [] : (ship.contents || []).map((card) => ({ card }));
    if (cards.length) {
      tile.append(el("div", { className: "stack" }, ...cards.map((c) => stackCard(c.card))));
    } else if (ship.cargo) {
      tile.append(el("div", { className: "stack" },
        ...Array.from({ length: ship.cargo }, () => el("div", { className: "scard back" }, "?"))));
    } else {
      tile.append(el("div", { className: "stack empty small muted" }, "Empty hold"));
    }
    if (mine && playing() && g.turn === state.you && !g.inspection && !g.loading && contract?.to === ship.at) {
      tile.append(el("button", {
        className: "small green", onclick: (e) => { e.stopPropagation(); send({ action: "deliver", ship: sid }); },
      }, `Deliver #${ship.contract.slice(1)}`));
    }
    if (mine) tile.onclick = () => onShip(sid);
    return tile;
  }

  function stackCard(goodId) {
    const good = game().goods[goodId];
    return el("div", { className: `scard${good.legal ? "" : " illegal"}`, style: `background:${good.color}`, title: good.text },
      el("span", {}, good.name), el("b", {}, String(good.value)));
  }

  function interpolBoard() {
    const g = game();
    const police = g.police;
    const turn = g.turn === g.interpol && playing();
    const canBuy = myTurn() && isCop() && police.buys > 0;
    const owned = Object.entries(police.owned).map(([id, n]) => `${g.cards[id]?.name || id} ×${n}`).join(", ");
    const market = Object.entries(police.supply).map(([cardId, left]) => {
      const cost = g.cards[cardId].cost;
      const button = canBuy
        ? el("button", { className: "small", disabled: left <= 0 || police.budget < cost, onclick: () => send({ action: "buy", card: cardId }) }, "Buy")
        : "";
      return copCard(cardId, {}, el("div", { className: "foot" }, el("span", { className: "small" }, `${left} left`), button));
    });
    return playerBoard(g.interpol, "interpol",
      el("div", { className: "small muted" },
        (turn ? `Actions ${police.actions} · Buys ${police.buys} · Budget ${police.budget} · ` : "") +
        `Hand ${police.hand} · Deck ${police.deck.draw} · Discard ${police.deck.discard}`),
      el("h3", {}, "Play area"),
      police.played.length
        ? el("div", { className: "cards-row" }, ...police.played.map((id) => copCard(id)))
        : el("p", { className: "small muted" }, turn ? "Nothing played yet this turn." : "Nothing in play."),
      el("h3", {}, "Market"),
      el("div", { className: "market" }, ...market),
      el("p", { className: "small muted" }, `Owns: ${owned}`));
  }

  function renderLog() {
    const g = game();
    const entries = [];
    for (let i = g.logSize - 1; i >= Math.max(0, g.logSize - 80); i--) {
      const entry = g.log[String(i)];
      if (!entry) continue;
      const color = entry.pid ? (entry.pid === g.interpol ? "#2962ff" : g.smugglers[entry.pid]?.color) : null;
      entries.push(el("div", { className: "log-entry", style: color ? `border-left-color:${color}` : "" },
        entry.text,
        entry.cards ? el("div", { className: "cards" }, ...entry.cards.map(goodChip)) : ""));
    }
    $("log").replaceChildren(...entries);
  }

  function renderHand() {
    const bar = $("hand-bar");
    const priv = state.private;
    const show = !!priv?.role && playing();
    bar.hidden = !show;
    document.querySelector("main").classList.toggle("with-hand", show);
    if (!show) return;
    const g = game();
    if (priv.role === "smuggler") {
      bar.replaceChildren(
        el("div", { className: "label" }, el("span", {}, el("b", {}, "Your goods"), ` (${priv.hand.length})`),
          el("span", {}, `Credits: ${g.smugglers[state.you].credits}`)),
        el("div", { className: "cards-row" }, ...priv.hand.map((card) => goodCard(card))));
      return;
    }
    const police = g.police;
    const cards = priv.hand.map((card) => {
      const def = g.cards[card.card];
      const usable = myTurn() && (def.kind === "funding" || police.actions > 0);
      const chosen = targeting?.uid === card.uid;
      return copCard(card.card, {
        disabled: !usable,
        className: `icard ${def.kind}${chosen ? " chosen" : ""}`,
        onclick: () => playCard(card),
      });
    });
    bar.replaceChildren(
      el("div", { className: "label" }, el("span", {}, el("b", {}, "Interpol hand")),
        el("span", {}, `Actions ${police.actions} · Buys ${police.buys} · Budget ${police.budget}`),
        el("span", {}, `Score ${police.score}`)),
      el("div", { className: "cards-row" }, ...cards));
  }

  // --- Interactions -------------------------------------------------------------------------

  function playCard(card) {
    if (!myTurn()) return;
    const effects = game().cards[card.card].effects;
    if (effects.repeat) {
      targeting = { uid: card.uid, cardId: null };
    } else if (effects.piece) {
      startPieceTargeting({ uid: card.uid, cardId: card.card });
      return;
    } else {
      targeting = null;
      send({ action: "play", card: card.uid });
      return;
    }
    render();
  }

  function chooseCopy(copyUid, cardId) {
    if (game().cards[cardId].effects.piece) {
      startPieceTargeting({ uid: targeting.uid, cardId, copy: copyUid });
      return;
    }
    send({ action: "play", card: targeting.uid, copy: copyUid });
    targeting = null;
  }

  function startPieceTargeting(next) {
    targeting = next;
    const pieces = Object.keys(state.private.targets[next.cardId] || {});
    if (pieces.length === 1) targeting.piece = pieces[0];
    render();
  }

  function sendPlay() {
    const t = targeting;
    send({ action: "play", card: t.uid, copy: t.copy, piece: t.piece, to: t.to });
    targeting = null;
    render();
  }

  function onNode(node) {
    if (!state || !playing()) return;
    if (targeting?.piece) {
      const allowed = state.private.targets[targeting.cardId]?.[targeting.piece] || [];
      if (!allowed.includes(node)) return;
      targeting.to = node;
      sendPlay();
      return;
    }
    if (selectedShip) {
      const reach = state.private.reach[selectedShip] || {};
      if (node in reach) {
        send({ action: "move", ship: selectedShip, to: node });
        selectedShip = null;
        render();
      }
    }
  }

  function onShip(sid) {
    if (!state || !playing()) return;
    const ship = game().ships[sid];
    if (!ship) return;
    if (targeting) return onNode(ship.at);
    if (selectedShip && sid !== selectedShip && ship.at in (state.private.reach[selectedShip] || {})) {
      return onNode(ship.at);  // moving onto a spot where a ship already is
    }
    if (ship.owner !== state.you || !myTurn()) return;
    if (!state.private.reach?.[sid]) return showError(`${ship.name} has already acted this turn.`);
    selectedShip = selectedShip === sid ? null : sid;
    render();
  }

  function onPiece(pieceId) {
    if (!state || !playing()) return;
    const piece = game().police.pieces[pieceId];
    if (!piece) return;
    if (targeting && !targeting.piece && targeting.cardId) {
      if (pieceId in (state.private.targets[targeting.cardId] || {})) {
        targeting.piece = pieceId;
        render();
      }
      return;
    }
    if (piece.at) onNode(piece.at);
  }
})();
