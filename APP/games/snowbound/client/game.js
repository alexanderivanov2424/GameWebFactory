/*
 * Snowbound page wiring: lobby, and the side panels (cash, survival and supplies, machines,
 * upgrades, team, log) refreshed ~4 times a second from lobby.state while playing. Buttons are
 * built once and updated in place (machines, supplies) or rebuilt only when the list changes
 * (upgrades), so a click never lands on a button that was just replaced. The map is map.js.
 *   SB.fmt(n)   short number: 950, 1.2k, 3.4M, 5.6B, 7.8T
 */
(() => {
  const SB = (window.SB = window.SB || {});
  const { $, el, fill } = AppDom;
  let state = null;
  let lastGameNumber = null;

  SB.fmt = (n) => {
    if (!isFinite(n)) return "0";
    const a = Math.abs(n);
    if (a < 10) return String(Math.round(n * 10) / 10);
    if (a < 1000) return String(Math.round(n));
    const units = [["T", 1e12], ["B", 1e9], ["M", 1e6], ["k", 1e3]];
    for (const [u, v] of units) if (a >= v) return (n / v).toFixed(a / v >= 100 ? 0 : a / v >= 10 ? 1 : 2) + u;
    return String(Math.round(n));
  };
  const fmt = SB.fmt;
  const money = (n) => "$" + fmt(n);

  const lobby = AppLobby.connect("snowbound", {
    onState(newState) { state = newState; render(); },
    onSnapshot(newState) { state = newState; },
    onError: (message) => showError(message),
    onConnection(status) { $("connection").textContent = AppLobbyUI.connectionText(status, lobby.roomId); },
  });
  const showError = AppLobbyUI.errorBox($("error"));
  const rt = AppRealtime.attach(lobby);
  const renderButtons = AppLobbyUI.lobbyButtons(lobby, { join: $("join"), leave: $("leave"), ready: $("ready"), back: $("back") });
  const renderSettings = AppLobbyUI.settingsForm($("settings"), lobby);
  SB.map.init(lobby, rt);

  $("home").addEventListener("click", () => SB.map.center());
  $("flakeGo").addEventListener("click", () => {
    const f = state && state.game && state.game.flake;
    if (f) SB.map.center([f.x + 0.5, f.y + 0.5]);
  });
  $("clearFocus").addEventListener("click", () => lobby.sendGame({ action: "focus" }));
  for (const button of document.querySelectorAll(".sb-supply button")) {
    button.addEventListener("click", () => {
      const qty = supplyQty(button);
      if (qty > 0) lobby.sendGame({ action: "supply", item: button.dataset.item, qty });
    });
  }

  function render() {
    const inLobby = state.phase === "lobby";
    $("lobby").hidden = !inLobby;
    $("game").hidden = inLobby;
    renderButtons();
    if (inLobby) {
      AppLobbyUI.renderPlayers($("players"), lobby, {});
      AppLobbyUI.renderStart($("start"), lobby);
      AppLobbyUI.renderSpectators($("spectators"), state);
      renderSettings();
      return;
    }
    if (state.gameNumber !== lastGameNumber) {
      lastGameNumber = state.gameNumber;
      machineRows = null;
      upgradeKey = null;
      SB.map.reset();
    }
    refresh();
  }

  // --- panels -------------------------------------------------------------------------

  function supplyQty(button) {
    const mine = state && state.private;
    if (!mine) return 0;
    if (button.dataset.minutes) {
      return Math.max(20, Math.ceil(mine.dieselUse * 60 * Number(button.dataset.minutes)));
    }
    return Number(button.dataset.qty);
  }

  let machineRows = null;
  function renderMachines(game, mine, me) {
    const defs = game.defs.machines;
    const ids = Object.keys(defs).sort((a, b) => defs[a].order - defs[b].order);
    if (!machineRows) {
      machineRows = {};
      fill($("machines"), ids.map((id) => {
        const d = defs[id];
        const sub = el("div", { className: "sub" });
        const buy1 = el("button", { className: "green", onclick: () => lobby.sendGame({ action: "buy", machine: id, count: 1 }) });
        const buy10 = el("button", { onclick: () => lobby.sendGame({ action: "buy", machine: id, count: 10 }) });
        const row = el("div", { className: "sb-machine", title: `${d.text}\n${d.rate} snow/s each${d.diesel ? `, ${d.diesel} L diesel/s each` : ", no diesel"}` },
          el("span", { className: "icon" }, d.icon), el("div", {}, el("b", {}, d.name), sub), buy1, buy10);
        machineRows[id] = { row, sub, buy1, buy10 };
        return row;
      }));
    }
    let highest = -1;
    ids.forEach((id, k) => { if (mine.machines[id].owned) highest = k; });
    ids.forEach((id, k) => {
      const r = machineRows[id], m = mine.machines[id];
      r.row.hidden = k > highest + 2 && k > 1;
      r.sub.textContent = `Owned ${m.owned}${m.owned ? ` · ${fmt(m.rate)} snow/s` : ""}`;
      r.buy1.textContent = `Buy ${money(m.cost1)}`;
      r.buy10.textContent = `×10 ${money(m.cost10)}`;
      r.buy1.disabled = me.cash < m.cost1;
      r.buy10.disabled = me.cash < m.cost10;
    });
  }

  let upgradeKey = null, upgradeButtons = [];
  function renderUpgrades(game, mine, me) {
    const defs = game.defs.upgrades;
    const key = mine.upgrades.join(",");
    if (key !== upgradeKey) {
      upgradeKey = key;
      upgradeButtons = mine.upgrades.map((id) => {
        const u = defs[id];
        const b = el("button", { className: "sb-upgrade", title: u.text + (u.shared ? " (shared with the team)" : ""),
          onclick: () => lobby.sendGame({ action: "upgrade", upgrade: id }) },
        `${u.shared ? "🤝 " : ""}${u.name}`, el("small", {}, money(u.cost)));
        b.dataset.cost = u.cost;
        return b;
      });
      const owned = mine.owned.length + Object.keys(game.shared).length;
      fill($("upgrades"), upgradeButtons.length ? upgradeButtons : el("span", { className: "muted small" }, "Nothing new yet: earn more or buy machines."),
        owned ? el("div", { className: "muted small", style: "width:100%" }, `${owned} owned (${mine.owned.length} yours, ${Object.keys(game.shared).length} shared)`) : null);
    }
    for (const b of upgradeButtons) b.disabled = me.cash < Number(b.dataset.cost);
  }

  function bar(id, value) { $(id).style.width = `${Math.max(0, Math.min(100, value))}%`; }

  function statusChip(p) {
    const text = { frostbite: "Frostbite", starving: "Starving", frenzy: "Frenzy x5" }[p.status];
    return text ? el("span", { className: `sb-status ${p.status}` }, text) : null;
  }

  let logCount = null;
  function refresh() {
    if (!state || !state.game || state.phase === "lobby") return;
    const game = state.game, mine = state.private, me = game.players[state.you];

    const w = game.weather;
    const weather = $("weather");
    weather.className = `sb-weather ${w.kind}`;
    weather.textContent = w.kind === "clear" ? "☀️ Clear skies" : w.kind === "warning" ? `⚠️ Blizzard in ${w.left}s!` : `🌨️ Blizzard! ${w.left}s left`;
    const pct = (100 * game.progress.reached) / game.progress.total;
    $("progressFill").style.width = `${Math.min(100, (100 * pct) / game.progress.goal)}%`;
    const dusted = game.progress.dusted ? ` · ${fmt(game.progress.dusted)} lots snowed on again` : "";
    $("progressText").textContent = `${pct.toFixed(1)}% of the valley cleared (goal ${game.progress.goal}%)${dusted}`;
    $("flakeGo").hidden = !game.flake || !mine;
    $("clock").textContent = `${Math.floor(game.time / 60)}:${String(game.time % 60).padStart(2, "0")}`;

    const result = $("result");
    result.hidden = !state.result;
    if (state.result) {
      fill(result, el("h2", { style: "margin-top:0" }, state.result.reason),
        el("ul", {}, Object.entries(state.result.cleared || {}).sort((a, b) => b[1] - a[1]).map(([pid, snow]) =>
          el("li", {}, `${game.players[pid] ? game.players[pid].name : pid}: ${fmt(snow)} snow cleared`))));
    }

    if (!me || !mine) {
      $("cash").textContent = "Spectating";
      $("rates").textContent = "";
    } else {
      $("cash").textContent = money(me.cash);
      $("rates").textContent = `Machines ${fmt(me.rate)} snow/s · Click ${fmt(mine.click)} snow`;
      const notes = [];
      if (me.status === "frostbite") notes.push("🥶 Frostbite: you can't shovel and your machines run at half speed. Get the stove going!");
      if (me.status === "starving") notes.push("🍽️ Starving: your clicks are weak and you get colder. Buy rations!");
      if (mine.frenzy) notes.push(`⚡ Frenzy: x5 for ${mine.frenzy}s`);
      if (mine.dieselUse > 0 && mine.diesel <= 0) notes.push("⛽ Out of diesel: your machines stopped.");
      fill($("status"), notes.map((n) => el("div", {}, n)));
      $("foodText").textContent = `${me.food}`;
      $("warmText").textContent = `${me.warmth}${game.stove.lit ? " (stove lit)" : " (stove out!)"}`;
      bar("foodBar", me.food);
      bar("warmBar", me.warmth);
      const dieselLeft = mine.dieselUse > 0 ? ` · ${Math.floor(mine.diesel / mine.dieselUse)}s` : "";
      $("rationsText").textContent = `🥫 Rations ${mine.rations}${mine.auto.includes("rations") ? " (delivered)" : ""}`;
      $("dieselText").textContent = `⛽ Diesel ${fmt(mine.diesel)} L${dieselLeft}${mine.auto.includes("diesel") ? " (delivered)" : ""}`;
      $("logsText").textContent = `🪵 Woodpile ${fmt(game.woodpile)} (team) · burns ${game.stove.burn}/min`;
      for (const button of document.querySelectorAll(".sb-supply button")) {
        const qty = supplyQty(button);
        const cost = qty * game.prices[button.dataset.item];
        button.textContent = `+${fmt(qty)} ${money(cost)}`;
        button.disabled = me.cash < cost || (w.kind === "blizzard" && button.dataset.item !== "rations");
      }
      renderMachines(game, mine, me);
      renderUpgrades(game, mine, me);
    }

    fill($("team"), Object.entries(game.players).map(([pid, p]) =>
      el("li", {}, el("span", { className: "sb-dot", style: `background:${p.color}` }), el("b", {}, p.name),
        ` ${money(p.cash)} · ${fmt(p.rate)}/s · cleared ${fmt(p.cleared)} · 🍲${p.food} 🌡️${p.warmth}`, statusChip(p))));

    if (game.logCount !== logCount) {
      logCount = game.logCount;
      const entries = Object.entries(game.log).sort((a, b) => Number(b[0]) - Number(a[0]));
      fill($("log"), entries.map(([, text]) => el("div", {}, text)));
    }
  }

  setInterval(() => { if (state && state.phase !== "lobby") refresh(); }, 250);
})();
