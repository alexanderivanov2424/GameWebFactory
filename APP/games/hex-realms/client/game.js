/*
 * Hex Realms: the page glue. Connects to the lobby, keeps the UI state (selection, mode, rotation, tab),
 * turns clicks on the map into game messages, and re-renders the map (map.js) and panels (hud.js,
 * panels.js) from the state. The server validates everything; the ghost colours here are only a hint.
 *
 * Clicking a cell selects what's on it; clicking it again cycles unit -> structure -> construction site.
 * ui.resView: null | a resource, "people", "population" or "housing" shown on the map: greyscale, with what makes it (green +n) and
 * uses it (red -n) each turn, or for "people" where they are (blue "n work" badges), for "population" who lives in each
 * home (blue "x/y" badges), from the report's flows (click its
 * chip on the top bar again or Esc to leave).
 * ui.tech: null | the open tech tree tab (a currency: "science" / "faith"), shown in the #tech popup.
 * ui.mode: null | {type: "build", kind, rot} | {type: "shoot", unit} | {type: "found", unit, rot}
 * (Escape cancels; R or right-click turns). ui.sel: null | {kind: "unit"|"structure", id}; giving a unit a
 * command deselects it (clearing its orders keeps it selected).
 * When a turn resolves, replay.js plays its combats (Esc skips).
 * render() runs on each new state (redraws the map); refresh() on UI-only changes (no map redraw).
 */
(() => {
  const { $, el, fill } = AppDom;
  const U = HexMap.util;
  const ui = { sel: null, mode: null, tab: "build", tech: null, resView: null, buildCat: null, trade: { give: "gold", get: "food" }, lastRot: 0,
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

  const replay = HexReplay.create(map);

  const act = {
    send: (msg) => lobby.sendGame(msg),
    select(kind, id) { ui.sel = kind ? { kind, id } : null; refresh(); },
    setMode(mode) { ui.mode = mode; refresh(); },
    centre: (k) => map.centre(k),
    resView(r) { ui.resView = ui.resView === r ? null : r; refresh(); },
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
      if (replay.playing) replay.skip();
      updateTurnAlert(null);
      AppLobbyUI.renderPlayers($("players"), lobby, {});
      AppLobbyUI.renderStart($("start"), lobby);
      AppLobbyUI.renderSpectators($("spectators"), state);
      renderSettings();
      return;
    }
    const game = state.game, priv = state.private;
    if (ui.gameNumber !== state.gameNumber) {
      replay.skip();
      Object.assign(ui, { gameNumber: state.gameNumber, sel: null, mode: null, flashSeen: null, resView: null });
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
    // A new resolution: replay its combats (replay.js), or just flash the cells when there's nothing to replay.
    if (ui.flashSeen !== null && ui.flashSeen !== flashKey && !replay.play(game, state.you)) map.flash(HexPanels.flashCells(game));
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
    if (!playing) ui.resView = null;
    map.setResView(c.game, ui.resView ? c.priv.report.flows.filter((f) => f[1] === ui.resView) : null,
      Object.fromEntries((c.priv.orders?.builds || []).map((b) => [b.id, { cells: b.cells }])));
    renderHint(c);
    highlights(c);
    ghost();
  }

  function renderTabs(c, playing) {
    const tabs = playing ? [["build", "Build"], ["report", "Report"]] : [["report", "Report"]];
    if (!tabs.some(([id]) => id === ui.tab) && ui.tab !== "none") ui.tab = tabs[0][0];
    fill($("tabs"), tabs.map(([id, label]) => el("button", {
      className: `hr-tab${ui.tab === id ? " on" : ""}`, onclick: () => { ui.tab = ui.tab === id ? "none" : id; refresh(); },
    }, label)), playing ? el("button", {
      className: `hr-tab${ui.tech ? " on" : ""}`, title: "Open the tech tree (science and faith advances)",
      onclick: () => { ui.tech = ui.tech ? null : HexPanels.currencies(c.content)[0]; refresh(); },
    }, "Tech tree") : null);
    renderTech(c, playing);
    const body = $("tab-body");
    body.hidden = ui.tab === "none";
    if (body.hidden) return;
    keep(body, () => {
      if (ui.tab === "build") HexHud.build(body, c);
      else HexPanels.report(body, c);
    });
  }

  // The tech tree: a popup over the map with a tab per currency (science, faith); Esc or ✕ closes it.
  function renderTech(c, playing) {
    const box = $("tech");
    box.hidden = !playing || !ui.tech;
    if (box.hidden) return;
    const { resIcon, resName, btn } = HexHud.fmt;
    fill($("tech-head"), el("h3", {}, "Tech tree"),
      HexPanels.currencies(c.content).map((cur) => el("button", {
        className: `hr-tab${ui.tech === cur ? " on" : ""}`, onclick: () => { ui.tech = cur; refresh(); },
      }, `${resIcon(cur)} ${resName(cur)}`)),
      el("span", { className: "muted small" }, `You have ${c.priv.res[ui.tech] ?? 0} ${resIcon(ui.tech)}`),
      el("span", { className: "spacer" }),
      btn("✕ Close (Esc)", () => { ui.tech = null; refresh(); }));
    keep($("tech-body"), () => HexPanels.techTree($("tech-body"), c, ui.tech));
  }

  function renderHint(c) {
    const m = ui.mode, box = $("hint");
    box.hidden = !m && !ui.resView;
    box.classList.toggle("hr-hintbuild", m?.type === "build");
    if (!m && ui.resView) {
      const { resIcon, resName, btn } = HexHud.fmt, r = ui.resView;
      const text = r === "people" ? "where your people are this turn: green = idle at home, red = in a job, a unit or a recruit ordered there, blue = building"
        : r === "population" ? "blue = people living there / the housing it gives (your people and the people in your units, filling the oldest homes first)"
        : r === "housing" ? "green = the housing each structure gives (your people and the people in your units must fit in it)"
        : "green = made there each turn, red = used each turn (units' upkeep; each person's food where they work, build or rest at home)";
      fill(box, `${resIcon(r)} ${resName(r)} view: ${text}. Faded = not working this turn. Click the resource again or Esc to leave. `,
        btn("Close (Esc)", () => act.resView(null)));
      return;
    }
    if (!m) return;
    const cancel = HexHud.fmt.btn("Cancel (Esc)", () => act.setMode(null));
    const names = c.content;
    if (m.type === "build") {
      // Left: name + controls, then the terrains it can go on (and why the hovered spot is refused);
      // right: the structure card. What it costs and makes shows under the top bar (showDeltas).
      const d = names.structures[m.kind];
      fill(box, el("div", { className: "hr-hintmain" },
        el("div", {}, el("b", {}, `${d.icon || ""} ${d.name}`), ": click to place · R to turn · Esc to cancel"),
        el("div", {}, HexHud.fmt.structInfo(names, d).terrains),
        el("div", { className: "hr-here neg" })), HexHud.structCard(names, d));
    }
    else if (m.type === "claim") fill(box, `Extending territory: click a green cell to make it yours at once (${HexHud.fmt.costText(names.claim.cost)} each, no refund). Each bought cell costs ${names.claim.upkeep} gold a turn. Bought land is weak (dashed): it's lost to an enemy unit on or next to it, if it's cut off from your cities' free land, or to another realm's Town Hall. Esc to stop. `, cancel);
    else if (m.type === "shoot") fill(box, "Click an enemy unit or structure in range. ", cancel);
    else fill(box, "Found a city here: R turns the footprint, click it (or Confirm) to place. ",
      HexHud.fmt.btn("Confirm", confirmFound, { cls: "endturn" }), cancel);
  }

  const isEnemy = (c, k) => {
    const u = idx.unitAt[k], s = idx.structAt[k];
    return (u && c.game.units[u].owner !== c.you) || (s && c.game.structures[s].owner !== c.you && c.content.structures[c.game.structures[s].type].hp > 0);
  };

  // Cells you could claim (the server decides): explored, nobody's, next to your territory, no enemy unit on or next to it.
  function claimable(c) {
    const g = c.game;
    const enemyUnit = (k) => idx.unitAt[k] && g.units[idx.unitAt[k]].owner !== c.you;
    return Object.keys(g.cells).filter((k) => !(k in g.territory) && U.neighbors(k).some((n) => g.territory[n] === c.you)
      && !enemyUnit(k) && !U.neighbors(k).some(enemyUnit));
  }

  function highlights(c) {
    const h = {}, sel = ui.sel;
    if (c.priv && ui.mode?.type === "claim") {
      for (const k of claimable(c)) h[k] = "claim";
    } else if (c.priv && sel?.kind === "unit" && c.game.units[sel.id]?.owner === c.you) {
      const u = c.game.units[sel.id];
      h[u.at] = "sel";
      if (ui.mode?.type === "shoot" && ui.mode.unit === sel.id) {
        const range = c.content.units[u.type].range;
        for (const k of Object.keys(c.game.cells)) if (k !== u.at && U.dist(k, u.at) <= range) h[k] = isEnemy(c, k) ? "attack" : "range";
      } else if (!ui.mode) {
        for (const k of c.priv.reach[sel.id] || []) h[k] = isEnemy(c, k) ? "attack" : "reach";
      }
      const goal = c.priv.auto?.[sel.id]?.goal;
      if (goal && !(goal in h)) h[goal] = "goal";
    } else if (sel?.kind === "structure" || sel?.kind === "site") {
      for (const k of (sel.kind === "site" ? c.game.sites : c.game.structures)[sel.id].cells) h[k] = "sel";
    } else if (sel?.kind === "unit") h[c.game.units[sel.id].at] = "sel";
    map.setHighlights(h);
  }

  // Why the ghost's cells can't take this structure ("" if they look fine): a hint from what you see;
  // the server decides.
  function buildProblem(c, def, cells) {
    const pending = new Set(c.priv.orders.builds.flatMap((b) => b.cells));
    const g = c.game;
    const enemyUnit = (k) => idx.unitAt[k] && g.units[idx.unitAt[k]].owner !== c.you;
    for (const k of cells) {
      if (!(k in g.cells)) return "Part of it is off the map (or unexplored).";
      if (g.territory[k] !== c.you) return "Part of it is outside your territory.";
      if (!(def.terrain || []).includes(g.cells[k])) return `It can't go on ${(c.content.terrain[g.cells[k]]?.name || g.cells[k]).toLowerCase()}.`;
      if (idx.structAt[k] || idx.siteAt[k]) return "Something is already built there.";
      if (pending.has(k)) return "You already ordered a build there.";
      if (enemyUnit(k)) return "An enemy unit stands there.";
    }
    if (def.coast && !cells.some((k) => U.neighbors(k).some((n) => g.cells[n] === "water"))) return "It must touch water.";
    return "";
  }

  // What placing `def` changes, keyed like the top bar's delta slots: its cost (-n, once), what it would
  // make each turn at `cells` (+n/turn; just its base output without a spot), room in the stores, the
  // person it takes while working (people, not the cap), housing, and last the turns to build it.
  function deltas(c, def, kind, cells) {
    const out = {};
    const add = (k, text, cls) => (out[k] ||= []).push([text, cls]);
    for (const [r, n] of Object.entries(def.cost || {})) add(r, `−${n}`, "neg");
    for (const [r, n] of Object.entries(cells ? outputAt(c, def, kind, cells) : (Object.keys(def.onTerrain || {}).length ? {} : def.produce || {})))
      if (n) add(r, `${n > 0 ? "+" : "−"}${Math.abs(n)}/turn`, n > 0 ? "pos" : "neg");
    if (def.storage) for (const r of Object.keys(c.priv.report.caps || {})) add(r, `+${def.storage} room`, "pos");
    for (const [r, n] of Object.entries(def.store || {})) add(r, `+${n} room`, "pos");
    if (def.jobs) add("people", `−${def.jobs} when working`, "neg");
    const housing = (def.housing || 0) + (def.home ? c.priv.homeHousing || 0 : 0);
    if (housing) add("housing", `+${housing}`, "pos");
    const idle = Math.max(0, c.priv.report.idle), now = Math.min(idle, def.hammers);
    add("turns", `🔨 ${def.hammers}${now ? ` · ${now} builder${now === 1 ? "" : "s"} now` : " · no idle people"}`, "");
    return out;
  }

  // A preview of economy.output for `def` placed on `cells` (anchor first), from what you see; the server decides.
  function outputAt(c, def, kind, cells) {
    const g = c.game, out = {};
    const plus = (r, n) => { out[r] = (out[r] || 0) + n; };
    const base = Object.keys(def.onTerrain || {}).length ? def.onTerrain[g.cells[cells[0]]] || {} : def.produce || {};
    for (const [r, n] of Object.entries(base)) plus(r, n);
    for (const k of cells) for (const [r, n] of Object.entries((def.perCell || {})[g.cells[k]] || {})) plus(r, n);
    const mine = new Set(cells);
    const around = [...new Set(cells.flatMap((k) => U.neighbors(k)))].filter((n) => n in g.cells && !mine.has(n));
    const near = [...new Set(around.map((n) => idx.structAt[n]).filter(Boolean))].map((id) => g.structures[id]).filter((s) => s.owner === c.you);
    for (const adj of def.perAdjacent || []) {
      const count = adj.terrain ? around.filter((n) => g.cells[n] === adj.terrain).length
        : near.filter((s) => (adj.type ? s.type === adj.type : adj.tag ? (c.content.structures[s.type]?.tags || []).includes(adj.tag)
          : c.content.structures[s.type]?.home)).length;
      for (const [r, n] of Object.entries(adj.gain || {})) plus(r, n * Math.min(count, adj.max));
    }
    for (const [r, n] of Object.entries((c.priv.typeBonus || {})[kind] || {})) plus(r, n);
    for (const r of Object.keys(out)) if (out[r] < 0) out[r] = 0;  // penalties never make it negative
    return out;
  }

  // Fill the top bar's delta slots (empty them when d is null).
  function showDeltas(d) {
    for (const span of document.querySelectorAll("#topbar .hr-delta")) {
      const key = [...span.classList].find((x) => x.startsWith("hr-delta-"))?.slice(9);
      fill(span, ...((d && d[key]) || []).flatMap(([text, cls], i) => [i ? " " : null, el("span", { className: cls }, text)]));
    }
  }

  function ghost() {
    const m = ui.mode, here = $("hint").querySelector(".hr-here");
    if (here) here.textContent = "";
    showDeltas(null);
    if (!state || state.phase === "lobby" || !m || !state.private) return map.setGhost(null);
    const c = ctx();
    if (m.type === "build") {
      const def = c.content.structures[m.kind];
      const cells = hover && def.rotations[m.rot].map((d) => U.add(hover, d));
      const problem = cells && buildProblem(c, def, cells);
      showDeltas(deltas(c, def, m.kind, cells && !problem ? cells : null));
      const res = $("hint").querySelector(".hr-sres");  // the card's list: this spot's output (base without one)
      if (res) fill(res, ...HexHud.fmt.resListEl(def, cells && !problem ? outputAt(c, def, m.kind, cells) : null));
      if (!cells) return map.setGhost(null);
      map.setGhost({ cells, ok: !problem, label: def.icon });
      if (here && problem) here.textContent = problem;
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
    ui.sel = null;
    act.setMode(null);
  }

  function onCell(k) {
    if (!state?.private || state.phase !== "playing") { selectAt(k); return; }
    const c = ctx(), m = ui.mode;
    if (m?.type === "build") {
      act.send({ action: "build", kind: m.kind, at: k, rot: m.rot });
      act.setMode(null);
      return;
    }
    if (m?.type === "claim") { act.send({ action: "claim", at: k }); return; }  // stays on: claim several
    if (m?.type === "shoot") { act.send({ action: "shoot", unit: m.unit, at: k }); ui.sel = null; act.setMode(null); return; }
    if (m?.type === "found") {
      const u = c.game.units[m.unit];
      if (u && c.content.structures.town_hall.rotations[m.rot].some((d) => U.add(u.at, d) === k)) confirmFound();
      return;
    }
    const sel = ui.sel;
    if (sel?.kind === "unit" && c.game.units[sel.id]?.owner === c.you) {
      const u = c.game.units[sel.id];
      if (k === u.at && thingsAt(k).length > 1) { selectAt(k); return; }  // a structure under it: cycle to it
      if (k === u.at) { act.send({ action: "move", unit: sel.id, to: k }); return; }  // clear (stays selected)
      // In reach: move (or attack) this turn. Further away (except onto another of your units, which
      // selects it): walk there over several turns. Either way the unit is deselected.
      const own = idx.unitAt[k] && c.game.units[idx.unitAt[k]].owner === c.you;
      if ((c.priv.reach[sel.id] || []).includes(k) || !own) { act.send({ action: "move", unit: sel.id, to: k }); act.select(null); return; }
    }
    selectAt(k);
  }

  // Everything on a cell, top first: unit, structure, construction site.
  const thingsAt = (k) => [["unit", idx.unitAt[k]], ["structure", idx.structAt[k]], ["site", idx.siteAt[k]]].filter(([, id]) => id);

  // Selects the first thing on the cell; clicking again moves on to the next one (and wraps round).
  function selectAt(k) {
    const things = thingsAt(k);
    if (!things.length) { act.select(null); return; }
    const i = things.findIndex(([kind, id]) => ui.sel?.kind === kind && ui.sel.id === id);
    act.select(...things[(i + 1) % things.length]);
  }

  document.addEventListener("keydown", (e) => {
    if (!state || state.phase === "lobby" || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === "Escape") { if (replay.playing) replay.skip(); else if (ui.tech) { ui.tech = null; refresh(); } else if (ui.mode) act.setMode(null); else if (ui.sel) act.select(null); else if (ui.resView) act.resView(null); }
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
