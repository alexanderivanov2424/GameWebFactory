/*
 * Gilded Trail: the game page. The map is drawn by board.js (TrailBoard).
 *
 * render() -> renderLobby() or renderGame(), which calls one render* per area: result, status
 * bar, prompt (side: what the current choice needs), players, log, market + reserve (below the
 * map), hand bar (fixed bottom); then map.highlight() for the current mode.
 * Client modes (reset each turn, Escape cancels):
 *   explorer   which of my explorers moves (click one on the map)
 *   cardSel    the movement card picked in hand (highlights the spaces it can pay for)
 *   mode       null | {kind: "pay", explorer, to, need, v} (rubble/base camp/rubble blockade)
 *              | {kind: "buy"} | {kind: "end"} | {kind: "play", uid}
 *   picks      uids picked in hand for pay / buy / end / the pending "remove" choice
 * The server sends every legal step (private.options / private.guide) and each card's coin
 * value (cards[id].coins), so this file holds no rules: it shows them and sends choices.
 */
(() => {
  const { $, el, listNames } = AppDom;
  let state = null;
  let lastGame = null;
  let turnKey = null;
  let explorer = 0;
  let cardSel = null;
  let mode = null;
  let picks = [];

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
    if (event.key === "Escape" && (mode || cardSel !== null)) cancel();
  });

  function send(message) {
    lobby.sendGame(message);
  }

  function cancel() {
    mode = null;
    cardSel = null;
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
    mode = null;
    cardSel = null;
    picks = [];
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
      mode = null;
      cardSel = null;
      picks = [];
    }
    const uids = new Set(hand().map((c) => c.uid));
    picks = picks.filter((uid) => uids.has(uid));
    if (cardSel !== null && !uids.has(cardSel)) cardSel = null;
    if (mode?.kind === "play" && !uids.has(mode.uid)) mode = null;
    if (g.pending) mode = null;
    const mine = g.players[state.you]?.explorers || [];
    if (!mine[explorer]) explorer = Math.max(0, mine.findIndex((k) => k));
  }

  function targets() {
    if (!myTurn() || (mode && mode.kind !== "pay")) return {};
    const out = {};
    const g = game();
    if (g.pending?.kind === "guide") {
      for (const k of priv().guide?.[String(explorer)] || []) out[k] = "go";
      return out;
    }
    if (g.pending || mode) return out;
    for (const [k, req] of Object.entries(priv().options?.[String(explorer)] || {})) {
      if (req.need === "discard" || req.need === "remove") {
        if (req.cards.length) out[k] = "step";
      } else if (cardSel !== null) {
        if (req.cards.includes(cardSel)) out[k] = "go";
      } else if (req.continue) {
        out[k] = "go";
      } else if (req.cards.length) {
        out[k] = "step";
      }
    }
    return out;
  }

  function renderHighlights() {
    const t = targets();
    if (mode?.kind === "pay") t[mode.to] = "go";
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
      el("div", {}, text), buttons.length ? el("div", { className: "row" }, ...buttons) : "");
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
      return promptBox("Remove cards", `Pick up to ${pending.max} card${pending.max > 1 ? "s" : ""} in your hand to remove from the game (or none).`,
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
    if (mode?.kind === "pay") {
      const verb = mode.need === "remove" ? "remove from the game" : "discard";
      return promptBox(mode.blockade !== undefined ? "Clear the blockade" : mode.need === "remove" ? "Base camp" : "Rubble",
        `Pick ${mode.v} card${mode.v > 1 ? "s" : ""} in your hand to ${verb}.`,
        button("Confirm", () => send({ action: "pay", explorer: mode.explorer, to: mode.to, cards: picks }), "green", n !== mode.v),
        button("Cancel", cancel, "plain"));
    }
    if (mode?.kind === "buy") {
      const offered = picks.reduce((sum, uid) => sum + def(hand().find((c) => c.uid === uid).card).coins, 0);
      return promptBox("Buy a card", `Pick the cards to pay with, then click a market card. Offered: ${fmtCoins(offered)} coins.`,
        button("Cancel", cancel, "plain"));
    }
    if (mode?.kind === "end") {
      return promptBox("End your turn", `Pick any cards to discard too, then end your turn. You'll draw back up to ${g.handSize}.`,
        button(n ? `End turn, discard ${n}` : "End turn", () => send({ action: "endTurn", discard: picks }), "green"),
        button("Cancel", cancel, "plain"));
    }
    if (mode?.kind === "play") {
      const card = hand().find((c) => c.uid === mode.uid);
      return promptBox(`Play ${def(card.card).name}?`, def(card.card).text,
        button("Play", () => { const uid = mode.uid; mode = null; send({ action: "play", card: uid }); }, "green"),
        button("Cancel", cancel, "plain"));
    }
    const lines = [];
    if (g.moving) {
      lines.push(`Moving with ${def(g.moving.card).name}: ${g.moving.left} ${g.moving.kind}${g.moving.left === 1 ? "" : "s"} left. Click a gold-edged space to keep going, or pick another card (the rest is lost).`);
    } else if (cardSel !== null) {
      lines.push(`${def(hand().find((c) => c.uid === cardSel).card).name} selected: click a gold-edged space. Esc cancels.`);
    } else {
      lines.push("Pick a movement card in your hand, then click a space next to your explorer. Rubble and base camps ask which cards to give up.");
    }
    if ((g.players[state.you].explorers || []).filter((k) => k).length > 1) lines.push("You have two explorers: click one on the map to move it.");
    if (g.played.length) lines.push(`Played this turn: ${g.played.map((c) => def(c).name).join(", ")}.`);
    promptBox("Your turn", lines.map((t) => el("div", { className: "small", style: "margin-bottom: 4px" }, t)));
  }

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
      return el("div", { className: `prow${pid === g.turn ? " current" : ""}${p.left ? " left" : ""}` },
        el("span", { className: "dot", style: `background:${p.color}` }),
        el("div", {}, el("b", {}, g.names[pid] + (pid === state.you ? " (you)" : "")),
          el("div", { className: "meta" },
            `hand ${p.hand} · deck ${p.deck} · discard ${p.discard} · removed ${p.removed}`
            + (p.left ? " · left" : arrived && !p.left ? ` · ${arrived}/${p.explorers.length} arrived` : ""))),
        el("div", {}, ...chips));
    }));
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
    const picking = myTurn() && (mode?.kind === "buy" || g.pending?.kind === "free");
    const open = m.slots.includes("");
    $("market").replaceChildren(...m.slots.map((cardId) => cardId
      ? cardFace(cardId, { onclick: () => onMarket(cardId), disabled: !picking }, { count: m.supply[cardId] })
      : el("div", { className: "tcard empty" }, "Sold out")));
    const reserve = Object.keys(m.supply).filter((id) => !m.slots.includes(id) && m.supply[id] > 0);
    $("reserve-note").textContent = open
      ? "(a market slot is empty: these can be bought)" : "(can be bought once a market slot sells out)";
    $("reserve").replaceChildren(...reserve.map((cardId) => {
      const d = def(cardId);
      const usable = picking && (open || g.pending?.kind === "free");
      return el("button", {
        className: "tcard", disabled: !usable, onclick: () => onMarket(cardId),
        title: `${d.name}${d.kind === "action" ? `: ${d.text}` : `: ${d.value} ${RES[d.kind]}`}${d.single ? " (single use)" : ""} · ${m.supply[cardId]} left`,
      }, el("div", { className: `band k-${d.kind}` }), el("div", { className: "nm" }, d.name),
      el("div", { className: "val" }, String(d.cost)));
    }));
  }

  function renderHand() {
    const bar = $("hand-bar");
    const show = !!priv().hand && state.phase === "playing";
    bar.hidden = !show;
    document.querySelector("main").classList.toggle("with-hand", show);
    if (!show) return;
    const g = game();
    const mine = myTurn();
    const picking = mine && (mode && mode.kind !== "play" || g.pending?.kind === "remove");
    const cards = hand().map((card) => {
      const d = def(card.card);
      const selected = picking ? picks.includes(card.uid) : cardSel === card.uid || mode?.uid === card.uid;
      const usable = mine && (picking || (!g.pending && !mode));
      const face = cardFace(card.card, { onclick: () => onCard(card), disabled: !usable });
      face.classList.toggle("sel", selected);
      if (!usable) face.disabled = true;
      return face;
    });
    const me = g.players[state.you];
    const controls = mine ? el("span", { className: "controls" },
      button(g.bought ? "Bought this turn" : "Buy a card", () => { cancel(); mode = { kind: "buy" }; render(); },
        "", g.bought || !!g.pending || !!mode),
      button("End turn", () => { cancel(); mode = { kind: "end" }; render(); }, "green", !!g.pending || !!mode)) : "";
    bar.replaceChildren(
      el("div", { className: "label" }, el("span", {}, el("b", {}, "Your hand"), ` (${hand().length})`),
        el("span", {}, `deck ${me.deck} · discard ${me.discard} · removed ${me.removed}`), controls),
      el("div", { className: "cards-row" }, ...(cards.length ? cards : [el("span", { className: "muted" }, "No cards in hand.")])));
  }

  // --- Interactions -------------------------------------------------------------------------

  function onCard(card) {
    if (!myTurn()) return;
    const g = game();
    if ((mode && mode.kind !== "play") || g.pending?.kind === "remove") {
      picks = picks.includes(card.uid) ? picks.filter((u) => u !== card.uid) : [...picks, card.uid];
      if (mode?.kind === "pay" && picks.length > mode.v) picks.shift();
      return render();
    }
    if (g.pending) return;
    if (def(card.card).kind === "action") {
      mode = mode?.uid === card.uid ? null : { kind: "play", uid: card.uid };
      cardSel = null;
    } else {
      mode = null;
      cardSel = cardSel === card.uid ? null : card.uid;
    }
    render();
  }

  function onMarket(cardId) {
    if (!myTurn()) return;
    if (game().pending?.kind === "free") return send({ action: "take", card: cardId });
    if (mode?.kind !== "buy") return showError('Click "Buy a card" first, then pick the cards to pay with.');
    send({ action: "buy", card: cardId, cards: picks });
  }

  function onExplorer(pid, index) {
    if (pid !== state.you || !myTurn()) return;
    explorer = index;
    if (mode?.kind === "pay") mode = null;
    render();
  }

  function onHex(k) {
    if (!myTurn()) return;
    const g = game();
    if (g.pending?.kind === "guide") {
      if ((priv().guide?.[String(explorer)] || []).includes(k)) send({ action: "guide", explorer, to: k });
      return;
    }
    if (g.pending || (mode && mode.kind !== "pay")) return;
    const req = priv().options?.[String(explorer)]?.[k];
    if (!req) {
      // Clicking a space next to my other explorer switches to it.
      const other = Object.entries(priv().options || {}).find(([, steps]) => steps[k]);
      if (other) { explorer = Number(other[0]); return onHex(k); }
      return;
    }
    if (req.need === "discard" || req.need === "remove") {
      if (!req.cards.length) return showError(`You need ${req.v} card${req.v > 1 ? "s" : ""} in hand for that.`);
      mode = { kind: "pay", explorer, to: k, need: req.need, v: req.v, blockade: req.blockade };
      picks = [];
      cardSel = null;
      return render();
    }
    if (cardSel !== null) {
      if (!req.cards.includes(cardSel)) return showError(`That card can't pay ${req.v} ${req.need}.`);
      return send({ action: "move", explorer, to: k, card: cardSel });
    }
    if (req.continue) return send({ action: "move", explorer, to: k });
    if (req.cards.length === 1) return send({ action: "move", explorer, to: k, card: req.cards[0] });
    if (req.cards.length) return showError(`Pick which card pays ${req.v} ${req.need}.`);
    showError(`None of your cards can pay ${req.v} ${req.need}.`);
  }
})();
