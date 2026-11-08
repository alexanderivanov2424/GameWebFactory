/*
 * Marooned: the game page. Lobby, then the game: status line, prompt box (prompts.js),
 * island board (board.js) and side panels (you, the selected square, camp, players,
 * objectives, log), and the end-of-game scores.
 *
 * Everything is drawn from state.game (public) and state.private (yours); the server sends
 * the answers the page needs (reachable squares in private.moves / private.explorable), so
 * the page has no rules of its own beyond showing costs.
 */
(() => {
  const { $, el, listNames } = AppDom;
  const ICON = MaroonedBoard.ITEM_ICONS;
  const COLORS = ["#e5484d", "#4a5cff", "#1a8a4a", "#d97706", "#8e44ad", "#0e9aa7", "#c2185b", "#5d4037"];
  let state = null;
  let selected = { game: null, key: null };

  const lobby = AppLobby.connect("marooned", {
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
  const send = (message) => lobby.sendGame(message);
  const renderButtons = AppLobbyUI.lobbyButtons(lobby, {
    join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back"),
  });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);
  const updateTurnAlert = AppLobbyUI.turnAlert($("prompt-wrap"));
  const board = MaroonedBoard.create($("board"), { onSquare });

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
    AppLobbyUI.renderPlayers($("players"), lobby, { afterName: () => null });
    AppLobbyUI.renderStart($("start"), lobby);
    AppLobbyUI.renderSpectators($("spectators"), state);
    renderSettings();
  }

  // --- Helpers ------------------------------------------------------------------------------

  const game = () => state.game;
  const priv = () => state.private || {};
  const name = (pid) => game().names[pid] || "?";
  const keyOf = (pos) => `${pos[0]},${pos[1]}`;
  const me = () => game().people[state.you];
  const inGame = () => game().order.includes(state.you);

  function colors() {
    const result = {};
    game().seats.forEach((pid, i) => { result[pid] = COLORS[i % COLORS.length]; });
    return result;
  }

  function canAct() {
    const g = game();
    return state.phase === "playing" && g.stage === "day" && g.turn === state.you && !g.pending && !g.check;
  }

  function button(label, message, props = {}) {
    const b = el("button", { className: "small", ...props }, label);
    b.addEventListener("click", () => send(message));
    return b;
  }

  function items(pack) {
    const entries = Object.entries(pack || {});
    if (!entries.length) return el("span", { className: "muted" }, "nothing");
    return el("span", {}, entries.map(([item, n]) => `${ICON[item] || ""}${n}`).join(" "));
  }

  function onSquare(key, how) {
    if (how === "move") send({ action: "move", cell: key.split(",").map(Number) });
    else if (how === "explore") send({ action: "explore", cell: key.split(",").map(Number) });
    else {
      selected = { game: state.gameNumber, key };
      renderGame();
    }
  }

  // --- Game ---------------------------------------------------------------------------------

  function renderGame() {
    const g = game();
    if (selected.game !== state.gameNumber) selected = { game: state.gameNumber, key: null };
    const mine = inGame() ? keyOf(me().pos) : null;
    const shown = selected.key && g.tiles[selected.key] ? selected.key : mine || keyOf(g.camp);
    const waitingOnMe = state.phase === "playing" && (
      g.actor === state.you ||
      (g.stage === "vote" && inGame() && !(g.voted || {})[state.you]) ||
      (g.stage === "objectives" && inGame() && !(g.picked || {})[state.you]));
    updateTurnAlert(waitingOnMe ? `${state.gameNumber}:${g.day}:${g.stage}:${g.actor}:${g.check ? g.check.step : ""}` : null);
    renderStatus();
    MaroonedPrompts.render($("prompt"), state, send);
    board.draw(g, priv(), state.you, { canAct: canAct(), selected: shown, colors: colors() });
    renderYou();
    renderSquare(shown);
    renderCamp();
    renderPeople();
    renderLog();
    renderResult();
  }

  function renderStatus() {
    const g = game();
    const parts = [el("b", {}, `Day ${g.day} of ${g.monsoon}`)];
    if (g.stage === "day" && g.turn) parts.push(` · ${g.turn === state.you ? "Your turn" : name(g.turn) + "'s turn"}`);
    if (g.stage === "vote") parts.push(" · Night: voting");
    if (g.stage === "objectives") parts.push(" · Picking objectives");
    if (g.launchDay) {
      parts.push(el("span", { className: "launch" },
        g.launchDay === g.day ? " · ⛵ The raft leaves tonight!" : ` · ⛵ The raft leaves at the end of day ${g.launchDay}`));
    }
    parts.push(` · Tiles left: ${g.tilesLeft}`);
    if (priv().role) {
      parts.push(el("span", { className: `role-badge ${priv().role}` },
        priv().role === "imposter" ? "You are the Imposter" : "Castaway"));
    }
    $("status").replaceChildren(...parts);
  }

  function renderYou() {
    const box = $("you");
    if (!inGame()) {
      box.replaceChildren(el("h2", {}, "Watching"), el("p", { className: "muted" }, "You're not on the island."));
      return;
    }
    const g = game();
    const s = me();
    const act = canAct();
    const atCamp = keyOf(s.pos) === keyOf(g.camp);
    const health = [`⚡ ${s.energy}/${s.maxEnergy}`, `🍽 hunger ${s.hunger}/${g.rules.maxHunger}`];
    if (s.wounds) health.push(`🩸 wounds ${s.wounds}`);
    if (s.sick) health.push("🤒 sick");
    if (s.rested) health.push("🛌 rested");
    const pack = Object.entries(s.pack).map(([item, n]) => {
      const row = el("div", { className: "row item-row" }, el("span", { className: "item" }, `${ICON[item] || ""} ${item} × ${n}`));
      if (act && atCamp) {
        row.append(button("→ camp", { action: "deposit", item, count: 1 }, { title: "Put 1 in the stockpile" }));
        if (n > 1) row.append(button("all", { action: "deposit", item, count: n }));
      }
      if (act && item === "food" && s.hunger > 0) row.append(button("Eat", { action: "eat", from: "pack" }, { className: "small green" }));
      if (act && item === "herbs" && (s.wounds || s.sick)) row.append(button("Heal", { action: "heal" }, { className: "small green" }));
      return row;
    });
    const tools = Object.entries(g.rules.tools).map(([key, tool]) => {
      const owned = s.tools.includes(key);
      const cost = Object.entries(tool.cost).map(([item, n]) => `${n}${ICON[item] || item}`).join(" ");
      const affordable = Object.entries(tool.cost).every(([item, n]) => (s.pack[item] || 0) >= n);
      const row = el("div", { className: "row item-row", title: tool.text },
        el("span", { className: "item" }, `${owned ? "✅" : "▫️"} ${tool.name}`), el("span", { className: "muted small" }, owned ? tool.text : cost));
      if (!owned && act) row.append(button("Craft", { action: "craft", tool: key }, { disabled: !affordable, title: `${tool.text} (1 energy)` }));
      return row;
    });
    const end = el("button", { className: "green", disabled: !act }, "End turn");
    end.addEventListener("click", () => send({ action: "end_turn" }));
    box.replaceChildren(
      el("div", { className: "row" }, el("h2", { style: "margin:0" }, "You"), el("span", { className: "spacer" }), end),
      el("p", { className: "health" }, health.join("  ·  ")),
      el("h3", {}, `Backpack (${Object.values(s.pack).reduce((a, b) => a + b, 0)}/${s.capacity})`),
      ...(pack.length ? pack : [el("p", { className: "muted small" }, "Empty.")]),
      el("h3", { style: "margin-top:10px" }, "Tools"),
      ...tools,
      ...objectivesList(),
    );
  }

  function objectivesList() {
    const list = priv().objectives || [];
    if (!list.length) return [];
    return [
      el("h3", { style: "margin-top:10px" }, "Secret objectives"),
      ...list.map((o) => el("p", { className: "small objective" }, el("b", {}, `${o.title} (+${o.points}) `), o.text)),
    ];
  }

  function renderSquare(key) {
    const g = game();
    const box = $("square");
    const tile = g.tiles[key];
    if (!tile) { box.replaceChildren(); return; }
    const kind = g.tileTypes[tile.type];
    const mineHere = inGame() && keyOf(me().pos) === key;
    const act = canAct() && mineHere;
    const s = inGame() ? me() : null;
    const parts = [
      el("h2", {}, `${kind.icon} ${kind.name}${mineHere ? " (you're here)" : ""}`),
      el("p", { className: "muted small" }, kind.text),
    ];
    if (tile.by) parts.push(el("p", { className: "small muted" }, `Explored by ${name(tile.by)}.`));
    const res = Object.entries(tile.res || {});
    if (res.length) {
      parts.push(el("h3", {}, "Resources"));
      for (const [item, n] of res) {
        const row = el("div", { className: "row item-row" }, el("span", { className: "item" }, `${ICON[item]} ${item} × ${n < 0 ? "∞" : n}`));
        if (act) row.append(button("Gather 🎲", { action: "gather", item }, { disabled: !s || s.energy < g.rules.costs.gather, title: "1 energy, secret d6 roll" }));
        parts.push(row);
      }
    }
    if (tile.searches) {
      const row = el("div", { className: "row item-row" }, el("span", { className: "item" }, `🔎 Can be searched ${tile.searches} more time${tile.searches > 1 ? "s" : ""}`));
      if (act) row.append(button("Search", { action: "search" }, { disabled: s.energy < g.rules.costs.search, title: `${g.rules.costs.search} energy` }));
      parts.push(row);
    }
    const pile = Object.entries(tile.pile || {});
    if (pile.length || tile.type === "camp") {
      parts.push(el("h3", {}, tile.type === "camp" ? "Stockpile" : "On the ground"));
      if (!pile.length) parts.push(el("p", { className: "muted small" }, "Empty."));
      for (const [item, n] of pile) {
        const row = el("div", { className: "row item-row" }, el("span", { className: "item" }, `${ICON[item]} ${item} × ${n}`));
        if (act) {
          row.append(button("Take", { action: "take", item, count: 1 }, { disabled: !s || totalPack(s) >= s.capacity }));
          if (item === "food" && tile.type === "camp" && s.hunger > 0) row.append(button("Eat", { action: "eat", from: "camp" }, { className: "small green" }));
        }
        parts.push(row);
      }
    }
    const others = g.order.filter((pid) => pid !== state.you && keyOf(g.people[pid].pos) === key);
    if (others.length) {
      parts.push(el("h3", {}, "People here"));
      for (const pid of others) parts.push(personRow(pid, act, s));
    }
    box.replaceChildren(...parts);
  }

  function totalPack(s) {
    return Object.values(s.pack).reduce((a, b) => a + b, 0);
  }

  function personRow(pid, act, s) {
    const g = game();
    const row = el("div", { className: "row item-row" }, el("span", { className: "item" }, name(pid)));
    if (!act) return row;
    const mine = Object.keys(s.pack);
    if (mine.length) {
      const pick = el("select", {}, ...mine.map((item) => el("option", { value: item }, `${ICON[item]} ${item}`)));
      const give = el("button", { className: "small plain" }, "Give 1");
      give.addEventListener("click", () => send({ action: "give", player: pid, item: pick.value }));
      row.append(pick, give);
    }
    const theirs = Object.keys(g.people[pid].pack);
    const steal = el("select", { title: "Take one item when you attack" },
      el("option", { value: "" }, "steal nothing"), ...theirs.map((item) => el("option", { value: item }, `steal ${ICON[item]} ${item}`)));
    const attack = el("button", { className: "small red", title: `${g.rules.costs.attack} energy: they take a wound (max energy -1)` }, "Attack");
    attack.addEventListener("click", () => {
      if (!confirm(`Attack ${name(pid)}? Everyone will see it.`)) return;
      const message = { action: "attack", player: pid };
      if (steal.value) message.steal = steal.value;
      send(message);
    });
    row.append(steal, attack);
    return row;
  }

  function projectBlock(key, project, act) {
    const parts = [];
    const steps = project.stages.map((stage, i) =>
      el("span", { className: `stage ${i < project.built ? "done" : i === project.built ? "current" : ""}` }, stage.name));
    parts.push(el("div", { className: "row" }, el("b", {}, project.name), ...steps));
    if (project.need) {
      const need = Object.entries(project.need).map(([item, n]) => `${ICON[item]} ${(project.have || {})[item] || 0}/${n}`).join("   ");
      const row = el("div", { className: "row item-row" }, el("span", { className: "item" }, need));
      if (project.patched) row.append(el("span", { className: "small muted" }, "(shaky: no new check)"));
      if (act) row.append(button(`Build ${project.name.toLowerCase()}`, { action: "build", project: key }, { title: "1 energy: puts in everything from your backpack that this stage needs" }));
      parts.push(row);
    } else {
      parts.push(el("p", { className: "small" }, "✅ Finished"));
    }
    return el("div", { className: "project" }, ...parts);
  }

  function renderCamp() {
    const g = game();
    const p = g.projects;
    const act = canAct() && keyOf(me().pos) === keyOf(g.camp);
    const deck = g.checkDeck;
    const total = Object.entries(deck.total).map(([id, n]) => `${deck.cards[id].name} ${n}`).join(", ");
    const revealed = Object.entries(deck.revealed).map(([id, n]) => `${deck.cards[id].name} ${n}`).join(", ") || "none";
    const parts = [
      el("h2", {}, "⛺ Camp"),
      el("p", { className: "small" }, `Shelter spots: ${p.spots} (first to reach camp sleeps inside)`),
      projectBlock("shelter", p.shelter, act),
      projectBlock("raft", p.raft, act),
      el("p", { className: "small muted" }, `Build-check deck: ${deck.left} cards left. Whole deck: ${total}. Revealed since the last shuffle: ${revealed}.`),
    ];
    if (act && !p.raft.need && !g.launchDay) {
      const launch = el("button", { className: "green" }, "⛵ Launch the raft");
      launch.addEventListener("click", () => {
        if (confirm("Launch? The raft leaves at the end of tomorrow with everyone at camp.")) send({ action: "launch" });
      });
      parts.push(launch);
    }
    $("camp").replaceChildren(...parts);
  }

  function renderPeople() {
    const g = game();
    const cols = colors();
    const rows = g.seats.map((pid) => {
      const s = g.people[pid];
      const left = !g.order.includes(pid);
      const flags = [];
      if (pid === g.turn) flags.push("▶");
      if (g.stage === "vote" && (g.voted || {})[pid]) flags.push("🗳");
      if (g.stage === "objectives" && (g.picked || {})[pid]) flags.push("✓");
      const dot = el("span", { className: "dot" });
      dot.style.background = cols[pid];
      const status = [];
      if (s.wounds) status.push(`🩸${s.wounds}`);
      if (s.sick) status.push("🤒");
      if (s.rested) status.push("🛌");
      return el("tr", { className: left ? "left" : pid === state.you ? "me" : "" },
        el("td", {}, flags.join(" ")),
        el("td", {}, dot, ` ${name(pid)}${pid === state.you ? " (you)" : ""}${left ? " (left)" : ""}`),
        el("td", {}, String(s.points)),
        el("td", {}, `${s.energy}/${s.maxEnergy}`),
        el("td", {}, String(s.hunger)),
        el("td", {}, status.join(" ")),
        el("td", {}, items(s.pack)),
        el("td", { className: "small" }, s.tools.map((t) => g.rules.tools[t].name).join(", ")));
    });
    $("people").replaceChildren(el("table", { className: "people" },
      el("thead", {}, el("tr", {}, ...["", "Player", "Pts", "⚡", "🍽", "", "Backpack", "Tools"].map((h) => el("th", {}, h)))),
      el("tbody", {}, ...rows)));
  }

  function renderLog() {
    const g = game();
    const lines = [];
    for (let i = g.logSize - 1; i >= 0 && lines.length < 60; i--) {
      const text = g.log[String(i)];
      if (text) lines.push(el("li", {}, text));
    }
    $("log").replaceChildren(el("h2", {}, "Log"), el("ul", { className: "log" }, ...lines));
  }

  function renderResult() {
    const box = $("result");
    const result = state.phase === "finished" ? state.result : null;
    box.hidden = !result;
    if (!result || !result.scores) { box.replaceChildren(); return; }
    const winners = result.winners.map(name);
    const order = Object.keys(result.scores).sort((a, b) => result.scores[b].total - result.scores[a].total);
    const cards = order.map((pid) => {
      const sc = result.scores[pid];
      return el("div", { className: `score-card${pid === result.imposter ? " imposter" : ""}` },
        el("h3", {}, `${name(pid)}${pid === result.imposter ? " 🎭 Imposter" : ""}: ${sc.total}`),
        el("ul", {}, ...sc.lines.map(([label, points]) => el("li", {}, `${label}: ${points > 0 ? "+" : ""}${points}`))),
        ...sc.objectives.map((o) => el("p", { className: "small" }, `${o.done ? "✅" : "❌"} ${o.title}: ${o.text}`)),
        el("p", { className: "small muted" }, `Announced a worse roll than rolled: ${result.lies[pid] || 0}×`));
    });
    box.replaceChildren(
      el("h2", {}, result.reason),
      el("p", {}, `The Imposter was ${name(result.imposter)}. `,
        result.escaped.length ? `Escaped: ${listNames(result.escaped.map(name))}. ` : "Nobody escaped. ",
        el("b", {}, winners.length ? `Winner: ${listNames(winners)}` : "No winner")),
      el("div", { className: "scores" }, ...cards));
  }
})();
