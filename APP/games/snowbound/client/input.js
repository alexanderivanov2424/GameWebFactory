/*
 * Snowbound controls: keyboard and mouse -> real-time input, actions and HUD shortcuts, plus
 * prediction of your own character so walking feels instant.
 *   SB.input.init(lobby)   once
 *   SB.input.frame(dt)     every animation frame (view.js): predicts your position, re-aims
 *   SB.input.me            {x, y} predicted position of your character (null if not playing)
 *   SB.input.aim           [x, y] lot under the mouse (or null); SB.input.inReach(x, y)
 *   SB.input.reset()       new game
 *   SB.input.road          road tool level 1-4 (0 = off); SB.input.setRoad(level) (0 turns it off)
 *   SB.input.demolish      demolish tool on; SB.input.setDemolish(on)
 *   SB.input.belt          conveyor tool on; SB.input.setBelt(on); SB.input.beltDir (0-3: right, down, left, up)
 *   SB.input.beltAt(x, y)  the conveyor on a lot ([dir, good, count, owner pid]) or undefined; SB.input.myBelt(x, y)
 *   (one build tool at a time: picking one turns the others off)
 *   SB.input.canRoad(x, y) can the selected road level be laid on that lot (cleared, not the cabin, not that good yet)
 * Input sent ({keys, aim, dig}, see server.py): whenever keys or the dig button change, and when
 * the aimed lot changes (at most every AIM_EVERY ms, the last one always sent).
 * Prediction: you move locally with SB.grid.move and the same speed rules; the server's position
 * corrects it (snap when more than SNAP lots apart, drift toward it while standing still).
 * Keys: WASD/arrows walk; hold mouse or Space to shovel the lot under the mouse; Shift+click sets
 * your units' rally point; B machines, U upgrades, T team, H build a hut, Q build a Snow Depot,
 * G road tool (1-4 pick the level; click or drag to lay road, sent in batches every ROAD_EVERY ms),
 * C conveyor tool (drag to lay belts pointing the way you drag; click a belt to turn it),
 * X demolish tool (click tears down what's on a lot; dragging on from there only takes belts and roads),
 * F follow me, R units work anywhere, Esc closes panels and the road tool; wheel zooms.
 */
(() => {
  const SB = (window.SB = window.SB || {});
  const { $ } = AppDom;
  const KEYS = { KeyW: "up", ArrowUp: "up", KeyS: "down", ArrowDown: "down", KeyA: "left", ArrowLeft: "left", KeyD: "right", ArrowRight: "right" };
  const DIRS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
  const AIM_EVERY = 100;
  const ROAD_EVERY = 120;
  const SNAP = 1.5;

  const input = (SB.input = { me: null, aim: null, road: 0, belt: false, demolish: false, beltDir: 0 });
  let lobby = null;
  const held = new Set();
  let mouseDig = false, spaceDig = false, mouse = null;
  let sent = { keys: "", aim: "", dig: false }, aimSentAt = 0, aimTimer = null;
  let stillFor = 0;
  let drag = null, queue = [], queueTimer = null, lastRoadLevel = 1;

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
    const me = input.me, mine = lobby.state.private;
    const reach = (mine && mine.reach) || lobby.state.game.move.reach;
    return !!me && Math.hypot(x + 0.5 - me.x, y + 0.5 - me.y) <= reach;
  };

  input.reset = () => { input.me = null; held.clear(); mouseDig = spaceDig = false; sent = { keys: "", aim: "", dig: false }; setTool(null); };

  // One build tool at a time: "road" (with a level), "belt", "demolish" or null.
  function setTool(tool, level) {
    input.road = tool === "road" ? level : 0;
    if (input.road) lastRoadLevel = input.road;
    input.belt = tool === "belt";
    input.demolish = tool === "demolish";
    drag = null;
    if (SB.hud) { SB.hud.roadTool(input.road); SB.hud.beltTool(input.belt); SB.hud.demolishTool(input.demolish); }
  }
  input.setRoad = (level) => setTool(level ? "road" : null, level);
  input.setBelt = (on) => setTool(on ? "belt" : null);
  input.setDemolish = (on) => setTool(on ? "demolish" : null);

  input.canRoad = (x, y) => SB.grid.reached(x, y) && SB.grid.feat(x, y) !== "X" && SB.grid.road(x, y) < input.road;
  input.beltAt = (x, y) => { const game = lobby.state && lobby.state.game, w = game ? game.w : 0; return game && game.belts && x >= 0 && y >= 0 && x < w ? game.belts[String(y * w + x)] : undefined; };
  input.myBelt = (x, y) => { const b = input.beltAt(x, y); return b && b[3] === lobby.state.you ? b : undefined; };
  input.canBelt = (x, y) => SB.grid.reached(x, y) && !["X", "S"].includes(SB.grid.feat(x, y)) && !input.beltAt(x, y);

  function flush() {
    queueTimer = null;
    if (!queue.length || !playing() || !(input.road || input.belt || input.demolish)) { queue = []; return; }
    const lots = queue.splice(0, 200);
    if (input.demolish) lobby.sendGame({ action: "demolish", lines: true, lots });
    else if (input.belt) lobby.sendGame({ action: "belt", lots });
    else lobby.sendGame({ action: "road", level: input.road, lots });
    if (queue.length) queueTimer = setTimeout(flush, ROAD_EVERY);
  }

  function steps(from, to) {
    // 4-connected lots from `from` (excluded) to `to`, so roads and belts never touch only at a corner.
    const out = [], at = [...from];
    while (at[0] !== to[0] || at[1] !== to[1]) {
      const dx = to[0] - at[0], dy = to[1] - at[1];
      if (Math.abs(dx) >= Math.abs(dy)) at[0] += Math.sign(dx); else at[1] += Math.sign(dy);
      out.push([...at]);
    }
    return out;
  }

  function dragTo(lot) {
    const lots = drag.last ? steps(drag.last, lot) : [lot];
    for (const [x, y] of lots) {
      const key = x + "," + y, prev = drag.last;
      if (input.belt) {
        // Each belt points at the next one dragged: turn the previous one (free) and lay this one the same way.
        if (prev) {
          const dir = [[1, 0], [0, 1], [-1, 0], [0, -1]].findIndex(([dx, dy]) => dx === x - prev[0] && dy === y - prev[1]);
          if (dir >= 0) { input.beltDir = dir; if (drag.laid.has(prev.join(","))) queue.push([prev[0], prev[1], dir]); }
        }
        drag.last = [x, y];
        if (drag.seen.has(key) || !(input.canBelt(x, y) || input.myBelt(x, y))) continue;
        drag.seen.add(key);
        drag.laid.add(key);
        queue.push([x, y, input.beltDir]);
        continue;
      }
      drag.last = [x, y];
      const ok = input.demolish ? SB.grid.road(x, y) > 0 || input.myBelt(x, y) : input.canRoad(x, y);
      if (drag.seen.has(key) || !ok) continue;
      drag.seen.add(key);
      queue.push([x, y]);
    }
    if (queue.length && !queueTimer) queueTimer = setTimeout(flush, ROAD_EVERY);
  }

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
      const wade = state.private && state.private.wade !== undefined ? state.private.wade : rules.wade;
      [me.x, me.y] = SB.grid.move(me.x, me.y, dx * step, dy * step, rules, wade);
    } else stillFor += dt;
    const err = Math.hypot(mine.x - me.x, mine.y - me.y);
    if (err > SNAP) { me.x = mine.x; me.y = mine.y; }
    else if (stillFor > 0.3) { me.x += (mine.x - me.x) * 0.15; me.y += (mine.y - me.y) * 0.15; }
    if (mouse) {
      const lot = SB.view.toLot(mouse.x, mouse.y);
      const key = lot.join(",");
      if (!input.aim || key !== input.aim.join(",")) { input.aim = lot; send(false); if (drag) dragTo(lot); }
    }
  };

  function swingAt(lot) {
    if (!lot || !playing() || !SB.grid.workable(lot[0], lot[1]) || !input.inReach(lot[0], lot[1])) return;
    lobby.sendGame({ action: "dig", x: lot[0], y: lot[1] });
    const mine = lobby.state.private;
    SB.view.puff(lot[0] + 0.5, lot[1] + 0.5, mine ? mine.click : 0);
    if (mine && mine.splash) {
      for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) SB.view.puff(lot[0] + dx + 0.5, lot[1] + dy + 0.5, 0);
    }
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
      if (input.road) { drag = { seen: new Set(), last: null }; dragTo(lot); return; }
      if (input.belt) {
        const here = input.myBelt(lot[0], lot[1]);
        if (here) {  // clicking your conveyor turns it clockwise; dragging on from it lays more
          input.beltDir = (here[0] + 1) % 4;
          lobby.sendGame({ action: "belt", lots: [[lot[0], lot[1], input.beltDir]] });
          drag = { seen: new Set([lot.join(",")]), laid: new Set([lot.join(",")]), last: lot };
          return;
        }
        drag = { seen: new Set(), laid: new Set(), last: null };
        dragTo(lot);
        return;
      }
      if (input.demolish) {
        lobby.sendGame({ action: "demolish", lots: [lot] });
        drag = { seen: new Set([lot.join(",")]), last: lot };
        return;
      }
      swingAt(lot);
      mouseDig = true;
      send(true);
    });
    window.addEventListener("mouseup", (ev) => {
      if (ev.button !== 0) return;
      if (drag) { drag = null; if (queueTimer) { clearTimeout(queueTimer); flush(); } }
      if (mouseDig) { mouseDig = false; send(true); }
    });
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
      const digit = { Digit1: 1, Digit2: 2, Digit3: 3, Digit4: 4 }[ev.code];
      if (digit && input.road) { ev.preventDefault(); input.setRoad(digit); return; }
      const hud = {
        KeyB: () => SB.hud.toggle("machines"), KeyU: () => SB.hud.toggle("upgrades"), KeyT: () => SB.hud.toggle("team"),
        Escape: () => { SB.hud.toggle(null); setTool(null); },
        KeyX: () => input.setDemolish(!input.demolish), KeyC: () => input.setBelt(!input.belt), KeyH: () => SB.hud.buildHut(), KeyQ: () => SB.hud.buildDepot(),
        KeyG: () => input.setRoad(input.road ? 0 : lastRoadLevel), KeyF: () => SB.hud.follow(), KeyR: () => SB.hud.anywhere(),
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
