/*
 * Planet Jumpers: game page script. Renders everything from the server state (no rules here).
 *   renderLobby()   players, the "run" setting, the host's saved run (state.game.save)
 *   renderGame()    renderMission() (left: task names only) + renderShip() (left), renderTable()
 *                   (seats around the round table with their taken tasks below them, the tasks
 *                   being drafted in the middle, cards played this trick), renderStatus() (draft
 *                   pass, whose turn, end early, debrief, result), renderPlayers() + log (right),
 *                   renderHand() (bottom bar)
 * Messages: take / pass (draft), play (a card), end (host: end the mission early), next (host,
 * after a mission). See server.py.
 */
(() => {
  const { $, el, fill } = AppDom;
  const SUIT_NAMES = { r: "Red", b: "Blue", y: "Yellow", g: "Green", k: "Black" };
  const STATUS = { done: "Done", failed: "Failed", open: "Open" };
  // A done task that can still fail (can_fail_when_done, cards left) shows "Done so far".
  const statusText = (t) => (t.status === "done" && !t.secured ? "Done so far" : STATUS[t.status]);
  let state = null;

  const lobby = AppLobby.connect("orbit-run", {
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
  const updateTurnAlert = AppLobbyUI.turnAlert($("table-wrap"));

  const send = (data) => lobby.sendGame(data);
  const name = (pid) => state.game.names[pid] || "?";

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    $("hand-bar").hidden = inLobby || !state.private;
    document.querySelector("h1").hidden = !inLobby;
    renderButtons();
    if (inLobby) renderLobby();
    else renderGame();
  }

  // --- Lobby ----------------------------------------------------------------------------

  function renderLobby() {
    updateTurnAlert(null);
    AppLobbyUI.renderPlayers($("players"), lobby, { afterName: () => null });
    AppLobbyUI.renderStart($("start"), lobby);
    AppLobbyUI.renderSpectators($("spectators"), state);
    renderSettings();
    const save = state.game && state.game.save;
    let text = "The host has no saved run.";
    if (save) {
      const s = save.ship;
      const over = save.over === "destroyed" ? " (destroyed: can't continue)"
        : save.over === "complete" ? " (complete: can't continue)" : "";
      text = `Host's saved run: ${save.missions} mission${save.missions === 1 ? "" : "s"} played${over}. `
        + `Hull ${s.health}/${save.caps.health}, fuel ${s.fuel}/${save.caps.fuel}, food ${s.food}/${save.caps.food}, science ${s.science}.`;
    }
    $("save").textContent = text;
  }

  // --- Game -----------------------------------------------------------------------------

  function cardFace(card) {
    const suit = card[0];
    const value = card.slice(1);
    return el("div", { className: `pcard s-${suit}`, title: `${SUIT_NAMES[suit]} ${value}` },
      el("span", { className: "corner" }, value),
      el("span", { className: "big" }, value),
      el("span", { className: "corner", style: "text-align: right" }, suit === "k" ? "★" : ""));
  }

  function renderGame() {
    const game = state.game;
    const finished = state.phase === "finished";
    const myTurn = !finished && game.turn === state.you;
    const mission = game.mission;
    updateTurnAlert(myTurn && mission
      ? `${state.gameNumber}:${mission.number}:${game.stage}:${game.trick.number}:${game.trick.plays.length}:${game.draft ? game.draft.left.length : ""}`
      : null);
    $("result").hidden = !finished;
    $("result").textContent = finished && state.result ? state.result.reason : "";
    renderMission(game);
    renderShip(game);
    renderTable(game);
    renderStatus(game, myTurn, finished);
    renderPlayers(game);
    renderHand(game, myTurn);
    fill($("log"), game.log.slice(-12).map((line) => el("li", {}, line)));
    const log = $("log");
    log.scrollTop = log.scrollHeight;
  }

  function renderMission(game) {
    const m = game.mission;
    if (!m) return fill($("mission"), el("div", { className: "muted" }, "No mission."));
    fill($("mission"),
      el("div", { className: "label" }, `Mission ${m.number} · Deck ${m.deck}`),
      el("h2", {}, m.name),
      el("div", { className: "yields" }, el("span", {}, `⛽ Refuel ${m.fuel}`), el("span", {}, `🍞 Food ${m.food}`)),
      el("div", { className: "label" }, "Tasks"),
      m.tasks.map((t) => el("div", { className: `task-name ${t.owner ? t.status : "open"}`, title: t.text }, t.name)),
      el("div", { className: "label", style: "margin-top: 8px" }, "Setup"),
      m.setup.length ? m.setup.map((line) => el("div", { className: "small" }, line))
        : el("div", { className: "small muted" }, "No special setup."));
  }

  function meter(label, key, value, cap) {
    const pips = [];
    for (let i = 0; i < cap; i++) pips.push(el("span", { className: `pip ${key}${i < value ? " on" : ""}` }));
    return el("div", { className: "meter" }, el("span", {}, label), el("span", { className: "pips" }, pips),
      el("span", { className: "muted" }, `${value}/${cap}`));
  }

  function renderShip(game) {
    const run = game.run;
    const s = run.ship;
    fill($("ship"),
      el("div", { className: "label" }, "Ship"),
      meter("Hull", "health", s.health, run.caps.health),
      meter("Fuel", "fuel", s.fuel, run.caps.fuel),
      meter("Food", "food", s.food, run.caps.food),
      el("div", { className: "meter" }, el("span", {}, "Science"), el("span", {}, String(s.science)), el("span")),
      el("div", { className: "label", style: "margin-top: 8px" }, "Run"),
      el("div", { className: "small" }, `Missions played: ${run.missions}`),
      el("div", { className: "small muted" }, `Mission decks left: ${[1, 2, 3].map((d) => game.decks[String(d)]).join(" / ")}`));
  }

  // A task card: name, its text, and its status once someone holds it.
  function taskCard(t, onclick) {
    return el(onclick ? "button" : "div", { className: `task ${t.owner ? t.status : "open"}`, onclick },
      el("div", { className: "task-head" },
        el("span", {}, t.name),
        t.owner ? el("span", { className: `pill ${t.status}` }, statusText(t)) : null),
      el("div", { className: "task-text" }, t.text));
  }

  // Seats around the circle, you at the bottom (spectators: the first seat), clockwise; each
  // seat's taken tasks hang below it. While drafting, the tasks left sit in the middle.
  function renderTable(game) {
    const wrap = $("table-wrap");
    wrap.querySelectorAll(".seat, .played").forEach((node) => node.remove());
    wrap.style.height = "";
    if (!game.mission) return fill($("table-center"));
    const seats = game.seats;
    const mine = Math.max(0, seats.indexOf(state.you));
    const cx = 300, cy = 260;
    const angleOf = (i) => Math.PI / 2 + ((i - mine + seats.length) % seats.length) * (2 * Math.PI / seats.length);
    const tasksOf = (pid) => game.mission.tasks.filter((t) => t.owner === pid);
    seats.forEach((pid, i) => {
      const a = angleOf(i);
      const seat = el("div", { className: "seat" },
        el("div", { className: `seat-box${game.turn === pid ? " turn" : ""}` },
          el("div", { className: "who" },
            pid === game.captain ? el("span", { className: "captain", title: "Captain (holds the black 4)" }, "★ CPT") : null,
            el("span", {}, name(pid) + (pid === state.you ? " (you)" : ""))),
          el("div", { className: "stats" }, `${game.handSizes[pid]} cards · ${game.tricksWon[pid]} tricks`)),
        el("div", { className: "seat-tasks" }, tasksOf(pid).map((t) => taskCard(t))));
      seat.style.left = `${cx + Math.cos(a) * 228}px`;
      seat.style.top = `${cy + Math.sin(a) * 222}px`;
      wrap.append(seat);
    });
    const trick = game.trick;
    trick.plays.forEach((play) => {
      const a = angleOf(seats.indexOf(play.pid));
      const node = el("div", { className: `played${trick.winner === play.pid ? " winner" : ""}` }, cardFace(play.card));
      node.style.left = `${cx + Math.cos(a) * 105}px`;
      node.style.top = `${cy + Math.sin(a) * 105}px`;
      wrap.append(node);
    });
    if (game.stage === "draft") {
      const myPick = state.phase !== "finished" && game.turn === state.you;
      const byId = Object.fromEntries(game.mission.tasks.map((t) => [t.id, t]));
      fill($("table-center"), el("div", { className: "draft-label" }, myPick ? "Your pick: click a task" : "Task draft"),
        game.draft.left.map((id) => taskCard(byId[id], myPick ? () => send({ action: "take", task: id }) : undefined)));
    } else {
      fill($("table-center"), game.stage === "collect" ? `${name(trick.winner)} wins the trick`
        : game.stage === "play" ? `Trick ${trick.number}${trick.plays.length ? ` · ${SUIT_NAMES[trick.plays[0].card[0]]} led` : ""}`
        : game.stage === "debrief" ? "Mission over" : "");
    }
    // Grow the table area so the bottom seat's tasks don't run into the status panel.
    const top = wrap.getBoundingClientRect().top;
    let bottom = 0;
    wrap.querySelectorAll(".seat").forEach((node) => { bottom = Math.max(bottom, node.getBoundingClientRect().bottom - top); });
    if (bottom + 8 > wrap.offsetHeight) wrap.style.height = `${Math.ceil(bottom + 8)}px`;
  }

  function renderStatus(game, myTurn, finished) {
    const box = $("status-body");
    if (!game.mission) return fill(box);
    if (game.stage === "draft") {
      const draft = game.draft;
      if (!myTurn) return fill(box, el("p", {}, `Task draft: ${name(draft.turn)} is choosing.`));
      return fill(box,
        el("p", {}, el("b", {}, "Your pick: "), "take a task from the middle of the table",
          draft.canPass ? " or pass." : " (you can't pass)."),
        draft.canPass ? el("div", { className: "choices" },
          el("button", { className: "plain", onclick: () => send({ action: "pass" }) }, "Pass")) : null);
    }
    if (game.stage === "play" || game.stage === "collect") {
      return fill(box,
        el("p", {}, game.stage === "collect" ? `${name(game.trick.winner)} wins the trick.`
          : myTurn ? el("b", {}, "Your turn: play a card.") : `${name(game.turn)} is playing.`),
        game.canEndEarly && !finished ? endEarly() : null);
    }
    if (game.stage === "debrief") {
      const byId = Object.fromEntries(game.mission.tasks.map((t) => [t.id, t]));
      const isHost = lobby.isHost();
      return fill(box,
        el("h2", {}, `${game.mission.name}: mission report`),
        el("ul", { className: "debrief" }, (game.debrief || []).map((r) =>
          el("li", {}, el("b", {}, byId[r.id].name), ` (${byId[r.id].owner ? name(byId[r.id].owner) : "nobody"}): `,
            STATUS[r.status], r.effects.length ? ` → ${r.effects.join(", ")}` : ""))),
        finished ? null : isHost
          ? el("div", {}, el("button", { className: "green", onclick: () => send({ action: "next" }) }, "Next mission"))
          : el("p", { className: "muted" }, "Waiting for the host to start the next mission."));
    }
    return fill(box);
  }

  // Every task is done and none can fail any more: the host may end the mission now.
  function endEarly() {
    return el("div", { className: "end-early" },
      el("p", {}, "Every task is done and can't fail any more."),
      lobby.isHost()
        ? el("button", { className: "green", onclick: () => send({ action: "end" }) }, "End mission")
        : el("p", { className: "muted" }, "The host can end the mission now."));
  }

  function renderPlayers(game) {
    fill($("plist"), game.seats.map((pid) => el("li", { className: game.turn === pid ? "turn" : "" },
      game.turn === pid ? "▶" : null,
      pid === game.captain ? el("span", { className: "captain" }, "★") : null,
      el("span", {}, name(pid) + (pid === state.you ? " (you)" : "")),
      el("span", { className: "count" }, game.handSizes ? `${game.handSizes[pid]} 🂠` : ""))));
  }

  function renderHand(game, myTurn) {
    const mine = state.private;
    if (!mine) return;
    const playing = myTurn && game.stage === "play";
    const can = new Set(playing ? mine.playable : []);
    $("hand").classList.toggle("myturn", playing);
    $("hand-label").textContent = playing
      ? (game.trick.plays.length && can.size < mine.hand.length ? `Your turn: follow ${SUIT_NAMES[game.trick.plays[0].card[0]]}` : "Your turn: click a card to play it")
      : `Your hand (${mine.hand.length})`;
    fill($("hand"), mine.hand.map((card) => {
      const face = cardFace(card);
      if (can.has(card)) {
        face.classList.add("can");
        face.onclick = () => send({ action: "play", card });
      }
      return face;
    }));
  }
})();
