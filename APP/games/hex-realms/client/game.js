/*
 * Hex Realms: the page glue. Connects to the lobby, keeps the UI state (selection, mode, rotation, tab),
 * turns clicks on the map into game messages, and re-renders the map (map.js) and panels (hud.js,
 * panels.js) from the state. The server validates everything; the ghost colours here are only a hint.
 *
 * ui.mode: null | {type: "build", kind, rot} | {type: "shoot", unit} | {type: "found", unit, rot}
 * (Escape cancels; R or right-click turns). ui.sel: null | {kind: "unit"|"structure", id}.
 * render() runs on each new state (redraws the map); refresh() on UI-only changes (no map redraw).
 */
(() => {
  const { $, el, fill } = AppDom;
  const U = HexMap.util;
  const ui = { sel: null, mode: null, tab: "build", buildCat: null, trade: { give: "gold", get: "food" }, lastRot: 0,
    key: null, flashSeen: null, turnStart: Date.now(), gameNumber: null };
  let state = null;
  let hover = null;
  let idx = { unitAt: {}, structAt: {} };

  const lobby = AppLobby.connect("hex-realms", {
    // The map lives in private.view (fog of war: each viewer gets their own); merge it into game, and
    // keep private only when it has your orders (you're still playing), as the panels expect.
    onState(newState) {
      const p = newState.private;
      state = { ...newState, game: newState.game && p?.view ? { ...newState.game, ...p.view } : newState.game, private: p?.orders ? p : null };
      render();
    },
    onError: (message) => showError(message),
    onConnection(status) { $("connection").textContent = AppLobbyUI.connectionText(status, lobby.roomId); },
  });
  const showError = AppLobbyUI.errorBox($("error"));
  const renderButtons = AppLobbyUI.lobbyButtons(lobby, { join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back") });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);
  const updateTurnAlert = AppLobbyUI.turnAlert($("map"));
  const map = HexMap.create($("map"), { onCell, onHover(k) { hover = k; ghost(); }, onRightClick() { rotate(); } });

  const act = {
    send: (msg) => lobby.sendGame(msg),
    select(kind, id) { ui.sel = kind ? { kind, id } : null; refresh(); },
    setMode(mode) { ui.mode = mode; refresh(); },
    centre: (k) => map.centre(k),
  };

  function ctx() {
    const game = state.game;
    return { game, priv: state.private, you: state.you, me: game.players[state.you], content: game.content, ui, act };
  }

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    renderButtons();
    if (inLobby) {
      updateTurnAlert(null);
      AppLobbyUI.renderPlayers($("players"), lobby, {});
      AppLobbyUI.renderStart($("start"), lobby);
      AppLobbyUI.renderSpectators($("spectators"), state);
      renderSettings();
      return;
    }
    const game = state.game, priv = state.private;
    if (ui.gameNumber !== state.gameNumber) {
      Object.assign(ui, { gameNumber: state.gameNumber, sel: null, mode: null, flashSeen: null });
      map.draw(game, state.you, priv);
      map.centre(home());
    }
    const key = `${state.gameNumber}:${game.turn}:${game.step}`;
    if (key !== ui.key) { ui.key = key; ui.mode = null; ui.turnStart = Date.now(); }
    idx = { unitAt: {}, structAt: {}, siteAt: {} };
    for (const [id, u] of Object.entries(game.units)) idx.unitAt[u.at] = id;
    for (const [id, s] of Object.entries(game.structures)) for (const c of s.cells) idx.structAt[c] = id;
    for (const [id, s] of Object.entries(game.sites || {})) for (const c of s.cells) idx.siteAt[c] = id;
    const pools = { unit: game.units, structure: game.structures, site: game.sites || {} };
    if (ui.sel && !pools[ui.sel.kind]?.[ui.sel.id]) { ui.sel = null; ui.mode = null; }
    map.draw(game, state.you, priv);

    const flashKey = `${state.gameNumber}:${game.step}`;
    if (ui.flashSeen !== null && ui.flashSeen !== flashKey) map.flash(HexPanels.flashCells(game));
    ui.flashSeen = flashKey;

    const alive = !!priv && game.players[state.you]?.alive;
    updateTurnAlert(alive && !priv.done && state.phase === "playing" ? `${state.gameNumber}:${game.turn}` : null);
    renderResult();
    refresh();
  }

  function renderResult() {
    const finished = state.phase === "finished" && state.result;
    $("result").hidden = !finished;
    if (!finished) return;
    const r = state.result, game = state.game;
    const winner = r.winner ? game.players[r.winner] : null;
    fill($("result-text"), 
      el("h2", {}, winner ? [el("span", { style: `color:${winner.color}` }, winner.name), " wins!"] : "Game over"),
      el("p", {}, r.reason || ""),
      Object.entries(r.scores || {}).sort((a, b) => b[1] - a[1]).map(([pid, score]) =>
        el("div", { className: "row" }, HexHud.fmt.nameSpan(game, pid), el("span", { className: "spacer" }), el("b", {}, `${score} points`))));
  }

  // Keep scroll positions while a panel's children are replaced.
  function keep(box, fn) {
    const top = box.scrollTop;
    fn();
    box.scrollTop = top;
  }

  function refresh() {
    if (!state || state.phase === "lobby") return;
    const c = ctx();
    HexHud.fmt.setResources(c.content.resourceInfo);
    const playing = !!c.priv && !!c.me;
    $("col-left").hidden = !playing;
    if (playing) {
      HexHud.topbar($("topbar"), c);
      tick();
      keep($("col-left"), () => {
        HexHud.players($("p-players"), c);
        HexHud.selection($("p-selection"), c);
        HexHud.orders($("p-orders"), c);
        HexHud.trade($("p-trade"), c);
      });
    } else {
      fill($("topbar"), el("span", { className: "hr-turn" }, `Turn ${c.game.turn} / ${c.game.turnLimit}`), el("span", { className: "muted" }, "Spectating"));
    }
    renderTabs(c, playing);
    renderHint(c);
    highlights(c);
    ghost();
  }

  function renderTabs(c, playing) {
    const tabs = playing ? [["build", "Build"], ["advances", "Advances"], ["report", "Report"]] : [["report", "Report"]];
    if (!tabs.some(([id]) => id === ui.tab) && ui.tab !== "none") ui.tab = tabs[0][0];
    fill($("tabs"), tabs.map(([id, label]) => el("button", {
      className: `hr-tab${ui.tab === id ? " on" : ""}`, onclick: () => { ui.tab = ui.tab === id ? "none" : id; refresh(); },
    }, label)));
    const body = $("tab-body");
    body.hidden = ui.tab === "none";
    if (body.hidden) return;
    keep(body, () => {
      if (ui.tab === "build") HexHud.build(body, c);
      else if (ui.tab === "advances") HexPanels.advances(body, c);
      else HexPanels.report(body, c);
    });
  }

  function renderHint(c) {
    const m = ui.mode, box = $("hint");
    box.hidden = !m;
    if (!m) return;
    const cancel = HexHud.fmt.btn("Cancel (Esc)", () => act.setMode(null));
    const names = c.content;
    if (m.type === "build") fill(box, `Placing ${names.structures[m.kind].name}: click to build, R or right-click to turn, Esc to stop. `, cancel);
    else if (m.type === "shoot") fill(box, "Click an enemy unit or structure in range. ", cancel);
    else fill(box, "Found a city here: R turns the footprint, click it (or Confirm) to place. ",
      HexHud.fmt.btn("Confirm", confirmFound, { cls: "endturn" }), cancel);
  }

  const isEnemy = (c, k) => {
    const u = idx.unitAt[k], s = idx.structAt[k];
    return (u && c.game.units[u].owner !== c.you) || (s && c.game.structures[s].owner !== c.you && c.content.structures[c.game.structures[s].type].hp > 0);
  };

  function highlights(c) {
    const h = {}, sel = ui.sel;
    if (c.priv && sel?.kind === "unit" && c.game.units[sel.id]?.owner === c.you) {
      const u = c.game.units[sel.id];
      h[u.at] = "sel";
      if (ui.mode?.type === "shoot" && ui.mode.unit === sel.id) {
        const range = c.content.units[u.type].range;
        for (const k of Object.keys(c.game.cells)) if (k !== u.at && U.dist(k, u.at) <= range) h[k] = isEnemy(c, k) ? "attack" : "range";
      } else if (!ui.mode) {
        for (const k of c.priv.reach[sel.id] || []) h[k] = isEnemy(c, k) ? "attack" : "reach";
      }
    } else if (sel?.kind === "structure" || sel?.kind === "site") {
      for (const k of (sel.kind === "site" ? c.game.sites : c.game.structures)[sel.id].cells) h[k] = "sel";
    } else if (sel?.kind === "unit") h[c.game.units[sel.id].at] = "sel";
    map.setHighlights(h);
  }

  function buildOk(c, def, cells) {
    const mine = new Set(), pending = new Set(c.priv.orders.builds.flatMap((b) => b.cells));
    for (const s of [...Object.values(c.game.structures), ...Object.values(c.game.sites || {})]) if (s.owner === c.you) s.cells.forEach((k) => mine.add(k));
    pending.forEach((k) => mine.add(k));
    const g = c.game;
    return cells.every((k) => k in g.cells && g.territory[k] === c.you && (def.terrain || []).includes(g.cells[k]) && !idx.structAt[k] && !idx.siteAt[k] && !pending.has(k))
      && cells.some((k) => U.neighbors(k).some((n) => mine.has(n)))
      && (!def.coast || cells.some((k) => U.neighbors(k).some((n) => g.cells[n] === "water")));
  }

  function ghost() {
    const m = ui.mode;
    if (!state || state.phase === "lobby" || !m || !state.private) return map.setGhost(null);
    const c = ctx();
    if (m.type === "build" && hover) {
      const def = c.content.structures[m.kind];
      const cells = def.rotations[m.rot].map((d) => U.add(hover, d));
      map.setGhost({ cells, ok: buildOk(c, def, cells), label: def.icon });
    } else if (m.type === "found") {
      const u = c.game.units[m.unit];
      const th = c.content.structures.town_hall;
      map.setGhost(u && { cells: th.rotations[m.rot].map((d) => U.add(u.at, d)), ok: true, label: th.icon });
    } else map.setGhost(null);
  }

  function rotate() {
    const m = ui.mode;
    if (m?.type === "build") { m.rot = (m.rot + 1) % 6; ui.lastRot = m.rot; ghost(); }
    else if (m?.type === "found") {
      const valid = state.private.found[m.unit] || [];
      if (valid.length) m.rot = valid[(valid.indexOf(m.rot) + 1) % valid.length];
      ghost();
    }
  }

  function confirmFound() {
    const m = ui.mode;
    if (m?.type !== "found") return;
    act.send({ action: "found", unit: m.unit, rot: m.rot });
    act.setMode(null);
  }

  function onCell(k) {
    if (!state?.private || state.phase !== "playing") { selectAt(k); return; }
    const c = ctx(), m = ui.mode;
    if (m?.type === "build") {
      act.send({ action: "build", kind: m.kind, at: k, rot: m.rot });
      if (m.kind !== "road") act.setMode(null);
      return;
    }
    if (m?.type === "shoot") { act.send({ action: "shoot", unit: m.unit, at: k }); act.setMode(null); return; }
    if (m?.type === "found") {
      const u = c.game.units[m.unit];
      if (u && c.content.structures.town_hall.rotations[m.rot].some((d) => U.add(u.at, d) === k)) confirmFound();
      return;
    }
    const sel = ui.sel;
    if (sel?.kind === "unit" && c.game.units[sel.id]?.owner === c.you) {
      const u = c.game.units[sel.id];
      if (k === u.at) { act.send({ action: "move", unit: sel.id, to: k }); return; }
      if ((c.priv.reach[sel.id] || []).includes(k)) { act.send({ action: "move", unit: sel.id, to: k }); return; }
    }
    selectAt(k);
  }

  function selectAt(k) {
    if (idx.unitAt[k]) act.select("unit", idx.unitAt[k]);
    else if (idx.structAt[k]) act.select("structure", idx.structAt[k]);
    else if (idx.siteAt[k]) act.select("site", idx.siteAt[k]);
    else act.select(null);
  }

  document.addEventListener("keydown", (e) => {
    if (!state || state.phase === "lobby" || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === "Escape") { if (ui.mode) act.setMode(null); else if (ui.sel) act.select(null); }
    else if (e.key === "r" || e.key === "R") rotate();
  });

  // Your first Town Hall, else your first unit (settlers before the first city), else the middle.
  function home() {
    const game = state?.game;
    if (!game?.structures) return "0,0";
    const hall = Object.values(game.structures).find((s) => s.owner === state.you && s.type === "town_hall");
    const unit = Object.values(game.units).find((u) => u.owner === state.you);
    return hall ? hall.at : unit ? unit.at : "0,0";
  }

  $("centre").addEventListener("click", () => map.centre(home()));

  function tick() {
    const span = $("hr-timer");
    if (!span || !state?.game || state.phase !== "playing") return;
    const left = Math.max(0, state.game.turnSeconds - Math.floor((Date.now() - ui.turnStart) / 1000));
    span.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")} left`;
  }
  setInterval(tick, 1000);
})();
