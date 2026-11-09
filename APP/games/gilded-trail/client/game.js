/*
 * Gilded Trail: the game page. The map is drawn by board.js (TrailBoard).
 *
 * render() -> renderLobby() or renderGame(), which calls one render* per area: result, status
 * bar, prompt (side: what the current choice needs), players (each with a "Deck" button that
 * lists the cards they own), log, market + reserve (below the map), hand bar (fixed bottom);
 * then map.highlight() for the current selection.
 * No modes: the player selects cards in hand (picks), then clicks what to use them on:
 *   a space   one selected card that can pay it moves there (none selected: the moving card
 *             goes on, or the only card that can pay); rubble / base camp / rubble blockade:
 *             exactly that many selected cards are discarded / removed
 *   a market or reserve card   the selected cards pay for it
 *   "Play <card>" (prompt)     a selected action card is played
 *   "End turn" (hand bar)      the selected cards are discarded too
 * Client state (reset each turn and when a card's choice starts or ends; Escape clears picks):
 *   explorer   which of my explorers moves (click one on the map)
 *   picks      uids selected in hand (also the pending "remove" choice, sent by itself once
 *              no more cards can be picked)
 *   viewDeck   whose deck list is open in the players panel (null = none)
 * The server sends every legal step (private.options / private.guide) and each card's coin
 * value (cards[id].coins), so this file holds no rules: it shows them and sends choices.
 */
(() => {
  const { $, el, listNames } = AppDom;
  let state = null;
  let lastGame = null;
  let turnKey = null;
  let explorer = 0;
  let picks = [];
  let pendingKind = "";
  let viewDeck = null;

  const lobby = AppLobby.connect("gilded-trail", {
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
  const map = TrailBoard.create($("board"), { onHex, onExplorer });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && picks.length) cancel();
  });

  function send(message) {
    lobby.sendGame(message);
  }

  function cancel() {
    picks = [];
    if (state) render();
  }

  // --- Helpers ------------------------------------------------------------------------------

  const game = () => state.game;
  const priv = () => state.private || {};
  const myTurn = () => state.phase === "playing" && game().turn === state.you;
  const hand = () => priv().hand || [];
  const def = (cardId) => game().cards[cardId];
  const RES = { machete: "machete", paddle: "paddle", coin: "coin", joker: "any", action: "" };

  function fmtCoins(value) {
    const whole = Math.floor(value);
    return value !== whole ? `${whole || ""}½` : String(whole);
  }

  function who(pid) {
    const g = game();
    return el("span", { className: "who" },
      el("span", { className: "dot", style: `background:${g.players[pid]?.color || "#999"}` }),
      (g.names[pid] || "?") + (pid === state.you ? " (you)" : ""));
  }

  function cardFace(cardId, props = {}, extra = {}) {
    const d = def(cardId);
    const tag = props.onclick ? "button" : "div";
    const children = [
      el("div", { className: `band k-${d.kind}` }),
      el("div", { className: "nm" }, d.name),
    ];
    if (d.text) children.push(el("div", { className: "desc" }, d.text));
    if (d.kind !== "action") {
      children.push(el("div", { className: "val" }, String(d.value),
        el("small", {}, ` ${RES[d.kind]}${d.value > 1 && d.kind !== "joker" ? "s" : ""}`)));
    }
    children.push(el("div", { className: "foot" },
      el("span", {}, `pays ${fmtCoins(d.coins)}`),
      d.single ? el("span", { className: "once" }, "SINGLE USE") : "",
      d.cost !== undefined ? el("span", {}, `cost ${d.cost}`) : ""));
    if (extra.count !== undefined) children.push(el("span", { className: "count" }, `×${extra.count}`));
    return el(tag, { className: "tcard", title: d.text || d.name, ...props }, ...children);
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
    turnKey = null;
    picks = [];
    viewDeck = null;
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
      map.draw(g);
      lastGame = g;
    }
    updateTurnAlert(myTurn() ? `${state.gameNumber}:${g.turnNumber}` : null);
    renderResult();
    renderStatus();
    renderPrompt();
    renderPeople();
    renderLog();
    renderMarket();
    renderHand();
    renderHighlights();
  }

  function resetModes() {
    const g = game();
    const key = `${state.gameNumber}:${g.turnNumber}`;
    if (key !== turnKey || !myTurn()) {
      if (key !== turnKey) explorer = g.moving && myTurn() ? g.moving.explorer : 0;
      turnKey = key;
      picks = [];
    }
    // A card's choice starting or ending: start from an empty selection (never trash old picks).
    const kind = g.pending?.kind || "";
    if (kind !== pendingKind) picks = [];
    pendingKind = kind;
    const uids = new Set(hand().map((c) => c.uid));
    picks = picks.filter((uid) => uids.has(uid));
    const mine = g.players[state.you]?.explorers || [];
    if (!mine[explorer]) explorer = Math.max(0, mine.findIndex((k) => k));
  }

  const paysWithCards = (req) => req.need === "discard" || req.need === "remove";

  // What clicking the space `req` describes would do with the current picks:
  // {cards: [uids]} pay / {card: uid} move with it / {card: null} the moving card goes on /
  // {error} with the reason.
  function plan(req) {
    if (paysWithCards(req)) {
      const verb = req.need === "remove" ? "remove from the game" : "discard";
      if (!req.cards.length) return { error: `You need ${req.v} card${req.v > 1 ? "s" : ""} in hand for that.` };
      if (picks.length === req.v) return { cards: picks };
      return { error: `Select ${req.v} card${req.v > 1 ? "s" : ""} in your hand to ${verb}, then click the space.`, step: true };
    }
    const payers = picks.filter((uid) => req.cards.includes(uid));
    if (payers.length === 1) return { card: payers[0] };
    if (req.continue) return { card: null };
    if (payers.length > 1) return { error: "Select only one card to move with.", step: true };
    if (req.cards.length === 1) return { card: req.cards[0], step: true };
    if (req.cards.length) return { error: `Select the card that pays ${req.v} ${req.need}, then click the space.`, step: true };
    return { error: `None of your cards can pay ${req.v} ${req.need}.` };
  }

  function targets() {
    if (!myTurn()) return {};
    const out = {};
    const g = game();
    if (g.pending?.kind === "guide") {
      for (const k of priv().guide?.[String(explorer)] || []) out[k] = "go";
      return out;
    }
    if (g.pending) return out;
    for (const [k, req] of Object.entries(priv().options?.[String(explorer)] || {})) {
      const p = plan(req);
      if (p.step) out[k] = "step";
      else if (!p.error) out[k] = "go";
    }
    return out;
  }

  function renderHighlights() {
    const t = targets();
    map.highlight({ targets: t, explorer: myTurn() ? explorer : null, you: state.you });
  }

  function renderResult() {
    const result = state.result;
    if (!result) return $("result").replaceChildren();
    const g = game();
    const winners = result.winners || [];
    const headline = winners.length
      ? `${listNames(winners.map((p) => g.names[p]))} win${winners.length === 1 ? "s" : ""}!`
      : "Nobody wins.";
    const rows = g.seats.map((pid) => {
      const p = g.players[pid];
      return el("div", { className: "small" }, who(pid), " ",
        p.left ? "left the game" : p.arrived ? "reached the golden city" : "still in the jungle",
        ` · ${p.blockades.length} blockade${p.blockades.length === 1 ? "" : "s"}`);
    });
    $("result").replaceChildren(el("div", {}, el("b", {}, headline), " ", result.reason || ""), ...rows);
  }

  function renderStatus() {
    const g = game();
    const parts = [el("span", {}, el("b", {}, g.board.name)), el("span", {}, `Round ${g.round}`)];
    if (state.phase === "playing") parts.push(el("span", {}, "Turn: ", who(g.turn)));
    if (g.finalRound && state.phase === "playing") parts.push(el("span", { className: "final" }, "Final round"));
    $("status").replaceChildren(...parts);
  }

  function promptBox(title, text, ...buttons) {
    $("prompt").replaceChildren(el("h3", { style: "margin: 0 0 6px" }, title),
      el("div", {}, ...[].concat(text)), buttons.length ? el("div", { className: "row" }, ...buttons) : "");
  }

  function button(label, onclick, className = "", disabled = false) {
    return el("button", { className, onclick, disabled }, label);
  }

  function renderPrompt() {
    const g = game();
    if (!myTurn()) {
      if (state.phase === "playing") promptBox(`${g.names[g.turn]}'s turn`, waitingText());
      else $("prompt").replaceChildren();
      return;
    }
    const pending = g.pending;
    const n = picks.length;
    if (pending?.kind === "remove") {
      return promptBox("Remove cards", `Click up to ${pending.max} card${pending.max > 1 ? "s" : ""} in your hand to remove from the game (or none). `
        + "The choice ends by itself once you can't pick any more.",
        button(n ? `Remove ${n}` : "Remove none", () => send({ action: "trash", cards: picks }), "green", n > pending.max));
    }
    if (pending?.kind === "free") {
      return promptBox("Courier", "Click any market or reserve card to take it for free.",
        button("Skip", () => send({ action: "take", card: null }), "plain"));
    }
    if (pending?.kind === "guide") {
      return promptBox("Local Guide", "Click a highlighted space next to your explorer: it ignores the space's requirement (across a blockade, it takes the blockade instead).",
        button("Skip", () => send({ action: "guide", to: null }), "plain"));
    }
    const lines = [];
    if (g.moving) {
      lines.push(`Moving with ${def(g.moving.card).name}: ${g.moving.left} ${g.moving.kind}${g.moving.left === 1 ? "" : "s"} left. Click a gold-edged space to keep going (selecting another card that can pay a space starts it there instead, and the rest is lost).`);
    }
    if (picks.length) {
      const offered = picks.reduce((sum, uid) => sum + def(cardOf(uid).card).coins, 0);
      lines.push(`Selected ${picks.length} card${picks.length > 1 ? "s" : ""}: click a space to move or pay with ${picks.length > 1 ? "them" : "it"}`
        + (g.bought ? "." : `, or a market card to buy (they pay ${fmtCoins(offered)} coin${offered === 1 ? "" : "s"}).`)
        + " End turn discards them. Esc clears.");
    } else {
      lines.push("Select cards in your hand, then click what to use them on: a space next to your explorer (one movement card; rubble and base camps take that many cards), "
        + (g.bought ? "" : "a market card to buy (the cards pay their coins), ") + "or play a selected action card.");
    }
    if ((g.players[state.you].explorers || []).filter((k) => k).length > 1) lines.push("You have two explorers: click one on the map to move it.");
    if (g.bought) lines.push("You've bought your card for this turn.");
    if (g.played.length) lines.push(`Played this turn: ${g.played.map((c) => def(c).name).join(", ")}.`);
    const plays = picks.map(cardOf).filter((c) => def(c.card).kind === "action")
      .map((c) => button(`Play ${def(c.card).name}`, () => { picks = picks.filter((u) => u !== c.uid); send({ action: "play", card: c.uid }); }, "green"));
    if (picks.length) plays.push(button("Clear selection", cancel, "plain"));
    promptBox("Your turn", lines.map((t) => el("div", { className: "small", style: "margin-bottom: 4px" }, t)), ...plays);
  }

  const cardOf = (uid) => hand().find((c) => c.uid === uid);

  function waitingText() {
    const g = game();
    if (g.pending) return "Choosing what their card does…";
    if (g.moving) return `Moving with ${def(g.moving.card).name} (${g.moving.left} left).`;
    return g.played.length ? `Played: ${g.played.map((c) => def(c).name).join(", ")}.` : "Planning a route…";
  }

  function renderPeople() {
    const g = game();
    $("people").replaceChildren(...g.seats.map((pid) => {
      const p = g.players[pid];
      const arrived = p.explorers.filter((k) => !k).length;
      const chips = p.blockades.map((id) => {
        const b = g.blockades[String(id)];
        return el("span", { className: `chip t-${b.t}`, title: `Blockade ${id + 1}` }, String(b.v));
      });
      const open = viewDeck === pid;
      const toggle = el("button", {
        className: `deck-btn${open ? " on" : ""}`, title: "Show every card this player owns",
        onclick: () => { viewDeck = open ? null : pid; renderPeople(); },
      }, open ? "Hide deck" : "Deck");
      return el("div", { className: `prow${pid === g.turn ? " current" : ""}${p.left ? " left" : ""}` },
        el("span", { className: "dot", style: `background:${p.color}` }),
        el("div", {}, el("span", { className: "pname" }, el("b", {}, g.names[pid] + (pid === state.you ? " (you)" : "")), toggle),
          el("div", { className: "meta" },
            `hand ${p.hand} · deck ${p.deck} · discard ${p.discard} · removed ${p.removed}`
            + (p.left ? " · left" : arrived && !p.left ? ` · ${arrived}/${p.explorers.length} arrived` : ""))),
        el("div", {}, ...chips),
        open ? deckList(p) : "");
    }));
  }

  // Every card a player owns (hand, deck and discard together) and the cards they removed.
  function deckList(p) {
    const order = { machete: 0, paddle: 1, coin: 2, joker: 3, action: 4 };
    const lines = (counts) => Object.entries(counts || {})
      .sort(([a], [b]) => (order[def(a).kind] - order[def(b).kind]) || def(a).name.localeCompare(def(b).name))
      .map(([id, n]) => {
        const d = def(id);
        const what = d.kind === "action" ? d.text : `${d.value} ${RES[d.kind]}`;
        return el("div", { className: "deck-line", title: `${d.name}: ${what}${d.single ? " (single use)" : ""}` },
          el("span", { className: `kband k-${d.kind}` }), el("span", {}, d.name),
          el("span", { className: "muted" }, d.kind === "action" ? "action" : what), el("b", {}, `×${n}`));
      });
    const total = Object.values(p.owned || {}).reduce((a, b) => a + b, 0);
    const removed = lines(p.removedCards);
    return el("div", { className: "deck-view" },
      el("div", { className: "small muted" }, `${total} card${total === 1 ? "" : "s"} (hand, deck and discard together)`),
      ...lines(p.owned),
      removed.length ? el("div", { className: "small muted", style: "margin-top: 6px" }, "Removed from the game") : "",
      ...removed);
  }

  function renderLog() {
    const g = game();
    const entries = [];
    for (let i = g.logSize - 1; i >= Math.max(0, g.logSize - 80); i--) {
      const entry = g.log[String(i)];
      if (!entry) continue;
      const color = entry.pid ? g.players[entry.pid]?.color : null;
      entries.push(el("div", { className: "log-entry", style: color ? `border-left-color:${color}` : "" },
        el("span", { className: "r" }, `R${entry.round}`), entry.text));
    }
    $("log").replaceChildren(...entries);
  }

  function renderMarket() {
    const g = game();
    const m = g.market;
    const free = myTurn() && g.pending?.kind === "free";
    const picking = free || (myTurn() && !g.pending && !g.bought);
    const open = m.slots.includes("");
    $("market").replaceChildren(...m.slots.map((cardId) => cardId
      ? cardFace(cardId, { onclick: () => onMarket(cardId), disabled: !picking }, { count: m.supply[cardId] })
      : el("div", { className: "tcard empty" }, "Sold out")));
    const reserve = Object.keys(m.supply).filter((id) => !m.slots.includes(id) && m.supply[id] > 0);
    $("reserve-note").textContent = open
      ? "(a market slot is empty: these can be bought)" : "(can be bought once a market slot sells out)";
    const usable = picking && (open || free);
    $("reserve").replaceChildren(...reserve.map((cardId) =>
      cardFace(cardId, { onclick: () => onMarket(cardId), disabled: !usable }, { count: m.supply[cardId] })));
  }

  function renderHand() {
    const bar = $("hand-bar");
    const show = !!priv().hand && state.phase === "playing";
    bar.hidden = !show;
    document.querySelector("main").classList.toggle("with-hand", show);
    if (!show) return;
    const g = game();
    const mine = myTurn();
    const usable = mine && (!g.pending || g.pending.kind === "remove");
    const cards = hand().map((card) => {
      const face = cardFace(card.card, { onclick: () => onCard(card), disabled: !usable });
      face.classList.toggle("sel", picks.includes(card.uid));
      return face;
    });
    const me = g.players[state.you];
    const n = picks.length;
    const controls = mine ? el("span", { className: "controls" },
      g.bought ? el("span", { className: "muted" }, "Bought this turn") : "",
      button(n ? `End turn, discard ${n}` : "End turn", () => send({ action: "endTurn", discard: picks }), "green", !!g.pending)) : "";
    bar.replaceChildren(
      el("div", { className: "label" }, el("span", {}, el("b", {}, "Your hand"), ` (${hand().length})`),
        el("span", {}, `deck ${me.deck} · discard ${me.discard} · removed ${me.removed}`), controls),
      el("div", { className: "cards-row" }, ...(cards.length ? cards : [el("span", { className: "muted" }, "No cards in hand.")])));
  }

  // --- Interactions -------------------------------------------------------------------------

  function onCard(card) {
    const g = game();
    if (!myTurn() || (g.pending && g.pending.kind !== "remove")) return;
    picks = picks.includes(card.uid) ? picks.filter((u) => u !== card.uid) : [...picks, card.uid];
    // Nothing left to pick in the "remove" choice (the max, or every card in hand): finish it.
    if (g.pending?.kind === "remove" && picks.length >= Math.min(g.pending.max, hand().length)) {
      return send({ action: "trash", cards: picks });
    }
    render();
  }

  function onMarket(cardId) {
    const g = game();
    if (!myTurn()) return;
    if (g.pending?.kind === "free") return send({ action: "take", card: cardId });
    if (g.pending) return;
    if (g.bought) return showError("You've already bought a card this turn.");
    if (!picks.length) return showError("Select the cards to pay with in your hand first, then click the card to buy.");
    send({ action: "buy", card: cardId, cards: picks });
  }

  function onExplorer(pid, index) {
    if (pid !== state.you || !myTurn()) return;
    explorer = index;
    render();
  }

  function onHex(k) {
    if (!myTurn()) return;
    const g = game();
    if (g.pending?.kind === "guide") {
      if ((priv().guide?.[String(explorer)] || []).includes(k)) send({ action: "guide", explorer, to: k });
      return;
    }
    if (g.pending) return;
    const req = priv().options?.[String(explorer)]?.[k];
    if (!req) {
      // Clicking a space next to my other explorer switches to it.
      const other = Object.entries(priv().options || {}).find(([, steps]) => steps[k]);
      if (other) { explorer = Number(other[0]); return onHex(k); }
      return;
    }
    const p = plan(req);
    if (p.error) return showError(p.error);
    if (p.cards) return send({ action: "pay", explorer, to: k, cards: p.cards });
    if (p.card === null) return send({ action: "move", explorer, to: k });
    send({ action: "move", explorer, to: k, card: p.card });
  }
})();
