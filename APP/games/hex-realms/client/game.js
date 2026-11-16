/*
 * Hex Realms page glue: the lobby connection, UI state, clicks on the map, and re-rendering the map and panels.
 * No exports. The server validates everything; checks here are only hints (e.g. ghost colours).
 */
(() => {
  const { $, el, fill } = AppDom;
  const U = HexMap.util;
  // mode: build, shoot, found or claim (Esc cancels); sel: unit, structure or site; resView and tech: map and popup state.
  const ui = { sel: null, mode: null, tab: "build", tech: null, resView: null, buildCat: null, trade: {}, lastRot: 0,
    key: null, flashSeen: null, turnStart: Date.now(), gameNumber: null, hoverCells: null };
  let state = null;
  const ZOOM_TO = 1.6;  // least zoom when an Orders row is clicked
  let hover = null;
  let idx = { unitAt: {}, structAt: {} };

  const lobby = AppLobby.connect("hex-realms", {
    // Fog of war: the map comes from private.view. Keep private only while you have orders.
    onState(newState) {
      const p = newState.private;
      state = { ...newState, game: newState.game && p?.view ? { ...newState.game, ...p.view } : newState.game, private: p?.orders ? p : null };
      render();
    },
    onError: (message) => showError(message),
    onConnection(status) { $("connection").textContent = AppLobbyUI.connectionText(status, lobby.roomId); },
  });
  const showError = AppLobbyUI.errorBox($("error"));
  fill($("rules"), HexText.rules.map(([title, html]) => { const p = el("p", {}, el("b", {}, `${title}. `)); p.insertAdjacentHTML("beforeend", html); return p; }));
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
    // Orders panel: light up a thing's cells while its row is hovered (null clears); glide to it on click.
    hoverCells(cells) { ui.hoverCells = cells; if (state?.game) highlights(ctx()); },
    zoomTo: (cells) => map.focus(cells, Math.max(map.getView().k, ZOOM_TO), 500),
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
    // New resolution: replay its combats, or just flash the cells if there is nothing to replay.
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

  // Panels are rebuilt on each render; keep their scroll position.
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
        HexHud.selection($("p-selection"), c);
        HexHud.orders($("p-orders"), c);
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
    const tabs = playing ? [["build", "Build"], ["players", "Players"], ["report", "Report"]] : [["players", "Players"], ["report", "Report"]];
    if (!tabs.some(([id]) => id === ui.tab) && ui.tab !== "none") ui.tab = tabs[0][0];
    fill($("tabs"), tabs.map(([id, label]) => el("button", {
      className: `hr-tab${ui.tab === id ? " on" : ""}`, onclick: () => { ui.tab = ui.tab === id ? "none" : id; refresh(); },
    }, label)), playing ? el("button", {
      className: `hr-tab${ui.tech ? " on" : ""}`, title: HexText.panels.techOpen,
      onclick: () => { ui.tech = ui.tech ? null : HexPanels.currencies(c.content)[0]; refresh(); },
    }, "Tech tree") : null);
    renderTech(c, playing);
    const body = $("tab-body");
    body.hidden = ui.tab === "none";
    if (body.hidden) return;
    keep(body, () => {
      if (ui.tab === "build") HexHud.build(body, c);
      else if (ui.tab === "players") HexHud.players(body, c);
      else HexPanels.report(body, c);
    });
  }

  // Tech tree popup: one tab per currency; Esc or ✕ closes it.
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
      const text = ["people", "population", "housing"].includes(r) ? HexText.resView[r] : HexText.resView.flow;
      fill(box, HexText.resView.bar(resIcon(r), resName(r), text),
        btn("Close (Esc)", () => act.resView(null)));
      return;
    }
    if (!m) return;
    const cancel = HexHud.fmt.btn("Cancel (Esc)", () => act.setMode(null));
    const names = c.content;
    if (m.type === "build") {
      // Left: name, controls and terrains (and why the spot is refused); right: the card. Costs show in the top bar.
      const d = names.structures[m.kind];
      fill(box, el("div", { className: "hr-hintmain" },
        el("div", {}, el("b", {}, `${d.icon || ""} ${d.name}`), HexText.hint.build),
        el("div", {}, HexHud.fmt.structInfo(names, d).terrains),
        el("div", { className: "hr-here neg" })), HexHud.structCard(names, d));
    }
    else if (m.type === "claim") fill(box, HexText.claim.hint(HexHud.fmt.costText(names.claim.cost), names.claim), cancel);
    else if (m.type === "shoot") fill(box, HexText.hint.shoot, cancel);
    else fill(box, HexText.hint.found,
      HexHud.fmt.btn("Confirm", confirmFound, { cls: "endturn" }), cancel);
  }

  const isEnemy = (c, k) => {
    const u = idx.unitAt[k], s = idx.structAt[k];
    return (u && c.game.units[u].owner !== c.you) || (s && c.game.structures[s].owner !== c.you && c.content.structures[c.game.structures[s].type].hp > 0);
  };

  // Cells you could claim (a hint; the server decides).
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
    for (const k of ui.hoverCells || []) h[k] = "focus";
    map.setHighlights(h);
  }

  // Why the ghost cells can't take this structure ("" if fine). A hint; the server decides.
  function buildProblem(c, def, cells) {
    const pending = new Set(c.priv.orders.builds.flatMap((b) => b.cells));
    const g = c.game;
    const enemyUnit = (k) => idx.unitAt[k] && g.units[idx.unitAt[k]].owner !== c.you;
    for (const k of cells) {
      if (!(k in g.cells)) return HexText.hint.problem.offMap;
      // Mirrors orders.placeable: yours, or (def.outside: Walls, Towers) nobody's and next to yours.
      if (g.territory[k] !== c.you && !(def.outside && !(k in g.territory) && U.neighbors(k).some((n) => g.territory[n] === c.you)))
        return def.outside ? HexText.hint.problem.outsideNear : HexText.hint.problem.outside;
      if (!(def.terrain || []).includes(g.cells[k])) return HexText.hint.problem.terrain((c.content.terrain[g.cells[k]]?.name || g.cells[k]).toLowerCase());
      if (idx.structAt[k] || idx.siteAt[k]) return HexText.hint.problem.built;
      if (pending.has(k)) return HexText.hint.problem.ordered;
      if (enemyUnit(k)) return HexText.hint.problem.enemy;
    }
    if (def.coast && !cells.some((k) => U.neighbors(k).some((n) => g.cells[n] === "water"))) return HexText.hint.problem.coast;
    return "";
  }

  // What placing `def` changes, keyed by top-bar delta slot; output is previewed at `cells`.
  function deltas(c, def, kind, cells) {
    const out = {};
    const add = (k, text, cls) => (out[k] ||= []).push([text, cls]);
    for (const [r, n] of Object.entries(def.cost || {})) add(r, `−${n}`, "neg");
    for (const [r, n] of Object.entries(cells ? outputAt(c, def, kind, cells) : (Object.keys(def.onTerrain || {}).length ? {} : def.produce || {})))
      if (n) add(r, `${n > 0 ? "+" : "−"}${Math.abs(n)}${(c.content.flat || []).includes(r) ? "" : "/turn"}`, n > 0 ? "pos" : "neg");
    if (def.storage) for (const r of Object.keys(c.priv.report.caps || {})) add(r, `+${def.storage} room`, "pos");
    for (const [r, n] of Object.entries(def.store || {})) add(r, `+${n} room`, "pos");
    const jobs = cells ? jobsAt(c, def, cells) : def.jobs || 0;
    if (jobs) add("people", `−${jobs} when working`, "neg");
    const housing = (def.housing || 0) + Object.entries(c.priv.housingBonus || {}).reduce((n, [tag, b]) => n + ((def.tags || []).includes(tag) ? b : 0), 0);
    if (housing) add("housing", `+${housing}`, "pos");
    const idle = Math.max(0, c.priv.report.idle), now = Math.min(idle, def.hammers);
    add("turns", `🔨 ${def.hammers}${now ? ` · ${now} builder${now === 1 ? "" : "s"} now` : " · no idle people"}`, "");
    return out;
  }

  // Preview of `def`'s output on `cells` (anchor first); the server decides.
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
      const count = adj.terrain ? around.filter((n) => g.cells[n] === adj.terrain && !idx.structAt[n] && !idx.siteAt[n]).length
        : adj.unique ? new Set(near.map((s) => s.type)).size
        : near.filter((s) => (adj.type ? s.type === adj.type : (c.content.structures[s.type]?.tags || []).includes(adj.tag))).length;
      const times = adj.needs ? (count >= adj.needs ? 1 : 0) : Math.min(count, adj.max);
      for (const [r, n] of Object.entries(adj.gain || {})) plus(r, n * times);
    }
    for (const [r, n] of Object.entries((c.priv.typeBonus || {})[kind] || {})) plus(r, n);
    for (const r of Object.keys(out)) if (out[r] <= 0) delete out[r];  // penalties never make it negative
    // Boosts from own working neighbours (+add to each resource it makes).
    const working = new Set(c.priv.report.staffed || []);
    const matches = (b) => (b.type ? b.type === kind : (def.tags || []).includes(b.tag));
    const add = near.filter((s) => working.has(s.id)).reduce((n, s) =>
      n + (c.content.structures[s.type]?.boost || []).filter(matches).reduce((x, b) => x + b.add, 0), 0);
    if (add) for (const r of Object.keys(out)) out[r] += add;
    return out;
  }

  // Workers it would need at `cells` (none while a freeNear structure touches that terrain).
  const jobsAt = (c, def, cells) => (def.jobs && def.freeNear && cells.some((k) => U.neighbors(k).some((n) => c.game.cells[n] === def.freeNear)) ? 0 : def.jobs || 0);

  // Fill the top bar's delta slots; null empties them.
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
      const res = $("hint").querySelector(".hr-sres");  // the card's list: this spot's output, or the base output without a spot
      if (res) fill(res, ...HexHud.fmt.resListEl(def, cells && !problem
        ? { res: outputAt(c, def, m.kind, cells), jobs: jobsAt(c, def, cells), terrain: c.game.cells[cells[0]] } : null));
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
    if (m?.type === "claim") { act.send({ action: "claim", at: k }); return; }  // stays in claim mode
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
      // In reach: move or attack now; farther away walks over several turns. Either way it deselects.
      const own = idx.unitAt[k] && c.game.units[idx.unitAt[k]].owner === c.you;
      if ((c.priv.reach[sel.id] || []).includes(k) || !own) { act.send({ action: "move", unit: sel.id, to: k }); act.select(null); return; }
    }
    selectAt(k);
  }

  // Everything on a cell, top first: unit, structure, construction site.
  const thingsAt = (k) => [["unit", idx.unitAt[k]], ["structure", idx.structAt[k]], ["site", idx.siteAt[k]]].filter(([, id]) => id);

  // Selects the first thing on the cell; each click moves to the next (wrapping).
  function selectAt(k) {
    const things = thingsAt(k);
    if (!things.length) { act.select(null); return; }
    const i = things.findIndex(([kind, id]) => ui.sel?.kind === kind && ui.sel.id === id);
    act.select(...things[(i + 1) % things.length]);
  }

  document.addEventListener("keydown", (e) => {
    if (!state || state.phase === "lobby" || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === "Escape") { if (replay.playing) replay.skip(); else if (ui.tech) { ui.tech = null; refresh(); } else if (ui.mode) act.setMode(null); else if (ui.sel) act.select(null); else if (ui.resView) act.resView(null); }
    else if ((e.key === "Enter" || e.key === " ") && replay.playing) { e.preventDefault(); replay.next(); }
    else if (e.key === "r" || e.key === "R") rotate();
  });

  // Your first Town Hall, else your first unit, else 0,0.
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
