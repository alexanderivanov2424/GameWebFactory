/*
 * Bastion: the game page. Renders everything from the state and holds no rules: where a card may
 * go and what it would make there come from state.private.targets; outputs, links and bonus
 * breakdowns from game.structures; card and enemy text from the server.
 *
 * Sections: lobby; status bar (renderStatus); enemy cards (renderFoes, with strike buttons);
 * board (BastionBoard + hover: ghost for blueprints with R / wheel to turn, target outlines for
 * work/repair/cure cards, click an enemy tile to raze it); side panel (renderInspector,
 * renderMarket, renderTeam, renderLog); bottom bar (renderBar: hand, End turn); deck window, help.
 */
(() => {
  const { $, el } = AppDom;
  let state = null;
  let selection = null; // {uid, card, rotation}
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
  const updateTurnAlert = AppLobbyUI.turnAlert($("board-wrap"), { text: "New round!" });
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
  const mySeat = () => (state.game && state.game.seats[state.you]) || null;
  const priv = () => state.private || null;
  const cardOf = (id) => game().cards[id];
  const isBuild = (id) => cardOf(id).kind === "build";
  const icon = (key) => game().icons[key] || "";
  const amounts = (obj) => Object.entries(obj || {}).map(([k, n]) => `${n}${icon(k)}`).join(" ");
  const affordable = (cost) => Object.entries(cost || {}).every(([k, n]) => (game().stock[k] || 0) >= n);
  const canAct = () => state.phase === "playing" && mySeat() && !mySeat().done;
  const targetsOf = (uid) => (priv() && priv().targets[String(uid)]) || null;
  const nameOf = (pid) => game().names[pid] || pid;
  const signed = (n) => (n > 0 ? `+${n}` : String(n));

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

  function shapeEl(cells) {
    const w = Math.max(...cells.map((c) => c[0])) + 1;
    const h = Math.max(...cells.map((c) => c[1])) + 1;
    const filled = new Set(cells.map(([x, y]) => `${x},${y}`));
    const box = el("div", { className: "shape" });
    box.style.gridTemplateColumns = `repeat(${w}, 9px)`;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) box.append(el("i", { className: filled.has(`${x},${y}`) ? "" : "e" }));
    return box;
  }

  function cardEl(cardId, { off = false, selected = false } = {}) {
    const card = cardOf(cardId);
    const kind = card.kind === "build" ? game().kinds[card.structure] : null;
    const node = el("div", { className: `pcard ${card.kind}${off ? " off" : ""}${selected ? " sel" : ""}` });
    node.append(el("div", { className: "name", textContent: card.name }));
    node.append(el("div", { className: "kind", textContent: { build: "Blueprint", action: "Action", curse: "Curse" }[card.kind] }));
    if (kind) {
      node.append(el("span", { className: "icon", textContent: kind.icon || "" }));
      node.append(shapeEl(kind.rotations[0]));
      node.title = kind.text;
    }
    node.append(el("div", { className: "text", textContent: card.text }));
    return node;
  }

  function send(message) {
    lobby.sendGame(message);
  }

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
    board.build(g);
    renderResult(finished);
    renderStatus();
    renderFoes();
    renderMarket();
    renderTeam();
    renderLog();
    renderBar();
    renderDeckWindow();
    updateHover();
    $("help-button").hidden = false;
    const seat = mySeat();
    updateTurnAlert(!finished && seat && !seat.done ? `${state.gameNumber}:${g.step}` : null);
  }

  function renderResult(finished) {
    const box = $("result");
    box.hidden = !finished;
    if (!finished || !state.result) return;
    const r = state.result;
    box.className = r.victory ? "win" : "loss";
    box.replaceChildren(el("b", {}, r.victory ? "🏆 Victory! " : "💀 Defeat. "), r.reason || "");
  }

  function renderStatus() {
    const g = game();
    const coming = Object.values(g.foes).filter((f) => f.state === "coming").map((f) => f.arrives);
    let phase;
    if (coming.length) {
      const next = Math.min(...coming);
      const active = Object.values(g.foes).some((f) => f.state === "active");
      phase = active ? `Next enemy arrives on round ${next}` : `Peace — the next enemy arrives on round ${next}`;
    } else {
      phase = `Every enemy is here: beat them all by the end of round ${g.deadline}`;
    }
    const keep = el("span", { className: "pill" }, "🏰 Keep ",
      el("span", { className: "meter" }, el("span", { style: `width:${Math.round((100 * g.keep) / g.keepMax)}%` })),
      ` ${g.keep}/${g.keepMax}`);
    const pills = g.resources.map(([id, name, ic]) =>
      el("span", { className: `pill${g.stock[id] ? "" : " zero"}`, title: name }, `${ic} ${g.stock[id]}`));
    $("status").replaceChildren(
      el("span", { className: "round" }, `Round ${g.round}`),
      el("span", { className: "phase" }, phase),
      keep, ...pills,
      el("span", { className: `pill${g.soldiers ? "" : " zero"}`, title: "Soldiers" }, `${icon("soldiers")} ${g.soldiers}`));
  }

  // --- enemies ----------------------------------------------------------------------------------

  function renderFoes() {
    const g = game();
    const foes = Object.entries(g.foes).sort((a, b) => Number(a[0]) - Number(b[0]));
    $("foes").replaceChildren(...foes.map(([index, foe]) => foeEl(Number(index), foe)));
  }

  function foeEl(index, foe) {
    if (foe.state === "coming") {
      return el("div", { className: "foe coming" },
        el("div", {}, el("div", { className: "icon" }, "❔"), el("div", {}, `Arrives on round ${foe.arrives}`)));
    }
    if (foe.state === "defeated") {
      return el("div", { className: "foe defeated" },
        el("div", { className: "head" }, el("span", { className: "icon" }, foe.icon), foe.name), el("div", {}, "Beaten"));
    }
    const g = game();
    const node = el("div", { className: "foe" });
    node.append(el("div", { className: "head" }, el("span", { className: "icon" }, foe.icon), foe.name));
    node.append(el("div", { className: "hp" },
      el("span", { className: "meter foe" }, el("span", { style: `width:${Math.round((100 * foe.hp) / foe.maxHp)}%` })),
      `${foe.hp}/${foe.maxHp}`));
    if (foe.text) node.append(el("div", { className: "text" }, foe.text));
    const list = el("ol");
    foe.attacks.forEach((a, i) => list.append(el("li", { className: i === foe.next ? "next" : "", title: a.text },
      el("b", {}, a.name), `: ${a.text}`)));
    node.append(list);
    const beat = el("div", { className: "beat" }, el("b", {}, "Beat it: "));
    const d = foe.defeat;
    if (d.soldiers) {
      const most = Math.min(foe.hp, Math.floor(g.soldiers / d.soldiers));
      beat.append(`${d.soldiers}${icon("soldiers")} per damage.`, el("br"));
      beat.append(strikeButton(index, "soldiers", 1, `Strike (${d.soldiers}${icon("soldiers")})`, most >= 1));
      if (most > 1) beat.append(strikeButton(index, "soldiers", most, `All in ×${most}`, true));
    }
    if (d.resources) {
      beat.append(`${amounts(d.resources)} per damage.`, el("br"));
      beat.append(strikeButton(index, "resources", 1, `Bonfire (${amounts(d.resources)})`, affordable(d.resources)));
    }
    if (d.cure) beat.append("each building of its plague you cure deals 1 damage. ");
    if (d.cards) beat.append("each of its curse cards you pay off deals 1 damage. ");
    if (d.raze) beat.append(`raze every ${foe.lair} tile on the board (click it; ${d.raze}${icon("soldiers")} each). `);
    node.append(beat);
    return node;
  }

  function strikeButton(foe, way, times, label, enabled) {
    const button = el("button", { className: "small", textContent: label });
    button.disabled = !enabled || !canAct();
    button.addEventListener("click", () => send({ action: "strike", foe, way, times }));
    return button;
  }

  // --- board ---------------------------------------------------------------------------------

  function structureCells(uid) {
    const s = game().structures[uid];
    return s ? s.cells : [];
  }

  function showTip(text) {
    const tip = $("tip");
    if (!text || !hover) {
      tip.hidden = true;
      return;
    }
    const r = board.cellRect(hover[0], hover[1]);
    tip.textContent = text;
    tip.style.left = `${r.left + 50}px`;
    tip.style.top = `${r.top - 4}px`;
    tip.hidden = false;
  }

  function updateHover() {
    board.clearMarks();
    if (!state || !state.game) return;
    const g = game();
    let tip = null;
    const at = hover ? board.structureAt(hover[0], hover[1]) : null;
    if (selection && isBuild(selection.card) && hover) {
      const { ax, ay, cells } = anchor(selection.card, selection.rotation, hover[0], hover[1]);
      const spots = (targetsOf(selection.uid) || {})[String(selection.rotation)] || {};
      const value = spots[`${ax},${ay}`];
      board.mark(cells, "ghost");
      if (value === undefined) board.mark(cells, "bad");
      const kind = g.kinds[cardOf(selection.card).structure];
      const key = kind.work ? Object.keys(kind.work.makes)[0] : null;
      tip = value === undefined ? "Can't build here" : key ? `Would make +${value}${icon(key)}` : "Build here";
    } else if (selection) {
      const targets = targetsOf(selection.uid) || {};
      for (const uid of Object.keys(targets)) board.mark(structureCells(uid), "target");
      if (at && targets[at]) {
        board.mark(structureCells(at), "hl");
        tip = targets[at];
      }
    } else if (at) {
      board.mark(structureCells(at), "hl");
    } else if (hover && g.blights[`${hover[0]},${hover[1]}`]) {
      const b = g.blights[`${hover[0]},${hover[1]}`];
      const foe = g.foes[String(b.foe)];
      const cost = b.lair && foe.defeat ? foe.defeat.raze : 1;
      tip = `Click to raze: ${cost}${icon("soldiers")}`;
    }
    showTip(tip);
    renderInspector(at);
  }

  function clickCell(x, y) {
    if (!state || !state.game || !canAct()) return;
    if (selection && isBuild(selection.card)) {
      const { ax, ay } = anchor(selection.card, selection.rotation, x, y);
      const spots = (targetsOf(selection.uid) || {})[String(selection.rotation)] || {};
      if (spots[`${ax},${ay}`] === undefined) return showError("That doesn't fit there.");
      send({ action: "play", uid: selection.uid, x: ax, y: ay, rotation: selection.rotation });
      selection = null;
    } else if (selection) {
      const at = board.structureAt(x, y);
      if (!at || !(targetsOf(selection.uid) || {})[at]) return showError("Pick one of the outlined buildings.");
      send({ action: "play", uid: selection.uid, x, y });
      selection = null;
    } else if (game().blights[`${x},${y}`]) {
      send({ action: "raze", x, y });
    }
    updateHover();
  }

  function turn(direction) {
    selection.rotation = (selection.rotation + direction + 4) % 4;
    updateHover();
  }

  function cancel() {
    if (!selection) return;
    selection = null;
    renderBar();
    updateHover();
  }

  function checkSelection() {
    if (!selection) return;
    const p = priv();
    if (!canAct() || !p || !p.hand.some((c) => c.uid === selection.uid)) selection = null;
  }

  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea, select")) return;
    if (e.key === "Escape") cancel();
    if ((e.key === "r" || e.key === "R") && selection && isBuild(selection.card)) turn(e.shiftKey ? -1 : 1);
  });

  // --- side panel ------------------------------------------------------------------------------

  function partsList(parts) {
    return el("ul", { className: "parts" }, ...parts.map(([why, n]) =>
      el("li", { className: n < 0 ? "minus" : "plus" }, `${signed(n)} ${why}`)));
  }

  function kindInfo(kind) {
    const lines = [];
    if (kind.work) {
      const key = Object.keys(kind.work.makes)[0];
      const uses = Object.keys(kind.work.uses).length ? `${amounts(kind.work.uses)} → ` : "";
      lines.push(el("div", {}, el("b", {}, "Work: "), `${uses}${kind.work.makes[key]}${icon(key)}`));
    }
    if (kind.requires.length) lines.push(el("div", {}, el("b", {}, "Must be "), kind.requires.join(", ")));
    if (kind.bonuses.length) {
      lines.push(el("div", {}, el("b", {}, "Likes / hates:")));
      lines.push(el("ul", { className: "parts" }, ...kind.bonuses.map(([why, n]) =>
        el("li", { className: n < 0 ? "minus" : "plus" }, `${signed(n)} ${why}`))));
    }
    if (Object.keys(kind.cost).length) lines.push(el("div", {}, el("b", {}, "Cost: "), amounts(kind.cost)));
    if (kind.text) lines.push(el("div", { className: "muted" }, kind.text));
    return lines;
  }

  function renderInspector(uid) {
    const g = game();
    const box = $("inspector");
    if (selection && isBuild(selection.card)) {
      const kind = g.kinds[cardOf(selection.card).structure];
      box.replaceChildren(el("h3", {}, `${kind.icon} ${kind.name}`), ...kindInfo(kind),
        el("div", { className: "muted small" }, "R or mouse wheel: turn · right-click or Esc: cancel"));
      return;
    }
    const s = uid ? g.structures[uid] : null;
    if (s) {
      const kind = g.kinds[s.kind];
      const lines = [el("h3", {}, `${kind.icon} ${kind.name}`)];
      if (s.owner) lines.push(el("div", { className: "muted" }, `Built by ${nameOf(s.owner)}`));
      if (kind.work) {
        const key = Object.keys(kind.work.makes)[0];
        const uses = Object.keys(kind.work.uses).length ? `uses ${amounts(kind.work.uses)}, ` : "";
        lines.push(el("div", {}, el("b", {}, `Output: +${s.output}${icon(key)}`), ` (${uses}${s.worked ? "worked this round" : "not worked yet"})`));
        lines.push(partsList(s.parts));
        const link = { depot: "Next to a depot: delivers at once.", road: "Linked by road: goods wait for a Haul.", none: "Cut off: no road to the keep or a storage yard." }[s.link];
        lines.push(el("div", {}, link));
      }
      if (Object.keys(s.store).length) lines.push(el("div", {}, `Stored: ${amounts(s.store)} (max ${g.storeCap})`));
      if (s.plague) lines.push(el("div", { className: "minus" }, "🦠 Plagued: can't work until cured."));
      if (s.frozen) lines.push(el("div", {}, "❄️ Frozen this round."));
      if (s.ruined.length) lines.push(el("div", { className: "minus" }, `🔥 ${s.ruined.length} ruined tile(s): repair before it can work.`));
      if (s.kind !== "keep") lines.push(el("div", { className: "muted" }, `Safe from raids: ${s.protected}/${s.cells.length} tiles`));
      if (kind.text) lines.push(el("div", { className: "muted" }, kind.text));
      box.replaceChildren(...lines);
      return;
    }
    const b = hover ? g.blights[`${hover[0]},${hover[1]}`] : null;
    if (b) {
      const foe = g.foes[String(b.foe)];
      box.replaceChildren(el("h3", {}, `${b.icon} ${b.name}`),
        el("div", {}, `Placed by the ${foe ? foe.name : "enemy"}. Buildings next to it make 1 less.`),
        el("div", {}, b.lair ? "Its lair: razing every tile beats it." : "Raze it with 1 soldier."));
      return;
    }
    box.replaceChildren(el("h3", {}, "Inspector"),
      el("div", { className: "muted" }, "Hover a building to see what it makes and why."));
  }

  function renderMarket() {
    const g = game();
    $("market").replaceChildren(...g.market.map((cardId, slot) => {
      const card = cardOf(cardId);
      const kind = card.kind === "build" ? g.kinds[card.structure] : null;
      const buy = el("button", { className: "small", textContent: `Buy ${card.price}${icon("gold")}` });
      buy.disabled = !canAct() || g.stock.gold < card.price;
      buy.addEventListener("click", () => send({ action: "buy", slot }));
      const row = el("div", { className: "offer", title: kind ? kind.text : card.text },
        el("div", { className: "what" }, el("b", {}, `${kind ? `${kind.icon} ` : ""}${card.name}${kind ? " (blueprint)" : ""}`),
          el("span", {}, card.text)), buy);
      return row;
    }));
  }

  function renderTeam() {
    const g = game();
    $("team").replaceChildren(...Object.entries(g.seats).map(([pid, seat]) => el("li", {},
      el("span", { className: "dot", style: `background:${seat.color}` }),
      el("span", {}, `${seat.name}${pid === state.you ? " (you)" : ""}`),
      el("span", { className: "spacer" }),
      el("span", { className: "muted small" }, `${seat.deck.length} cards`),
      el("span", {}, seat.done ? "✓ done" : "…"))));
  }

  function renderLog() {
    const g = game();
    const lines = [];
    for (let i = g.logCount - 1; i >= Math.max(0, g.logCount - 80); i--) {
      const entry = g.log[String(i)];
      if (entry) lines.push(el("p", {}, el("span", { className: "r" }, `R${entry.round} `), entry.text));
    }
    $("log").replaceChildren(...lines);
  }

  // --- bottom bar ------------------------------------------------------------------------------

  function renderBar() {
    const seat = mySeat();
    const p = priv();
    const show = Boolean(seat && p);
    $("bar").hidden = !show;
    $("main").classList.toggle("with-bar", show);
    if (!show) return;
    const finished = state.phase !== "playing";
    const endTurn = $("end-turn");
    endTurn.textContent = seat.done ? "Take back" : "End turn";
    endTurn.className = seat.done ? "plain" : "green";
    endTurn.disabled = finished;
    let info = "Click a card to use it.";
    if (finished) info = "The game is over.";
    else if (seat.done) info = "Waiting for the others…";
    else if (selection && isBuild(selection.card)) info = "Click the board to build (R turns it).";
    else if (selection) info = "Click an outlined building.";
    $("bar-info").textContent = info;
    $("cards").replaceChildren(...p.hand.map((c) => {
      const card = cardOf(c.card);
      const targets = targetsOf(c.uid);
      const empty = card.targeted && targets && !Object.keys(targets).length;
      const node = cardEl(c.card, { off: !affordable(costOf(c.card)) || empty, selected: selection && selection.uid === c.uid });
      node.addEventListener("click", () => clickCard(c));
      return node;
    }));
  }

  function clickCard(instance) {
    if (!canAct()) return;
    const card = cardOf(instance.card);
    if (card.kind === "build" || card.targeted) {
      selection = selection && selection.uid === instance.uid ? null : { uid: instance.uid, card: instance.card, rotation: 0 };
      renderBar();
      updateHover();
      return;
    }
    send({ action: "play", uid: instance.uid });
  }

  $("end-turn").addEventListener("click", () => {
    const seat = mySeat();
    if (seat) send({ action: "end_turn", done: !seat.done });
  });

  // --- windows --------------------------------------------------------------------------------

  function renderDeckWindow() {
    const seat = mySeat();
    if (!seat || !$("deck-window").open) return;
    const counts = {};
    for (const id of seat.deck) counts[id] = (counts[id] || 0) + 1;
    $("deck-note").textContent = `${seat.deck.length} cards · ${seat.draw} to draw · ${seat.discard} discarded`;
    $("deck-cards").replaceChildren(...Object.entries(counts).map(([id, n]) => {
      const node = cardEl(id);
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
