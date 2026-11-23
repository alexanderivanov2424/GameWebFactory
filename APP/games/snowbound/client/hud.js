/*
 * Snowbound HUD: everything drawn over the map except the map itself, refreshed ~5 times a second.
 *   SB.hud.init(lobby)     once (button handlers)
 *   SB.hud.refresh(state)  update every HUD box from the state
 *   SB.hud.reset()         new game (rebuild the machine rows and upgrade buttons)
 *   SB.hud.toggle(name)    open/close the side panel: "machines" | "upgrades" | "team" | null (close)
 *   SB.hud.buildHut(), buildDepot(), follow(), anywhere()   hotbar actions (also keys H, Q, F, R)
 *   SB.hud.roadTool(level)  show the road tool box with that level picked (0 hides it; input.js owns the tool)
 *   SB.hud.demolishTool(on) light the Demolish button; SB.hud.beltTool(on) the Conveyors button and its hint box
 * Buttons are built once and updated in place (machines, supplies) or rebuilt only when their list
 * changes (upgrades), so a click never lands on a button that was just replaced.
 *   SB.fmt(n)   short number: 9.5, 950, 1.2k, 3.4M, 5.6B
 */
(() => {
  const SB = (window.SB = window.SB || {});
  const { $, el, fill } = AppDom;

  SB.fmt = (n) => {
    if (!isFinite(n)) return "0";
    const a = Math.abs(n);
    if (a < 10) return String(Math.round(n * 10) / 10);
    if (a < 1000) return String(Math.round(n));
    for (const [u, v] of [["T", 1e12], ["B", 1e9], ["M", 1e6], ["k", 1e3]]) {
      if (a >= v) return (n / v).toFixed(a / v >= 100 ? 0 : a / v >= 10 ? 1 : 2) + u;
    }
    return String(Math.round(n));
  };
  const fmt = SB.fmt;
  const money = (n) => "$" + fmt(n);

  const FEATURE_NAMES = { ".": "Snow", ",": "Cleared ground", x: "Cabin", X: "Cabin", t: "Forest", T: "Forest (logs found)",
    h: "Buried cabin", H: "Dug-out cabin", g: "Gas station", G: "Gas station", C: "Supply cache", K: "Skier rescued", S: "Ruins" };
  const hud = (SB.hud = {});
  let lobby = null, panel = null, machineRows = null, upgradeKey = null, upgradeButtons = [], logCount = null, miniAt = 0;

  hud.toggle = (name) => {
    panel = name === panel ? null : name;
    $("hudPanel").hidden = !panel;
    $("panelMachines").hidden = panel !== "machines";
    $("panelUpgrades").hidden = panel !== "upgrades";
    $("panelTeam").hidden = panel !== "team";
    $("tabMachines").classList.toggle("on", panel === "machines");
    $("tabUpgrades").classList.toggle("on", panel === "upgrades");
    $("tabTeam").classList.toggle("on", panel === "team");
  };
  hud.buildHut = () => lobby.sendGame({ action: "hut" });
  hud.buildDepot = () => lobby.sendGame({ action: "depot" });
  hud.demolishTool = (on) => $("demolishTool").classList.toggle("on", on);
  hud.beltTool = (on) => {
    $("beltTool").classList.toggle("on", on);
    $("hudBelts").hidden = !on;
    const game = lobby && lobby.state && lobby.state.game;
    if (on && game) $("beltCost").textContent = money(game.beltCost);
  };
  let roadButtons = null;
  hud.roadTool = (level) => {
    const box = $("hudRoads");
    box.hidden = !level;
    $("roadTool").classList.toggle("on", !!level);
    const game = lobby && lobby.state && lobby.state.game;
    if (!level || !game || !game.roadLevels) return;
    if (!roadButtons) {
      roadButtons = game.roadLevels.slice(1).map((lv, k) => el("button", { onclick: () => SB.input.setRoad(k + 1),
        title: `Machines ×${lv.unit} speed, you ×${lv.walk}${k + 1 === 4 ? ". Never snowed over." : ""}` },
      el("kbd", {}, String(k + 1)), `${lv.name} ${money(lv.cost)}`));
      fill($("roadLevels"), roadButtons);
    }
    roadButtons.forEach((b, k) => b.classList.toggle("on", k + 1 === level));
  };
  hud.follow = () => lobby.sendGame({ action: "rally", follow: true });
  hud.anywhere = () => lobby.sendGame({ action: "rally" });
  hud.reset = () => { machineRows = null; upgradeKey = null; logCount = null; };

  function machineSub(game, d) {
    const goods = game.defs.goods;
    const name = (g) => (g === "snow" ? "snow" : `${goods[g].icon} ${goods[g].name}`);
    if (d.recipe) {
      const out = goods[d.recipe.out];
      return `${fmt(d.recipe.per)} ${name(d.recipe.in)} → ${out.icon} ${out.name} (${money(out.value)})`;
    }
    if (d.carry) return `Hauls ${fmt(d.carry)} snow per load`;
    return "";
  }

  function supplyQty(button, mine) {
    if (button.dataset.minutes) return Math.max(20, Math.ceil(mine.dieselUse * 60 * Number(button.dataset.minutes)));
    return Number(button.dataset.qty);
  }

  function renderMachines(game, mine, me) {
    const defs = game.defs.machines;
    const ids = Object.keys(defs).filter((id) => !defs[id].unique).sort((a, b) => defs[a].order - defs[b].order);
    if (!machineRows) {
      machineRows = {};
      fill($("machines"), ids.map((id) => {
        const d = defs[id];
        const sub = el("div", { className: "sub" });
        const buy1 = el("button", { className: "green", onclick: () => lobby.sendGame({ action: "buy", machine: id, count: 1 }) });
        const buy10 = d.placed ? el("span", { className: "muted small" }, "where you stand")
          : el("button", { onclick: () => lobby.sendGame({ action: "buy", machine: id, count: 10 }) });
        const row = el("div", { className: "sb-machine", title: `${d.text}\nAbout ${fmt(d.nominal)} snow/s each${d.diesel ? `, ${d.diesel} L diesel/s` : ""}` },
          el("span", { className: "icon" }, d.icon),
          el("div", {}, el("b", {}, d.name), el("div", { className: "sub" }, d.text),
            machineSub(game, d) ? el("div", { className: "sub" }, machineSub(game, d)) : null, sub), buy1, buy10);
        machineRows[id] = { row, sub, buy1, buy10 };
        return row;
      }));
    }
    let highest = -1;
    ids.forEach((id, k) => { if (mine.machines[id].owned) highest = k; });
    ids.forEach((id, k) => {
      const r = machineRows[id], m = mine.machines[id];
      r.row.hidden = k > highest + 2 && k > 1;
      r.sub.textContent = m.owned ? `Owned ${m.owned}${m.rate ? ` · ${fmt(m.rate)} snow/s` : ""}` : "";
      r.buy1.textContent = (defs[id].placed ? "Place " : "") + money(m.cost1);
      r.buy1.disabled = me.cash < m.cost1;
      if (!defs[id].placed) {
        r.buy10.textContent = `×10 ${money(m.cost10)}`;
        r.buy10.disabled = me.cash < m.cost10;
      }
    });
  }

  function renderUpgrades(game, mine, me) {
    const defs = game.defs.upgrades;
    const key = mine.upgrades.join(",");
    if (key !== upgradeKey) {
      upgradeKey = key;
      upgradeButtons = mine.upgrades.map((id) => {
        const u = defs[id];
        const b = el("button", { className: "sb-upgrade", title: u.text + (u.shared ? " (for the whole team)" : ""),
          onclick: () => lobby.sendGame({ action: "upgrade", upgrade: id }) },
        `${u.shared ? "🤝 " : ""}${u.name}`, el("small", {}, `${money(u.cost)} · ${u.text}`));
        b.dataset.cost = u.cost;
        return b;
      });
      const shared = Object.keys(game.shared).length;
      fill($("upgrades"), upgradeButtons.length ? upgradeButtons : el("span", { className: "muted" }, "Nothing new yet: earn more or buy machines."),
        el("div", { className: "muted", style: "width:100%" }, `Owned: ${mine.owned.length} yours, ${shared} shared`));
    }
    for (const b of upgradeButtons) b.disabled = me.cash < Number(b.dataset.cost);
  }

  function statusChip(p) {
    const text = { frostbite: "Frostbite", starving: "Starving", frenzy: "Frenzy x5" }[p.status];
    return text ? el("span", { className: `sb-status ${p.status}` }, text) : null;
  }

  function renderTeam(game, state) {
    if (panel !== "team") return;
    fill($("team"), Object.entries(game.players).map(([pid, p]) => {
      const units = Object.values(p.owned).reduce((a, b) => a + b, 0);
      return el("li", { title: "Click to follow (spectators)", onclick: () => { SB.view.spectate = pid; } },
        el("span", { className: "sb-dot", style: `background:${p.color}` }), el("b", {}, p.name + (pid === state.you ? " (you)" : "")),
        statusChip(p),
        el("div", { className: "muted" }, `${money(p.cash)} · ${fmt(p.rate)} snow/s · ${units} units · cleared ${fmt(p.cleared)}` +
          (p.goods ? ` · goods ${money(p.goods)}` : "")),
        el("div", { className: "muted" }, `🍲 ${p.food}  🌡️ ${p.warmth}`));
    }));
  }

  function hoverText(game, mine, [x, y]) {
    const snow = SB.grid.snowAt(x, y), workable = SB.grid.workable(x, y), road = SB.grid.road(x, y);
    const parts = [FEATURE_NAMES[SB.grid.feat(x, y)] || "Snow"];
    const at = (list) => Object.values(list || {}).some(([lx, ly]) => lx === x && ly === y);
    if (at(game.depots)) parts[0] = "🏪 Snow Depot: machines unload snow here";
    if (at(game.markets)) parts[0] = "🚉 Old Rail Station: snow drop point and goods market";
    for (const lm of Object.values(game.landmarks || {})) {
      if (x >= lm.x && y >= lm.y && x < lm.x + lm.size && y < lm.y + lm.size) {
        const d = game.defs.landmarks[lm.id];
        parts[0] = `${d.icon} ${d.name}` + (lm.found ? ` (found by ${game.players[lm.found] ? game.players[lm.found].name : "someone"})` : ` · ${lm.left} of ${lm.total} lots to clear`);
      }
    }
    const placed = mine && mine.units ? Object.values(mine.units).find((u) => u.f && Math.floor(u.x) === x && Math.floor(u.y) === y) : null;
    if (placed) {
      const d = game.defs.machines[placed.m], out = game.defs.goods[d.recipe.out];
      parts[0] = `${d.icon} ${d.name}: input ${Math.round(placed.f[0] * 100)}% · ${placed.f[1]} ${out.icon} waiting${placed.s === "full" ? " · FULL: put a conveyor beside it" : ""}`;
    }
    const belt = SB.input.beltAt(x, y);
    if (belt) parts.push(`${belt[3] === lobby.state.you ? "Your conveyor" : `${(game.players[belt[3]] || {}).name || "Someone"}'s conveyor`} ${"→↓←↑"[belt[0]]}` +
      (belt[2] ? ` · ${belt[2]} ${game.defs.goods[belt[1]].icon}` : " · empty"));
    if (road) parts.push(`${game.roadLevels[road].name} road`);
    if (snow) parts.push(`~${fmt(snow)} snow`);
    if (SB.input.belt) {
      parts.push(SB.input.myBelt(x, y) ? "click: turn it" : belt ? "not yours" : SB.input.canBelt(x, y) ? `click or drag: conveyor ${money(game.beltCost)}` : "can't lay a conveyor here");
    } else if (SB.input.demolish) {
      parts.push(demolishText(game, mine, x, y, at, placed || placedAt(mine, x, y), road));
    } else if (SB.input.road) {
      const lv = game.roadLevels[SB.input.road];
      parts.push(SB.input.canRoad(x, y) ? `click: ${lv.name} ${money(lv.cost - game.roadLevels[road].cost)}` : "can't lay road here");
    } else if (workable) parts.push(SB.input.inReach(x, y) ? "hold to shovel" : "walk closer to shovel");
    return parts.join(" · ");
  }

  function placedAt(mine, x, y) {
    return mine && mine.units ? Object.values(mine.units).find((u) => Math.floor(u.x) === x && Math.floor(u.y) === y &&
      lobby.state.game.defs.machines[u.m].placed) : null;
  }

  function demolishText(game, mine, x, y, at, placed, road) {
    // What a click would tear down (the server decides; this mirrors logic/demolish.py's order).
    const share = game.refunds.share;
    if (SB.grid.feat(x, y) === "X" || at(game.markets)) return "can't be torn down";
    if (placed) {
      const d = game.defs.machines[placed.m];
      if (d.unique) return "landmark building: can't be torn down";
      if (placed.p !== lobby.state.you) return `${(game.players[placed.p] || {}).name || "Someone"}'s ${d.name}`;
      return `click: tear down ${d.name} (+${money(mine.machines ? mine.machines[placed.m].refund : 0)})`;
    }
    if (at(game.depots)) return `click: tear down depot (+${money(game.refunds.depot)})`;
    if (at(game.huts)) return `click: tear down hut (+${money(game.refunds.hut)})`;
    const belt = SB.input.beltAt(x, y);
    if (belt && belt[3] !== lobby.state.you && game.players[belt[3]]) return `${game.players[belt[3]].name}'s conveyor`;
    if (belt) return `click or drag: remove conveyor (+${money(game.refunds.belt)}, its goods are lost)`;
    if (road) return `click or drag: remove road (+up to ${money(share * game.roadLevels[road].cost)})`;
    return "nothing to tear down";
  }

  hud.refresh = (state) => {
    if (!state || !state.game || state.phase === "lobby") return;
    const game = state.game, mine = state.private, me = game.players[state.you];
    const w = game.weather;
    const weather = $("weather");
    weather.className = `sb-weather ${w.kind}`;
    weather.textContent = w.kind === "clear" ? "☀️ Clear" : w.kind === "warning" ? `⚠️ Blizzard in ${w.left}s!` : `🌨️ Blizzard ${w.left}s`;
    const pct = (100 * game.progress.reached) / game.progress.total;
    $("progressFill").style.width = `${Math.min(100, (100 * pct) / game.progress.goal)}%`;
    const dusted = game.progress.dusted ? ` · ${fmt(game.progress.dusted)} snowed over` : "";
    $("progressText").textContent = `${pct.toFixed(1)}% cleared · goal ${game.progress.goal}%${dusted}`;
    $("clock").textContent = `${Math.floor(game.time / 60)}:${String(game.time % 60).padStart(2, "0")}`;

    $("result").hidden = !state.result;
    if (state.result) {
      fill($("resultBody"), el("h2", { style: "margin-top:0" }, state.result.reason),
        el("ul", {}, Object.entries(state.result.cleared || {}).sort((a, b) => b[1] - a[1]).map(([pid, snow]) =>
          el("li", {}, `${game.players[pid] ? game.players[pid].name : pid}: ${fmt(snow)} snow cleared`))));
    }

    const aim = SB.input.aim;
    if (aim && aim[0] >= 0 && aim[1] >= 0 && aim[0] < game.w && aim[1] < game.h) $("hover").textContent = hoverText(game, mine, aim);
    else $("hover").textContent = "";

    const now = performance.now();
    if (now - miniAt > 400) { miniAt = now; SB.view.drawMinimap($("minimap")); }
    if (game.logCount !== logCount) {
      logCount = game.logCount;
      const entries = Object.entries(game.log).sort((a, b) => Number(b[0]) - Number(a[0])).slice(0, 6);
      fill($("log"), entries.map(([, text]) => el("div", {}, text)));
    }
    renderTeam(game, state);

    const playing = !!(me && mine && mine.machines);
    for (const id of ["hudNeeds", "hudBar"]) $(id).hidden = !playing;
    if (!playing) {
      $("cash").textContent = "Spectating";
      $("rates").textContent = "Team (T): click a player to follow them";
      fill($("status"));
      return;
    }
    $("cash").textContent = money(me.cash);
    $("rates").textContent = `Machines ${fmt(me.rate)} snow/s · Shovel ${fmt(mine.click)}/swing`;
    const haul = [];
    if (mine.carried) haul.push(`🛒 ${fmt(mine.carried)} snow on the way`);
    if (mine.waiting) haul.push(`🏭 ${money(mine.waiting)} goods waiting`);
    if (mine.onBelts) haul.push(`➡️ ${money(mine.onBelts)} on conveyors`);
    $("haul").textContent = haul.join(" · ");
    const notes = [];
    if (me.status === "frostbite") notes.push("🥶 Frostbite! You can't shovel. Get to the cabin or a hut.");
    if (me.status === "starving") notes.push("🍽️ Starving: weak and slow. Buy rations!");
    if (mine.frenzy) notes.push(`⚡ Frenzy x5 for ${mine.frenzy}s`);
    if (mine.dieselUse > 0 && mine.diesel <= 0) notes.push("⛽ Out of diesel: your machines stopped.");
    if (!game.stove.lit) notes.push("🪵 The woodpile is empty: no heat anywhere!");
    fill($("status"), notes.map((n) => el("div", {}, n)));

    $("foodText").textContent = me.food;
    $("warmText").textContent = me.warmth;
    $("foodBar").style.width = `${me.food}%`;
    $("warmBar").style.width = `${me.warmth}%`;
    const dieselLeft = mine.dieselUse > 0 ? ` · ${Math.floor(mine.diesel / mine.dieselUse)}s` : "";
    $("rationsText").textContent = `🥫 Rations ${mine.rations}${mine.auto.includes("rations") ? " 🚚" : ""}`;
    $("dieselText").textContent = `⛽ ${fmt(mine.diesel)} L${dieselLeft}${mine.auto.includes("diesel") ? " 🚚" : ""}`;
    $("logsText").textContent = `🪵 ${fmt(game.woodpile)} logs · −${game.stove.burn}/min`;
    for (const button of document.querySelectorAll(".sb-supply button")) {
      const qty = supplyQty(button, mine);
      const cost = qty * game.prices[button.dataset.item];
      button.textContent = `+${fmt(qty)} ${money(cost)}`;
      button.disabled = me.cash < cost || (w.kind === "blizzard" && button.dataset.item !== "rations");
    }
    $("buildHut").innerHTML = "";
    $("buildHut").append(el("kbd", {}, "H"), `Hut ${money(game.hutCost)}`);
    $("buildHut").disabled = me.cash < game.hutCost;
    $("buildDepot").innerHTML = "";
    $("buildDepot").append(el("kbd", {}, "Q"), `Depot ${money(game.depotCost)}`);
    $("buildDepot").disabled = me.cash < game.depotCost;
    $("follow").classList.toggle("on", me.rally === "follow");
    $("anywhere").classList.toggle("on", me.rally === undefined);
    renderMachines(game, mine, me);
    renderUpgrades(game, mine, me);
  };

  hud.init = (lobbyRef) => {
    lobby = lobbyRef;
    $("tabMachines").addEventListener("click", () => hud.toggle("machines"));
    $("tabUpgrades").addEventListener("click", () => hud.toggle("upgrades"));
    $("tabTeam").addEventListener("click", () => hud.toggle("team"));
    $("buildHut").addEventListener("click", hud.buildHut);
    $("buildDepot").addEventListener("click", hud.buildDepot);
    $("roadTool").addEventListener("click", () => SB.input.setRoad(SB.input.road ? 0 : 1));
    $("demolishTool").addEventListener("click", () => SB.input.setDemolish(!SB.input.demolish));
    $("beltTool").addEventListener("click", () => SB.input.setBelt(!SB.input.belt));
    $("follow").addEventListener("click", hud.follow);
    $("anywhere").addEventListener("click", hud.anywhere);
    for (const button of document.querySelectorAll(".sb-supply button")) {
      button.addEventListener("click", () => {
        const mine = lobby.state && lobby.state.private;
        if (mine) lobby.sendGame({ action: "supply", item: button.dataset.item, qty: supplyQty(button, mine) });
      });
    }
    const mini = $("minimap");
    const miniLot = (ev) => {
      const game = lobby.state.game, rect = mini.getBoundingClientRect();
      const k = Math.max(game.w, game.h) / rect.width;
      return [Math.floor((ev.clientX - rect.left) * k), Math.floor((ev.clientY - rect.top) * k)];
    };
    mini.addEventListener("click", (ev) => {
      if (!lobby.state || !lobby.state.game || !lobby.me()?.player) return;
      const [x, y] = miniLot(ev);
      lobby.sendGame({ action: "rally", x, y });
    });
    mini.addEventListener("contextmenu", (ev) => { ev.preventDefault(); hud.anywhere(); });
  };
})();
