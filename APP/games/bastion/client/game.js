/*
 * Bastion: the game page's controller. Renders from the state and holds no rules: where a unit
 * may go and what it would do come from state.private.places, haul sources from .sources, where a
 * card may go from .targets, tile cells from game.tiles; outputs, links and bonus breakdowns from
 * game.structures. Panels (status bar, round bar with the Hauling pool, enemy cards with their
 * Fighting pools, market, chronicle, card faces, and the inspector with the pick buttons) are
 * drawn by panels.js; the board by board.js.
 *
 * Sections: helpers (+ the context panels.js gets); render (lobby / game, turn alert); units
 * (unitClick: place, take back, resolve; a work unit with tools in stock opens a pick with /
 * without a tool (Shift+click = with a tool), a haul unit with several sources opens a pick of the
 * source); board (hover: blueprint ghost with R / wheel to turn, outlines for where units may go
 * (place phase) or your units to resolve (your turn), card / tile / haul-source targets, tips,
 * then panels.inspector; clicks); bottom bar (renderBar: hand, Ready / Not ready in the place phase, End turn on your turn, a trash
 * card such as Absolution: click it, click the cards to remove, then confirm; Road / Wall / Remove
 * set `tool` to lay or remove tiles until cancelled); windows (deck, help).
 *
 * Interaction state: selection (a hand card), tool (a tile tool), pick (a placed unit waiting for
 * a choice: {target}); at most one is set, and all clear when it isn't your turn.
 */
(() => {
  const { $, el } = AppDom;
  let state = null;
  let selection = null; // {uid, card, rotation} (+ trash: true, remove: [uid] for a trash card)
  let tool = null; // "road" | "wall" | "remove": laying or removing tiles
  let pick = null; // {target}: "s<uid>" (with or without a tool) or "haul" (which source)
  let hover = null; // [x, y]

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
  const updateTurnAlert = AppLobbyUI.turnAlert($("round-bar"), { text: "Your turn!" });
  const board = BastionBoard.create($("board"), {
    onHover(x, y) { hover = [x, y]; updateHover(); },
    onLeave() { hover = null; updateHover(); },
    onClick: clickCell,
    onRightClick: cancel,
    onWheel(direction) {
      if (!selection || !isBuild(selection.card)) return false;
      turn(direction);
      return true;
    },
  });

  // --- helpers ----------------------------------------------------------------------------

  const game = () => state.game;
  const you = () => state.you;
  const mySeat = () => (state.game && state.game.seats[state.you]) || null;
  const priv = () => state.private || null;
  const cardOf = (id) => game().cards[id];
  const isBuild = (id) => cardOf(id).kind === "build";
  const icon = (key) => game().icons[key] || "";
  const amounts = (obj) => Object.entries(obj || {}).filter(([, n]) => n).map(([k, n]) => `${n}${icon(k)}`).join(" ");
  const affordable = (cost) => Object.entries(cost || {}).every(([k, n]) => (game().stock[k] || 0) >= n);
  const nameOf = (pid) => game().names[pid] || pid;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const playing = () => state.phase === "playing" && Boolean(mySeat()) && Boolean(priv());
  // place phase and you can still change your placements
  const placing = () => playing() && game().phase === "place" && !game().ready[you()];
  const myTurn = () => playing() && game().phase === "act" && game().turn === you();
  const isPool = (t) => t === "haul" || t.startsWith("fight");
  const placeOf = (t) => (priv() && priv().places ? priv().places[t] : null) || null;
  const myUnits = () => (game().units || {})[you()] || { total: 0, free: 0, placed: 0 };
  const TOOLS = ["road", "wall", "remove"];
  const tileSpots = (t) => new Set((game().tiles || {})[t] || []); // legal cells, from the server
  const tileStock = (t) => (t === "road" ? game().roadStock : game().wallStock);
  const canLay = (t) => tileStock(t) > 0 || affordable(game().kinds[t].cost);
  // Where a hand card may go (blueprints and repair/cure cards), from the server.
  const targetsOf = (uid) => (priv() && (priv().targets || {})[String(uid)]) || null;

  // Your units on a target (pools hold {pid: n}; one-unit targets hold a pid).
  function mine(target) {
    const by = game().placements[target];
    if (!by) return 0;
    if (typeof by === "string") return by === you() ? 1 : 0;
    return by[you()] || 0;
  }

  function costOf(cardId) {
    const card = cardOf(cardId);
    if (card.kind === "build") return game().kinds[card.structure].cost;
    return card.kind === "curse" ? card.pay : card.cost;
  }

  function anchor(cardId, rotation, x, y) {
    const cells = game().kinds[cardOf(cardId).structure].rotations[rotation];
    const w = Math.max(...cells.map((c) => c[0])) + 1;
    const h = Math.max(...cells.map((c) => c[1])) + 1;
    const ax = x - Math.floor((w - 1) / 2);
    const ay = y - Math.floor((h - 1) / 2);
    return { ax, ay, cells: cells.map(([dx, dy]) => [ax + dx, ay + dy]) };
  }

  function send(message) {
    lobby.sendGame(message);
  }

  const panels = BastionPanels.create({
    state: () => state, game, priv, you, icon, amounts, affordable, nameOf, send,
    myTurn, placing, mine,
    placeOf, tileStock,
    unitClick: (target, event) => unitClick(target, event),
    takeBack: (target) => send({ action: "unplace", target }),
    resolve: (target, options) => resolve(target, options),
  });

  // --- render -------------------------------------------------------------------------------

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    renderButtons();
    if (inLobby) {
      selection = null;
      tool = null;
      pick = null;
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
    renderResult(finished);
    panels.status();
    panels.roundBar();
    panels.foes();
    panels.market();
    panels.log();
    renderBar();
    renderDeckWindow();
    updateHover();
    $("help-button").hidden = false;
    let alert = null;
    if (placing()) {
      $("round-bar").dataset.gwfAlert = "Place your units!";
      alert = `${state.gameNumber}:${g.step}:place`;
    } else if (myTurn()) {
      $("round-bar").dataset.gwfAlert = "Your turn!";
      alert = `${state.gameNumber}:${g.step}`;
    }
    updateTurnAlert(finished ? null : alert);
  }

  function renderResult(finished) {
    const box = $("result");
    box.hidden = !finished;
    if (!finished || !state.result) return;
    const r = state.result;
    box.className = r.victory ? "win" : "loss";
    box.replaceChildren(el("b", {}, r.victory ? "🏆 Victory! " : "💀 Defeat. "), r.reason || "");
  }

  // Drop selections that no longer apply (new state).
  function checkSelection() {
    if (!myTurn()) {
      selection = null;
      tool = null;
      pick = null;
      return;
    }
    if (tool && tool !== "remove" && !canLay(tool)) tool = null;
    if (pick && !mine(pick.target)) pick = null;
    if (pick && pick.target === "haul" && Object.keys(priv().sources || {}).length < 2) pick = null;
    if (!selection) return;
    const p = priv();
    if (!p.hand.some((c) => c.uid === selection.uid)) selection = null;
    else if (selection.trash) selection.remove = selection.remove.filter((uid) => p.hand.some((c) => c.uid === uid));
  }

  function refresh() {
    renderBar();
    updateHover();
  }

  // --- units ---------------------------------------------------------------------------------

  // Click on a unit target: place phase = place a unit (or take yours back from a building or
  // tile); your turn = resolve one of your units there (maybe via a pick).
  function unitClick(target, event = {}) {
    if (!playing()) return;
    const g = game();
    if (g.phase === "place") {
      if (g.ready[you()]) return showError("You're ready: click Not ready to change your placements.");
      const holder = g.placements[target];
      if (!isPool(target) && holder === you()) return send({ action: "unplace", target });
      const place = placeOf(target);
      if (!place) {
        if (!isPool(target) && holder) return showError(`${nameOf(holder)}'s unit is already there.`);
        const s = target.startsWith("s") ? g.structures[target.slice(1)] : null;
        if (s && !g.kinds[s.kind].work) return; // a house, wall... nothing to work: just inspecting
        const why = !s ? "" : s.ruined.length ? "it's damaged (repair it first)" : s.plague ? "it's plagued (cure it first)"
          : s.frozen ? "it's frozen this round" : s.output <= 0 ? "it would make nothing" : "";
        if (why) return showError(`No unit can go there: ${why}.`);
        return showError("No unit can go there now.");
      }
      if (myUnits().free <= 0) {
        return showError(myUnits().total
          ? "All your units are placed. Take one back first (click it, or Take back on a pool)."
          : "You have no units this round.");
      }
      // Shift+click on a pool places every free unit there (one message each).
      const count = isPool(target) && event.shiftKey ? myUnits().free : 1;
      for (let i = 0; i < count; i++) send({ action: "place", target });
      return;
    }
    if (g.phase !== "act") return;
    if (g.turn !== you()) return showError(g.turn ? `It's ${nameOf(g.turn)}'s turn.` : "Wait for the next round.");
    if (!mine(target)) return showError("You have no unit there.");
    const place = placeOf(target) || { text: "", tool: "", why: "" };
    if (place.why) return showError(place.why);
    selection = null;
    tool = null;
    if (target.startsWith("s")) {
      const withTool = place.tool && (g.stock.tools || 0) > 0;
      if (!withTool) return resolve(target);
      if (event.shiftKey) return resolve(target, { tool: true });
      pick = { target };
      return refresh();
    }
    if (target === "haul" && Object.keys(priv().sources || {}).length > 1) {
      pick = { target };
      return refresh();
    }
    if (target.startsWith("fight") && event.shiftKey) {
      // Shift+click: every fighter you have on that enemy strikes (one message each).
      for (let i = mine(target); i > 1; i--) send({ action: "resolve", target });
    }
    resolve(target);
  }

  function resolve(target, { tool: withTool = false, from = null } = {}) {
    const message = { action: "resolve", target };
    if (withTool) message.tool = true;
    if (from !== null) message.from = from;
    send(message);
    pick = null;
    refresh();
  }

  // My one-unit targets ("s<uid>", "raze<x>,<y>") as board cells.
  function targetCells(target) {
    if (target.startsWith("raze")) return [target.slice(4).split(",").map(Number)];
    if (target.startsWith("s")) return structureCells(target.slice(1));
    return [];
  }

  // --- board ---------------------------------------------------------------------------------

  function structureCells(uid) {
    const s = game().structures[uid];
    return s ? s.cells : [];
  }

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

  // What a unit target under the mouse would do, for the tip.
  function unitTip(target) {
    const g = game();
    const holder = g.placements[target];
    const place = placeOf(target);
    if (g.phase === "place") {
      if (holder === you()) return placing() ? "Your unit · click to take it back" : "Your unit";
      if (holder) return `${nameOf(holder)}'s unit`;
      if (place && placing()) return `Place a unit: ${place.text}${place.why ? ` (${place.why})` : ""}`;
      return null;
    }
    if (holder === you() && place) {
      if (!myTurn()) return `Your unit: ${place.text}`;
      if (place.why) return place.why;
      const shift = place.tool && (g.stock.tools || 0) > 0 ? ` · Shift+click: ${place.tool}` : "";
      return `Click: ${place.text}${shift}`;
    }
    return holder ? `${nameOf(holder)}'s unit` : null;
  }

  function updateHover() {
    board.clearMarks();
    if (!state || !state.game) return;
    const g = game();
    let tip = null;
    const at = hover ? board.structureAt(hover[0], hover[1]) : null;
    const key = hover ? `${hover[0]},${hover[1]}` : null;
    const blight = key ? g.blights[key] : null;
    const hoverTarget = at ? `s${at}` : blight ? `raze${key}` : null;
    if (tool) {
      const spots = tileSpots(tool);
      const ok = Boolean(hover) && spots.has(key);
      if (tool === "remove") {
        board.mark([...spots].map((k) => k.split(",").map(Number)), "target");
        if (ok) {
          board.mark([hover], "hl");
          tip = "Remove this tile (free)";
        }
      } else if (hover) {
        board.mark([hover], "ghost");
        if (!ok) board.mark([hover], "bad");
        const stock = tileStock(tool);
        tip = !ok ? "Can't lay a tile here"
          : stock > 0 ? `Lay a ${tool} (${stock} in stock)` : `Buy ${g.tileBatch} for ${amounts(g.kinds[tool].cost)}, lay one`;
      }
    } else if (selection && isBuild(selection.card)) {
      if (hover) {
        const { ax, ay, cells } = anchor(selection.card, selection.rotation, hover[0], hover[1]);
        const spots = (targetsOf(selection.uid) || {})[String(selection.rotation)] || {};
        const value = spots[`${ax},${ay}`];
        board.mark(cells, "ghost");
        if (value === undefined) board.mark(cells, "bad");
        const kind = g.kinds[cardOf(selection.card).structure];
        const made = kind.work ? Object.keys(kind.work.makes)[0] : null;
        tip = value === undefined ? "Can't build here" : made ? `Would make +${value}${icon(made)}` : "Build here";
      }
    } else if (selection && !selection.trash) {
      const targets = targetsOf(selection.uid) || {};
      for (const uid of Object.keys(targets)) board.mark(structureCells(uid), "target");
      if (at && targets[at]) {
        board.mark(structureCells(at), "hl");
        tip = targets[at];
      }
    } else if (pick && pick.target === "haul") {
      const sources = priv().sources || {};
      for (const uid of Object.keys(sources)) board.mark(structureCells(uid), "target");
      if (at && sources[at]) {
        board.mark(structureCells(at), "hl");
        tip = `Haul from here: ${sources[at]}`;
      }
    } else {
      if (pick) board.mark(targetCells(pick.target), "hl");
      if (placing() && myUnits().free > 0) {
        for (const t of Object.keys(priv().places || {})) board.mark(targetCells(t), "spot");
      }
      if (myTurn()) {
        for (const t of Object.keys(g.placements)) if (!isPool(t) && mine(t)) board.mark(targetCells(t), "target");
      }
      if (hoverTarget) {
        board.mark(at ? structureCells(at) : [hover], "hl");
        tip = unitTip(hoverTarget);
      }
      if (!tip && blight && myTurn()) {
        const foe = g.foes[String(blight.foe)];
        const cost = (blight.lair && foe && foe.defeat ? foe.defeat.raze || 1 : 1) - (blight.strikes || 0);
        tip = `Click to raze with soldiers: ${cost}${icon("soldiers")}`;
      }
    }
    showTip(tip);
    panels.inspector(at, { tool, selection, pick, hover });
  }

  function clickCell(x, y, event) {
    if (!state || !state.game || !playing()) return;
    const g = game();
    const at = board.structureAt(x, y);
    const key = `${x},${y}`;
    if (g.phase === "place") {
      if (at) unitClick(`s${at}`, event);
      else if (g.blights[key]) unitClick(`raze${key}`, event);
      return;
    }
    if (!myTurn()) return;
    if (tool) {
      if (!tileSpots(tool).has(key)) {
        return showError(tool === "remove" ? "Pick one of the outlined road or wall tiles." : "Roads and walls go on empty grass.");
      }
      send(tool === "remove" ? { action: "remove_tile", x, y } : { action: "tile", kind: tool, x, y });
      return; // the tool stays on to lay or remove more
    }
    if (selection && selection.trash) return;
    if (selection && isBuild(selection.card)) {
      const { ax, ay } = anchor(selection.card, selection.rotation, x, y);
      const spots = (targetsOf(selection.uid) || {})[String(selection.rotation)] || {};
      if (spots[`${ax},${ay}`] === undefined) return showError("That doesn't fit there.");
      send({ action: "play", uid: selection.uid, x: ax, y: ay, rotation: selection.rotation });
      selection = null;
      return refresh();
    }
    if (selection) {
      if (!at || !(targetsOf(selection.uid) || {})[at]) return showError("Pick one of the outlined buildings.");
      send({ action: "play", uid: selection.uid, x, y });
      selection = null;
      return refresh();
    }
    if (pick && pick.target === "haul") {
      if (!at || !(priv().sources || {})[at]) return showError("Pick one of the outlined buildings with goods waiting.");
      return resolve("haul", { from: Number(at) });
    }
    if (pick && at && `s${at}` === pick.target) {
      if (event && event.shiftKey) resolve(pick.target, { tool: true });
      return; // choose in the inspector
    }
    pick = null;
    if (at && mine(`s${at}`)) return unitClick(`s${at}`, event);
    if (g.blights[key]) {
      if (mine(`raze${key}`)) return unitClick(`raze${key}`, event);
      send({ action: "raze", x, y });
    }
    refresh();
  }

  function turn(direction) {
    selection.rotation = (selection.rotation + direction + 4) % 4;
    updateHover();
  }

  function cancel() {
    if (!selection && !tool && !pick) return;
    selection = null;
    tool = null;
    pick = null;
    refresh();
  }

  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea, select")) return;
    if (e.key === "Escape") cancel();
    if ((e.key === "r" || e.key === "R") && selection && isBuild(selection.card)) turn(e.shiftKey ? -1 : 1);
  });

  // --- bottom bar ------------------------------------------------------------------------------

  function barInfo() {
    const g = game();
    const units = myUnits();
    if (state.phase !== "playing") return ["The game is over.", false];
    if (g.phase === "place") {
      if (g.ready[you()]) return ["Ready. Waiting for the others… (Not ready lets you change your placements.)", false];
      if (!units.total) return ["No units for you this round: click Ready.", false];
      if (units.free) return [`${plural(units.free, "unit")} to place. Cards are played on your turn.`, false];
      return ["All your units are placed: click Ready.", false];
    }
    if (!myTurn()) return [g.turn ? `${nameOf(g.turn)}'s turn. Your cards wait for your turn.` : "", false];
    if (tool === "remove") return ["Click a road or wall tile to remove it (Esc stops).", false];
    if (tool) return [`Click empty grass to lay a ${tool} tile (Esc stops).`, false];
    if (selection && isBuild(selection.card)) return ["Click the board to build (R turns it).", false];
    if (selection && selection.trash) {
      return [`Click up to ${cardOf(selection.card).trash} other cards to remove from your deck for good, then confirm.`, false];
    }
    if (selection) return ["Click an outlined building.", false];
    if (pick) return [pick.target === "haul" ? "Pick the building to haul from." : "Work with or without a tool?", false];
    if (units.placed) return [`⚠ ${plural(units.placed, "unit")} not resolved yet: lost if you end your turn now.`, true];
    return ["Play cards, buy, build, then End turn.", false];
  }

  function renderBar() {
    const seat = mySeat();
    const p = priv();
    const show = Boolean(seat && p);
    $("bar").hidden = !show;
    $("main").classList.toggle("with-bar", show);
    if (!show) return;
    const g = game();
    const finished = state.phase !== "playing";
    const turnNow = myTurn();
    const main = $("phase-button");
    if (g.phase === "place") {
      const ready = Boolean(g.ready[you()]);
      main.textContent = ready ? "Not ready" : "Ready";
      main.className = ready ? "plain" : "green";
      main.title = ready ? "Take it back to change your placements (until the last player is ready)" : "Done placing";
      main.disabled = finished;
    } else {
      main.textContent = turnNow && myUnits().placed ? `End turn (${myUnits().placed} lost)` : "End turn";
      main.className = turnNow && myUnits().placed ? "red" : "green";
      main.title = "Unresolved units are lost; the next player acts";
      main.disabled = finished || !turnNow;
    }
    const [info, warn] = barInfo();
    $("bar-info").textContent = info;
    $("bar-info").classList.toggle("warn", warn);
    const confirm = $("confirm");
    confirm.hidden = !(selection && selection.trash) || !turnNow;
    if (!confirm.hidden) {
      const n = selection.remove.length;
      confirm.textContent = n ? `Remove ${n} card${n > 1 ? "s" : ""}` : "Play (remove none)";
    }
    for (const t of TOOLS) {
      const b = $(`tool-${t}`);
      if (t === "remove") {
        b.textContent = "✖ Remove (free)";
        b.disabled = !turnNow;
      } else {
        const kind = g.kinds[t];
        const stock = tileStock(t);
        b.textContent = `${kind.icon} ${kind.name} ${stock > 0 ? `(${stock} left)` : `(${g.tileBatch} for ${amounts(kind.cost)})`}`;
        b.title = `${kind.name} tiles are bought ${g.tileBatch} at a time for ${amounts(kind.cost)}, then laid one by one. ${kind.text}`;
        b.disabled = !turnNow || !canLay(t);
      }
      b.classList.toggle("on", tool === t);
    }
    const has = (targets) => Boolean(targets && Object.keys(targets).length);
    $("cards").replaceChildren(...p.hand.map((c) => {
      const card = cardOf(c.card);
      const empty = card.targeted && !has(targetsOf(c.uid));
      const marked = Boolean(selection && selection.trash && selection.remove.includes(c.uid));
      const off = !turnNow || !affordable(costOf(c.card)) || empty;
      const node = panels.cardEl(c.card, { off, selected: Boolean(selection && selection.uid === c.uid), marked });
      node.addEventListener("click", () => clickCard(c));
      return node;
    }));
  }

  function clickCard(instance) {
    if (!myTurn()) {
      if (playing()) showError(game().phase === "place" ? "Place your units first: cards are played on your turn." : `It's ${nameOf(game().turn)}'s turn.`);
      return;
    }
    tool = null;
    pick = null;
    const card = cardOf(instance.card);
    if (selection && selection.trash && instance.uid !== selection.uid) {
      const trash = cardOf(selection.card);
      const at = selection.remove.indexOf(instance.uid);
      if (at >= 0) selection.remove.splice(at, 1);
      else if (card.kind === "curse") return showError("Curses can only be paid off.");
      else if (selection.remove.length >= trash.trash) return showError(`${trash.name} removes up to ${trash.trash} cards.`);
      else selection.remove.push(instance.uid);
      renderBar();
      return;
    }
    if (card.trash) {
      selection = selection && selection.uid === instance.uid ? null
        : { uid: instance.uid, card: instance.card, rotation: 0, trash: true, remove: [] };
      return refresh();
    }
    if (card.kind === "build" || card.targeted) {
      selection = selection && selection.uid === instance.uid ? null : { uid: instance.uid, card: instance.card, rotation: 0 };
      return refresh();
    }
    selection = null;
    send({ action: "play", uid: instance.uid });
    refresh();
  }

  $("confirm").addEventListener("click", () => {
    if (!selection || !selection.trash || !myTurn()) return;
    send({ action: "play", uid: selection.uid, remove: selection.remove });
    selection = null;
    refresh();
  });

  for (const t of TOOLS) {
    $(`tool-${t}`).addEventListener("click", () => {
      if (!myTurn()) return;
      tool = tool === t ? null : t;
      selection = null;
      pick = null;
      refresh();
    });
  }

  $("reroll").addEventListener("click", () => {
    if (myTurn()) send({ action: "reroll" });
  });

  $("phase-button").addEventListener("click", () => {
    if (!playing()) return;
    const g = game();
    if (g.phase === "place") send({ action: "ready", done: !g.ready[you()] });
    else if (myTurn()) send({ action: "end_turn" });
  });

  // --- windows --------------------------------------------------------------------------------

  function renderDeckWindow() {
    const seat = mySeat();
    if (!seat || !$("deck-window").open) return;
    const counts = {};
    for (const id of seat.deck) counts[id] = (counts[id] || 0) + 1;
    $("deck-note").textContent = `${seat.deck.length} cards · ${seat.draw} to draw · ${seat.discard} discarded`;
    $("deck-cards").replaceChildren(...Object.entries(counts).map(([id, n]) => {
      const node = panels.cardEl(id);
      if (n > 1) node.querySelector(".name").textContent += ` ×${n}`;
      return node;
    }));
  }

  $("deck-button").addEventListener("click", () => {
    $("deck-window").showModal();
    renderDeckWindow();
  });
  $("help-button").addEventListener("click", () => $("help-window").showModal());
  document.querySelectorAll("dialog [data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));
})();
