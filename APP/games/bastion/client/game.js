/*
 * Bastion: the game page. Renders everything from the state (no rules: placement targets come
 * from state.private.targets, effective tower stats from game.structures, sieges as replays).
 *
 * Sections: lobby; status bar (renderStatus); board (BastionBoard + hover ghost, range circles,
 * demolish mode); side panel (renderTeam, renderNext, renderInspector, renderLog); bottom bar
 * (renderHand while building, renderMarket between levels); deck window (retire a card) and help.
 * Siege replays (BastionReplay) play once per battle id, never on the first render after a reload
 * (the status bar's "Watch last siege" button replays it).
 */
(() => {
  const { $, el, svg } = AppDom;
  let state = null;
  let board = null;
  let selection = null; // {uid, card} of the selected hand card
  let demolish = false;
  let hover = null; // {x, y}
  let firstRender = true;
  let seenBattle = 0; // highest battle id already shown (per game number)

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

  const replay = BastionReplay.create({
    overlay: $("overlay"), bar: $("replay-bar"), banner: $("replay-banner"),
    onKeep: () => renderStatus(),
    onEnd: () => render(),
  });

  // --- helpers ----------------------------------------------------------------------------

  const game = () => state.game;
  const mySeat = () => (state.game && state.game.seats[state.you]) || null;
  const priv = () => state.private || null;
  const at = (list, level) => (Array.isArray(list) ? list[Math.min(level, list.length) - 1] : list);
  const perLevel = (v) => (Array.isArray(v) ? v.join("/") : String(v));
  const fmt = (n) => String(Math.round(n * 10) / 10);

  function battleKey() {
    return `bastion:${lobby.roomId}:${state.gameNumber}:battle`;
  }
  function loadSeen() {
    try { return Number(sessionStorage.getItem(battleKey())) || 0; } catch { return 0; }
  }
  function saveSeen(id) {
    seenBattle = id;
    try { sessionStorage.setItem(battleKey(), String(id)); } catch { /* private mode */ }
  }

  function statLines(card, level) {
    const s = card.stats;
    const v = (name) => (level ? fmt(at(s[name], level)) : perLevel(s[name]));
    const parts = [];
    switch (card.kind) {
      case "tower":
        parts.push(`⚔ ${v("damage")}`, `◎ range ${v("range")}`, `every ${v("cooldown")} ticks`);
        if (s.area) parts.push("hits all around");
        if (s.splash) parts.push("splash");
        if (s.pierce) parts.push("ignores armor");
        parts.push(s.air ? "hits flyers" : "ground only");
        if (s.minRange) parts.push(`not closer than ${v("minRange")}`);
        break;
      case "wall": parts.push(`♥ ${v("hp")}`); break;
      case "spikes": parts.push(`${v("damage")} damage per tick`); break;
      case "tar": parts.push(`slows ${v("slow")}%`); break;
      case "barracks": parts.push(`soldiers ♥ ${v("hp")}`, `⚔ ${v("damage")}`, `back after ${v("respawn")} ticks`); break;
      case "farm": parts.push(`+${v("gold")} gold / turn`); break;
      case "forge": parts.push(`+${v("bonus")} damage next to it`); break;
      case "watch": parts.push(`+${v("bonus")} range next to it`); break;
      case "quarry": parts.push(`+${v("labor")} labor / turn`); break;
      case "chapel": parts.push(`keep +${v("keep")}`, `walls +${v("repair")}`); break;
      default: break;
    }
    return parts.join(" · ");
  }

  function cardEl(card, { cost, costClass = "", extra = [], className = "" } = {}) {
    const node = el("div", { className: `pcard ${card.kind === "order" ? "order" : ""} ${className}` },
      el("span", { className: `cost ${costClass}` }, cost),
      el("div", { className: "top" }, el("span", { className: "icon" }, card.icon),
        el("div", {}, el("div", { className: "name" }, card.name),
          el("div", { className: "kind" }, card.kind === "order" ? "order" : `${card.place === "road" ? "road · " : ""}${card.kind}`))),
      el("div", { className: "text", title: card.text }, card.text));
    const stats = statLines(card, 0);
    if (stats) node.append(el("div", { className: "stats" }, stats + (card.maxLevel > 1 ? ` (lvl ${Array.from({ length: card.maxLevel }, (_, i) => i + 1).join("/")})` : "")));
    node.append(...extra);
    return node;
  }

  function foeTitle(enemy) {
    const g = game();
    const bits = [`${enemy.name}: ${enemy.text}`,
      `Health ${Math.round(enemy.hp * g.hpScale)} · speed ${fmt(enemy.speed * 8)} cells/s` +
      (enemy.armor ? ` · armor ${enemy.armor}` : "") + ` · keep damage ${enemy.keep}`];
    if (enemy.flying) bits.push("Flying");
    return bits.join("\n");
  }

  // --- render -------------------------------------------------------------------------------

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    renderButtons();
    if (inLobby) {
      replay.stop();
      firstRender = true;
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
    const seat = mySeat();
    checkSelection();
    if (firstRender) {
      seenBattle = loadSeen();
      if (g.battle && g.battle.id > seenBattle) saveSeen(g.battle.id); // never animate right after a reload
    }
    renderBoard();
    if (g.battle && g.battle.id > seenBattle) {
      saveSeen(g.battle.id);
      replay.play(g, board);
    } else {
      replay.update(g);
    }
    renderResult(finished);
    renderStatus();
    renderTeam();
    renderNext();
    renderInspector();
    renderLog();
    renderBar();
    renderDeckWindow();
    $("help-button").hidden = false;
    const myMove = !finished && seat && !seat.done;
    updateTurnAlert(myMove && !replay.playing ? `${state.gameNumber}:${g.step}` : null);
    firstRender = false;
  }

  function renderResult(finished) {
    const box = $("result");
    box.hidden = !finished || replay.playing;
    if (!finished || !state.result) return;
    const r = state.result;
    box.className = r.victory ? "win" : "loss";
    box.replaceChildren(el("b", {}, r.victory ? "🏆 Victory! " : "💀 Defeat. "), r.reason || "");
  }

  function renderStatus() {
    if (!state || !state.game) return;
    const g = game();
    const level = g.levels[g.level - 1];
    const keep = replay.playing ? replay.keep : g.keep;
    const meter = el("span", { className: "meter" }, el("span"));
    meter.firstChild.style.width = `${Math.max(0, Math.min(100, (keep / g.keepMax) * 100))}%`;
    let stage;
    if (state.phase === "finished") stage = "Game over";
    else if (g.stage === "market") stage = "🛒 Market";
    else stage = `🔨 Build turn ${g.turn} of ${level.buildTurns}`;
    const pips = el("span", { id: "levels" }, ...g.levels.map((lv, i) => {
      const n = i + 1;
      const done = n < g.level || (n === g.level && (g.stage === "market" || (state.result && state.result.victory)));
      return el("span", { className: done ? "done" : n === g.level ? "now" : "", title: `Level ${n}: ${lv.name}\n${lv.text}` }, String(n));
    }));
    const items = [
      el("span", { className: "level" }, `Level ${g.level}/${g.levels.length}: ${level.name}`),
      el("span", { className: "pill" }, stage),
      el("span", { id: "keep-bar", className: "pill" }, "🏰 Keep ", meter, ` ${keep}/${g.keepMax}`),
      pips,
    ];
    if (g.battle && !replay.playing) {
      const watch = el("button", { className: "plain small", textContent: `▶ Watch siege ${g.battle.level}` });
      watch.onclick = () => { replay.play(game(), board); renderResult(state.phase === "finished"); renderStatus(); };
      items.push(watch);
    }
    $("status").replaceChildren(...items);
  }

  // --- board ---------------------------------------------------------------------------------

  function renderBoard() {
    board = BastionBoard.build($("board"), game(), {
      onHover(x, y) { hover = { x, y }; updateHover(); },
      onLeave() { hover = null; updateHover(); },
      onClick: clickCell,
      onCancel: cancel,
    });
    if (!$("ranges")) {
      const layer = svg("svg", { id: "ranges" });
      layer.style.cssText = "position:absolute;inset:3px;width:calc(100% - 6px);height:calc(100% - 6px);pointer-events:none;z-index:2";
      $("board-wrap").append(layer);
    }
    replay.attach(board);
    updateHover();
  }

  function targetsFor(cardId) {
    const p = priv();
    return (p && p.targets && p.targets[cardId]) || {};
  }

  function updateHover() {
    if (!board) return;
    const g = game();
    const ranges = $("ranges");
    if (ranges) ranges.replaceChildren();
    for (const cell of Object.values(board.cells)) {
      cell.classList.remove("ghost-ok", "ghost-bad", "target", "hot");
      cell.querySelectorAll(".ghost-icon, .ghost-cost").forEach((n) => n.remove());
    }
    const k = hover && `${hover.x},${hover.y}`;
    if (selection) {
      const card = g.cards[selection.card];
      const targets = targetsFor(selection.card);
      for (const t of Object.keys(targets)) board.cells[t] && board.cells[t].classList.add("target");
      if (k && board.cells[k]) {
        const cell = board.cells[k];
        const cost = targets[k];
        const seat = mySeat();
        const ok = cost !== undefined && seat && cost <= seat.labor;
        cell.classList.add(ok ? "ghost-ok" : "ghost-bad");
        if (card.kind !== "order" && !g.structures[k]) cell.append(el("span", { className: "ghost-icon" }, card.icon));
        if (cost !== undefined) cell.append(el("span", { className: "ghost-cost" }, `⚒${cost}`));
        const range = priv() && priv().ranges && priv().ranges[selection.card] && priv().ranges[selection.card][k];
        if (range !== undefined) drawRange(hover.x, hover.y, range);
      }
    } else if (k && board.cells[k]) {
      const info = g.structures[k];
      if (demolish) board.cells[k].classList.add(info && (!info.owner || info.owner === state.you) ? "ghost-bad" : "hot");
      if (info && info.range) drawRange(hover.x, hover.y, info.range);
      if (info && info.rally && info.rally.length) {
        const c = BastionBoard.center(info.rally[0], info.rally[1]);
        ranges.append(svg("circle", { cx: c.x, cy: c.y, r: 16, class: "rally-mark" }));
      }
    }
    renderInspector();
  }

  function drawRange(x, y, radius) {
    const c = BastionBoard.center(x, y);
    $("ranges").append(svg("circle", { cx: c.x, cy: c.y, r: radius * BastionBoard.CELL, class: "range" }));
  }

  function clickCell(x, y) {
    const g = game();
    const k = `${x},${y}`;
    if (selection) {
      const targets = targetsFor(selection.card);
      if (targets[k] === undefined) {
        showError(g.cards[selection.card].kind === "order" ? "Pick a structure that can be upgraded." : "You can't build that there.");
        return;
      }
      const seat = mySeat();
      if (seat && targets[k] > seat.labor) {
        showError(`That needs ${targets[k]} labor; you have ${seat.labor}.`);
        return;
      }
      lobby.sendGame({ action: "play", uid: selection.uid, x, y });
      selection = null;
      renderBar();
      updateHover();
      return;
    }
    if (demolish) {
      const info = g.structures[k];
      if (!info) return;
      const name = g.cards[info.card].name;
      if (info.owner && info.owner !== state.you) { showError("You can only demolish your own structures."); return; }
      if (window.confirm(`Demolish this ${name}? You get nothing back.`)) lobby.sendGame({ action: "demolish", x, y });
      demolish = false;
      renderBar();
      updateHover();
    }
  }

  function cancel() {
    if (selection || demolish) {
      selection = null;
      demolish = false;
      renderBar();
      updateHover();
    }
  }

  function checkSelection() {
    const p = priv();
    const seat = mySeat();
    const building = state.phase === "playing" && game().stage === "build" && seat && !seat.done;
    if (!building) { selection = null; demolish = false; return; }
    if (selection && !(p && p.hand.some((c) => c.uid === selection.uid))) selection = null;
  }

  // --- side panel -------------------------------------------------------------------------------

  function renderTeam() {
    const g = game();
    $("team").replaceChildren(...g.order.map((pid) => {
      const s = g.seats[pid];
      const swatch = el("span", { className: "swatch" });
      swatch.style.background = s.color;
      const status = state.phase !== "playing" ? "" : s.done ? "✓ done" : g.stage === "market" ? "shopping…" : "building…";
      return el("li", {}, swatch, el("span", { className: pid === state.you ? "gwf-you" : "" }, s.name + (pid === state.you ? " (you)" : "")),
        el("span", { className: "spacer" }),
        el("span", { className: "stats", title: `Deck: ${s.deck.length} cards` }, `⚒${s.labor} 💰${s.gold} 🂠${s.deck.length}`),
        el("span", { className: s.done ? "done small" : "muted small" }, status));
    }));
  }

  function renderNext() {
    const g = game();
    const box = $("next");
    if (state.phase === "finished") { box.hidden = true; return; }
    box.hidden = false;
    const index = g.stage === "market" ? g.level : g.level - 1;
    const level = g.levels[index];
    const before = new Set(g.levels.slice(0, index).flatMap((lv) => lv.roads));
    let when;
    if (g.stage === "market") when = `Next: level ${index + 1}, after ${level.buildTurns} build turns`;
    else {
      const left = level.buildTurns - g.turn;
      when = left === 0 ? "⚠ The siege comes when this turn ends!" : `Siege in ${left + 1} turns (after turn ${level.buildTurns})`;
    }
    const foes = Object.entries(level.counts).map(([id, n]) => {
      const enemy = g.enemies[id];
      return el("span", { className: "foe", title: foeTitle(enemy) }, el("span", { className: "ic" }, enemy.icon), `×${n}`);
    });
    const roads = level.roads.map((r) => el("span", { className: "road-tag" + (before.has(r) || index === 0 ? "" : " new"), title: before.has(r) || index === 0 ? "" : "This road is used for the first time!" },
      r === "main" ? "Main road" : "Flank road"));
    box.replaceChildren(el("h3", {}, `⚔ ${level.name}`), el("div", { className: "small muted" }, when),
      el("div", { className: "small" }, level.text), el("div", { className: "foes" }, ...foes),
      el("div", { className: "roads" }, "Roads: ", ...roads), el("div", { className: "small muted" }, `Reward: ${level.reward} gold each · enemy health ×${g.hpScale}`));
  }

  function renderInspector() {
    if (!state || !state.game) return;
    const g = game();
    const box = $("inspector");
    const k = hover && `${hover.x},${hover.y}`;
    if (selection && !k) {
      const card = g.cards[selection.card];
      box.replaceChildren(el("div", { className: "title" }, `${card.icon} ${card.name}`),
        el("div", {}, card.kind === "order" ? "Click a structure to upgrade." : "Click a highlighted cell to build (or on the same structure to upgrade). Right-click / Esc cancels."));
      return;
    }
    if (!k) {
      box.replaceChildren(el("div", { className: "title" }, "Inspector"),
        el("div", { className: "muted" }, "Hover the board for details. Hover enemies in the siege panel for their stats."));
      return;
    }
    const info = g.structures[k];
    const [x, y] = [hover.x, hover.y];
    const parts = [];
    if (info) {
      const card = g.cards[info.card];
      const owner = info.owner && g.seats[info.owner] ? g.seats[info.owner].name : info.owner ? g.names[info.owner] : "nobody";
      parts.push(el("div", { className: "title" }, `${card.icon} ${card.name}${card.maxLevel > 1 ? ` — level ${info.level}/${card.maxLevel}` : ""}`));
      parts.push(el("div", { className: "muted" }, `Built by ${owner}`));
      let stats = statLines(card, info.level);
      if (info.damage !== undefined && card.kind === "tower") stats = stats.replace(/^⚔ [\d.]+ · ◎ range [\d.]+/, `⚔ ${fmt(info.damage)} · ◎ range ${fmt(info.range)}`);
      if (info.damage !== undefined && card.kind === "barracks") stats = stats.replace(/⚔ [\d.]+/, `⚔ ${fmt(info.damage)}`);
      if (info.maxHp) stats = `♥ ${info.hp}/${info.maxHp}`;
      parts.push(el("div", {}, stats));
      parts.push(el("div", { className: "small muted" }, card.text));
    } else {
      const map = g.map;
      const isKeep = map.keep[0] === x && map.keep[1] === y;
      const road = Object.entries(map.roads).find(([, cells]) => cells.some(([cx, cy]) => cx === x && cy === y));
      const ground = { ".": "Grass: build towers, barracks, farms…", "^": "Rocks: nothing can be built here.", "~": "Water: nothing can be built here.", T: "Forest: nothing can be built here." }[map.terrain[y][x]];
      if (isKeep) parts.push(el("div", { className: "title" }, `🏰 The keep — ${g.keep}/${g.keepMax}`), el("div", {}, "Enemies that reach it damage it. At 0 the realm falls."));
      else if (road) {
        const entrance = road[1][0][0] === x && road[1][0][1] === y;
        parts.push(el("div", { className: "title" }, road[0] === "main" ? "Main road" : "Flank road"),
          el("div", {}, entrance ? "Enemies enter here; nothing can be built on this cell." : "Walls, spike pits and tar pits go here."));
      } else parts.push(el("div", { className: "title" }, `Cell ${x + 1}, ${y + 1}`), el("div", {}, ground));
    }
    if (selection) {
      const card = g.cards[selection.card];
      const cost = targetsFor(selection.card)[k];
      parts.push(el("div", { className: "small", style: "margin-top:6px" },
        cost === undefined ? `✖ ${card.name} can't go here.` : `${card.icon} ${card.name} here: ${cost} labor${info && card.kind !== "order" ? " (upgrade)" : ""}.`));
    }
    box.replaceChildren(...parts);
  }

  function renderLog() {
    const g = game();
    const box = $("log");
    const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 8;
    const entries = [];
    for (let i = Math.max(0, g.logCount - 80); i < g.logCount; i++) {
      const entry = g.log[String(i)];
      if (!entry) continue;
      const line = el("div", {});
      const seat = entry.pid && g.seats[entry.pid];
      if (seat) {
        const sw = el("span", { className: "swatch" });
        sw.style.cssText = `display:inline-block;margin-right:5px;background:${seat.color}`;
        line.append(sw);
      }
      line.append(entry.text);
      entries.push(line);
    }
    box.replaceChildren(...entries);
    if (stick || firstRender) box.scrollTop = box.scrollHeight;
  }

  // --- bottom bar ------------------------------------------------------------------------------

  function renderBar() {
    const seat = mySeat();
    const g = game();
    const show = state.phase === "playing" && seat;
    $("bar").hidden = !show;
    $("main").classList.toggle("with-bar", !!show);
    if (!show) { $("main").style.paddingBottom = ""; return; }
    if (g.stage === "market") renderMarket(seat);
    else renderHand(seat);
  }

  function renderHand(seat) {
    const g = game();
    const p = priv();
    const end = el("button", { className: seat.done ? "plain" : "green", textContent: seat.done ? "Take back" : "End turn" });
    end.onclick = () => { selection = null; demolish = false; lobby.sendGame({ action: "end_turn", done: !seat.done }); };
    const demo = el("button", { className: demolish ? "red small" : "plain small", textContent: demolish ? "Cancel demolish" : "Demolish…" });
    demo.disabled = seat.done;
    demo.onclick = () => { demolish = !demolish; selection = null; renderBar(); updateHover(); };
    const deck = el("button", { className: "plain small", textContent: `🂠 Deck (${seat.deck.length})` });
    deck.onclick = () => openDeck();
    const waiting = g.order.filter((pid) => !g.seats[pid].done).map((pid) => g.seats[pid].name);
    $("bar-info").replaceChildren(
      el("div", { className: "big" }, `⚒ ${seat.labor} labor · 💰 ${seat.gold}`),
      el("div", { className: "hint" }, `Draw ${seat.draw} · discard ${seat.discard}`),
      end, el("div", { className: "row" }, demo, deck),
      el("div", { className: "hint" }, seat.done ? `Waiting for ${AppDom.listNames(waiting)}…` : demolish ? "Click one of your structures." : selection ? "Click a highlighted cell." : "Pick a card."));
    const hand = (p && p.hand) || [];
    const cards = hand.map((inst) => {
      const card = g.cards[inst.card];
      const targets = targetsFor(inst.card);
      const usable = !seat.done && card.labor <= seat.labor && (!card.place || Object.keys(targets).length > 0);
      const node = cardEl(card, { cost: `⚒${card.labor}`, className: (usable ? "" : "disabled") + (selection && selection.uid === inst.uid ? " selected" : "") });
      node.title = usable ? (!card.place ? "Click to play" : "Click, then pick a cell") : seat.done ? "You've ended your turn" : "Not enough labor (or nowhere to play it)";
      node.onclick = () => {
        if (!usable) return;
        demolish = false;
        if (!card.place) {
          selection = null;
          lobby.sendGame({ action: "play", uid: inst.uid });
          return;
        }
        selection = selection && selection.uid === inst.uid ? null : { uid: inst.uid, card: inst.card };
        renderBar();
        updateHover();
      };
      return node;
    });
    if (!cards.length) cards.push(el("div", { className: "hint" }, "No cards left in hand."));
    $("cards").replaceChildren(...cards);
  }

  function renderMarket(seat) {
    const g = game();
    const done = el("button", { className: seat.done ? "plain" : "green", textContent: seat.done ? "Keep shopping" : "Done shopping" });
    done.onclick = () => lobby.sendGame({ action: "ready", done: !seat.done });
    const deck = el("button", { className: "plain small", textContent: `🂠 Deck (${seat.deck.length}) / retire` });
    deck.onclick = () => openDeck();
    const waiting = g.order.filter((pid) => !g.seats[pid].done).map((pid) => g.seats[pid].name);
    $("bar-info").replaceChildren(el("div", { className: "big" }, `💰 ${seat.gold} gold`),
      el("div", { className: "hint" }, "Buy cards for your deck (copies are unlimited)."),
      done, deck,
      el("div", { className: "hint" }, seat.done ? `Waiting for ${AppDom.listNames(waiting)}…` : ""));
    const offers = (g.market ? g.market.offers : []).map((cardId, slot) => {
      const card = g.cards[cardId];
      const buy = el("button", { className: "small buy", textContent: `Buy (${card.cost} 💰)` });
      buy.disabled = seat.done || card.cost > seat.gold;
      buy.onclick = (event) => { event.stopPropagation(); lobby.sendGame({ action: "buy", slot }); };
      const owned = seat.deck.filter((c) => c === cardId).length;
      return cardEl(card, { cost: `${card.cost}💰`, costClass: "gold",
        extra: [el("div", { className: "hint", style: "color:#6b5a40" }, `⚒${card.labor} labor · you own ${owned}`), buy] });
    });
    $("cards").replaceChildren(...offers);
  }

  // --- windows --------------------------------------------------------------------------------

  function openDeck() {
    const dialog = $("deck-window");
    if (!dialog.open) dialog.showModal();
    renderDeckWindow();
  }

  function renderDeckWindow() {
    const dialog = $("deck-window");
    if (!dialog.open || !state.game) return;
    const g = game();
    const p = priv();
    const seat = mySeat();
    if (!p || !seat) { dialog.close(); return; }
    const canRetire = state.phase === "playing" && g.stage === "market" && !seat.done && !p.retired && seat.gold >= g.rules.retireCost && p.owned.length > g.rules.minDeck;
    const groups = {};
    p.owned.forEach((c) => { (groups[c.card] = groups[c.card] || []).push(c.uid); });
    $("deck-note").textContent = g.stage === "market"
      ? (p.retired ? "You've retired a card this market." : `Retire one card per market for ${g.rules.retireCost} gold (at least ${g.rules.minDeck} cards stay).`)
      : "Cards can be retired at the market.";
    $("deck-cards").replaceChildren(...Object.entries(groups).map(([cardId, uids]) => {
      const card = g.cards[cardId];
      const extra = [];
      if (canRetire) {
        const retire = el("button", { className: "small red buy", textContent: `Retire one (${g.rules.retireCost} 💰)` });
        retire.onclick = () => lobby.sendGame({ action: "retire", uid: uids[0] });
        extra.push(retire);
      }
      return cardEl(card, { cost: `×${uids.length}`, extra });
    }));
  }

  // Keep the page's bottom padding as tall as the fixed bar (its height depends on the cards).
  new ResizeObserver(() => {
    const bar = $("bar");
    $("main").style.paddingBottom = bar.hidden ? "" : `${bar.offsetHeight + 24}px`;
  }).observe($("bar"));

  document.querySelectorAll("dialog [data-close]").forEach((b) => { b.onclick = () => b.closest("dialog").close(); });
  $("help-button").onclick = () => $("help-window").showModal();
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.querySelector("dialog[open]")) cancel();
  });
})();
