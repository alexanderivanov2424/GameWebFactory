/*
 * Metro Lanes HUD: the boxes over the canvas (refreshed on every state and 5 times a second).
 *   ML.hud.init(lobby)      once (tool buttons, pick buttons)
 *   ML.hud.refresh(state)   week clock, team trips, players and points, your stock, the weekly
 *                           pick dialog, the result
 *   ML.hud.refreshTools()   tool buttons only (after a tool change)
 *   ML.hud.reset()          new game
 */
(() => {
  const ML = (window.ML = window.ML || {});
  const { $, el, fill } = AppDom;
  const hud = (ML.hud = {});
  let lobby = null;
  let lastScores = "", lastPick = "", lastResult = "";
  const HINTS = {
    road: "Drag to draw roads · straight into water/mountains for a bridge/tunnel · right-drag to erase · O: owners",
    roundabout: "Click a junction to put a roundabout on it · right-click to take yours back",
    light: "Click a junction to put traffic lights on it · right-click to take yours back",
  };

  hud.init = (lobbyRef) => {
    lobby = lobbyRef;
    for (const button of document.querySelectorAll("#hudTools button[data-tool]")) {
      button.addEventListener("click", () => ML.input.setTool(button.dataset.tool));
    }
  };

  hud.reset = () => { lastScores = lastPick = lastResult = ""; };

  hud.refreshTools = () => {
    const state = lobby.state, game = state && state.game;
    const mine = game && game.players[state.you];
    for (const button of document.querySelectorAll("#hudTools button[data-tool]")) {
      button.classList.toggle("on", ML.input.tool === button.dataset.tool);
    }
    for (const span of document.querySelectorAll("#hudTools [data-item]")) {
      const text = mine ? String(mine.stock[span.dataset.item]) : "–";
      if (span.textContent !== text) span.textContent = text;
    }
    $("hudTools").hidden = !mine || state.phase !== "playing";
    const hint = mine && state.phase === "playing" ? HINTS[ML.input.tool] : "";
    if ($("hint").textContent !== hint) $("hint").textContent = hint;
  };

  function scores(state) {
    const game = state.game;
    const rows = Object.entries(game.players).sort((a, b) => b[1].points - a[1].points);
    const key = JSON.stringify(rows.map(([pid, p]) => [pid, p.points, p.gone, p.picked, p.name])) + !!game.pick;
    if (key === lastScores) return;
    lastScores = key;
    fill($("scores"), rows.map(([pid, p]) => el("li", { className: p.gone ? "gone" : "" },
      el("span", { className: "ml-dot", style: `background:${p.color}` }),
      el("span", {}, p.name + (pid === state.you ? " (you)" : "")),
      game.pick && !p.gone ? el("span", { className: "muted small" }, p.picked !== undefined ? "✓" : "…") : null,
      el("span", { className: "pts", title: `${p.trips} trips used their roads` }, String(p.points)))));
  }

  function pick(state) {
    const game = state.game, box = $("pick");
    const mine = game.players[state.you];
    box.hidden = !game.pick || state.phase !== "playing";
    if (box.hidden) { lastPick = ""; return; }
    const picked = mine ? mine.picked : undefined;
    const waiting = Object.values(game.players).filter((p) => !p.gone && p.picked === undefined).length;
    $("pickStatus").textContent = `${game.pick.left} s left · ` + (waiting ? `waiting for ${waiting} player${waiting === 1 ? "" : "s"}` : "everyone has picked");
    const key = `${game.week}:${picked}:${!!mine}`;
    if (key === lastPick) return;
    lastPick = key;
    $("pickTitle").textContent = `Week ${game.week}: +${game.rules.weekly} roads, and pick one`;
    fill($("offers"), game.pick.offers.map((offer, i) => {
      const button = el("button", { className: picked === i ? "chosen" : "", disabled: !mine || mine.gone || picked !== undefined },
        el("b", {}, offer.name), offer.text);
      button.addEventListener("click", () => lobby.sendGame({ action: "pick", option: i }));
      return button;
    }));
  }

  function result(state) {
    const box = $("result");
    box.hidden = state.phase !== "finished" || !state.result;
    if (box.hidden) { lastResult = ""; return; }
    const r = state.result;
    const key = JSON.stringify(r);
    if (key === lastResult) return;
    lastResult = key;
    const rows = Object.entries(r.points).sort((a, b) => b[1] - a[1]);
    fill($("resultBody"),
      el("h3", {}, r.reason),
      el("p", {}, `The city made ${r.trips} trips and lasted until week ${r.week}.`),
      el("ol", {}, rows.map(([pid, pts]) => el("li", {}, `${r.names[pid]}: ${pts} points`))));
  }

  hud.refresh = (state) => {
    const game = state.game;
    if (!game) return;
    $("week").textContent = `Week ${game.week}`;
    $("clockFill").style.width = `${Math.min(100, (100 * game.time) / game.weekLen)}%`;
    $("trips").textContent = `🚗 ${game.trips} trips`;
    $("paused").hidden = !game.pick;
    scores(state);
    pick(state);
    result(state);
    hud.refreshTools();
  };
})();
