/*
 * Snowbound controls: keyboard and mouse -> real-time input, actions and HUD shortcuts, plus
 * prediction of your own character so walking feels instant.
 *   SB.input.init(lobby)   once
 *   SB.input.frame(dt)     every animation frame (view.js): predicts your position, re-aims
 *   SB.input.me            {x, y} predicted position of your character (null if not playing)
 *   SB.input.aim           [x, y] lot under the mouse (or null); SB.input.inReach(x, y)
 *   SB.input.reset()       new game
 * Input sent ({keys, aim, dig}, see server.py): whenever keys or the dig button change, and when
 * the aimed lot changes (at most every AIM_EVERY ms, the last one always sent).
 * Prediction: you move locally with SB.grid.move and the same speed rules; the server's position
 * corrects it (snap when more than SNAP lots apart, drift toward it while standing still).
 * Keys: WASD/arrows walk; hold mouse or Space to shovel the lot under the mouse; Shift+click sets
 * your units' rally point; B machines, U upgrades, T team, H build a hut, F follow me, R units
 * work anywhere, Esc closes panels; wheel zooms.
 */
(() => {
  const SB = (window.SB = window.SB || {});
  const { $ } = AppDom;
  const KEYS = { KeyW: "up", ArrowUp: "up", KeyS: "down", ArrowDown: "down", KeyA: "left", ArrowLeft: "left", KeyD: "right", ArrowRight: "right" };
  const DIRS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
  const AIM_EVERY = 100;
  const SNAP = 1.5;

  const input = (SB.input = { me: null, aim: null });
  let lobby = null;
  const held = new Set();
  let mouseDig = false, spaceDig = false, mouse = null;
  let sent = { keys: "", aim: "", dig: false }, aimSentAt = 0, aimTimer = null;
  let stillFor = 0;

  const playing = () => lobby && lobby.state && lobby.state.phase === "playing" && lobby.me()?.player && lobby.state.game;
  // composedPath: the chat and settings live in shadow DOM, where ev.target is only their host element.
  const typing = (ev) => { const t = ev.composedPath ? ev.composedPath()[0] : ev.target; return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable); };

  function send(force) {
    if (!playing()) return;
    const keys = [...held].sort().join(","), aim = input.aim ? input.aim.join(",") : "", dig = mouseDig || spaceDig;
    const now = performance.now();
    if (keys === sent.keys && dig === sent.dig && aim === sent.aim) return;
    if (!force && keys === sent.keys && dig === sent.dig && now - aimSentAt < AIM_EVERY) {
      if (!aimTimer) aimTimer = setTimeout(() => { aimTimer = null; send(true); }, AIM_EVERY);
      return;
    }
    sent = { keys, aim, dig };
    aimSentAt = now;
    lobby.sendInput({ keys: [...held].sort(), aim: input.aim, dig });
  }

  input.inReach = (x, y) => {
    const me = input.me, rules = lobby.state.game.move;
    return !!me && Math.hypot(x + 0.5 - me.x, y + 0.5 - me.y) <= rules.reach;
  };

  input.reset = () => { input.me = null; held.clear(); mouseDig = spaceDig = false; sent = { keys: "", aim: "", dig: false }; };

  input.frame = (dt) => {
    const state = lobby.state;
    const game = state && state.game;
    const mine = game && game.players[state.you];
    if (!mine || state.phase !== "playing") { input.me = null; return; }
    if (!input.me) input.me = { x: mine.x, y: mine.y };
    const me = input.me, rules = game.move;
    let dx = 0, dy = 0;
    for (const k of held) { dx += DIRS[k][0]; dy += DIRS[k][1]; }
    if (dx || dy) {
      stillFor = 0;
      const len = Math.hypot(dx, dy), step = (SB.grid.speed({ ...mine, x: me.x, y: me.y }, rules) * Math.min(dt, 0.1)) / len;
      [me.x, me.y] = SB.grid.move(me.x, me.y, dx * step, dy * step, rules);
    } else stillFor += dt;
    const err = Math.hypot(mine.x - me.x, mine.y - me.y);
    if (err > SNAP) { me.x = mine.x; me.y = mine.y; }
    else if (stillFor > 0.3) { me.x += (mine.x - me.x) * 0.15; me.y += (mine.y - me.y) * 0.15; }
    if (mouse) {
      const lot = SB.view.toLot(mouse.x, mouse.y);
      const key = lot.join(",");
      if (!input.aim || key !== input.aim.join(",")) { input.aim = lot; send(false); }
    }
  };

  function swingAt(lot) {
    if (!lot || !playing() || !SB.grid.workable(lot[0], lot[1]) || !input.inReach(lot[0], lot[1])) return;
    lobby.sendGame({ action: "dig", x: lot[0], y: lot[1] });
    SB.view.puff(lot[0] + 0.5, lot[1] + 0.5, lobby.state.private ? lobby.state.private.click : 0);
  }

  input.init = (lobbyRef) => {
    lobby = lobbyRef;
    const canvas = $("map");
    canvas.addEventListener("contextmenu", (ev) => ev.preventDefault());
    canvas.addEventListener("mousemove", (ev) => { mouse = { x: ev.clientX, y: ev.clientY }; });
    canvas.addEventListener("mouseleave", () => { mouse = null; input.aim = null; mouseDig = false; send(true); });
    canvas.addEventListener("mousedown", (ev) => {
      mouse = { x: ev.clientX, y: ev.clientY };
      const lot = SB.view.toLot(ev.clientX, ev.clientY);
      input.aim = lot;
      if (ev.button !== 0 || !playing()) return;
      if (ev.shiftKey) { lobby.sendGame({ action: "rally", x: lot[0], y: lot[1] }); return; }
      swingAt(lot);
      mouseDig = true;
      send(true);
    });
    window.addEventListener("mouseup", (ev) => { if (ev.button === 0 && mouseDig) { mouseDig = false; send(true); } });
    canvas.addEventListener("wheel", (ev) => { ev.preventDefault(); SB.view.zoomBy(ev.deltaY < 0 ? 1.15 : 1 / 1.15); }, { passive: false });

    window.addEventListener("keydown", (ev) => {
      if (typing(ev) || $("game").hidden) return;
      if (KEYS[ev.code]) {
        ev.preventDefault();
        if (!held.has(KEYS[ev.code])) { held.add(KEYS[ev.code]); send(true); }
        return;
      }
      if (ev.repeat) return;
      if (ev.code === "Space") {
        ev.preventDefault();
        if (input.aim) swingAt(input.aim);
        spaceDig = true; send(true);
        return;
      }
      const hud = {
        KeyB: () => SB.hud.toggle("machines"), KeyU: () => SB.hud.toggle("upgrades"), KeyT: () => SB.hud.toggle("team"),
        Escape: () => SB.hud.toggle(null), KeyH: () => SB.hud.buildHut(), KeyF: () => SB.hud.follow(), KeyR: () => SB.hud.anywhere(),
      }[ev.code];
      if (hud) { ev.preventDefault(); hud(); }
    });
    window.addEventListener("keyup", (ev) => {
      if (KEYS[ev.code] && held.delete(KEYS[ev.code])) send(true);
      if (ev.code === "Space" && spaceDig) { spaceDig = false; send(true); }
    });
    window.addEventListener("blur", () => { held.clear(); mouseDig = spaceDig = false; send(true); });
  };
})();
