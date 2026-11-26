/*
 * Metro Lanes controls: mouse tools -> game actions, keyboard shortcuts, and your cursor as
 * real-time input (the others see it).
 *   ML.input.init(lobby, showError)   once
 *   ML.input.tool                     "road" | "roundabout" | "light"; ML.input.setTool(name)
 *   ML.input.preview()                what view.js draws: {tile, ok, pending: [[a, b]]}
 *   ML.input.reset()                  new game
 * Road tool: drag to draw; the stroke steps tile by tile (8 directions) toward the mouse and sends
 * {"action": "road", a, b} per step. Stepping straight into water/a mountain sends one step that
 * builds a whole bridge/tunnel and continues from where it lands; stepping onto an existing one
 * skips over it. A diagonal step that's blocked tries the two straight steps instead. Into a
 * building: only through its driveway, and the stroke ends there.
 * Right-drag (any tool): erase your pieces under the mouse. Roundabout / Light: click a road
 * tile. Keys 1-3 pick tools, Esc cancels, O toggles owner stripes.
 * Local checks (area, buildings, stock) stop a stroke instead of sending moves the server refuses.
 */
(() => {
  const ML = (window.ML = window.ML || {});
  const { $ } = AppDom;
  const CURSOR_EVERY = 100;

  const input = (ML.input = { tool: "road" });
  let lobby, showError;
  let drag = null;           // {last: t, button: 0 | 2, erased: Set}
  let mouse = null;          // [x, y] tile floats
  let pending = [];          // [[a, b, time]] steps sent, drawn until the server's state has them
  let spent = 0, spentAt = 0;
  let cursorAt = 0, cursorTimer = null;

  const game = () => lobby.state && lobby.state.game;
  const me = () => { const g = game(); return g && g.players[lobby.state.you]; };
  const playing = () => lobby.state && lobby.state.phase === "playing" && lobby.me()?.player && me() && !me().gone;
  const typing = (ev) => { const t = ev.composedPath ? ev.composedPath()[0] : ev.target; return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable); };
  const tileAt = (p) => {
    const g = game();
    if (!p) return null;
    const x = Math.floor(p[0]), y = Math.floor(p[1]);
    return g && ML.city.onMap(x, y) ? ML.city.idx(x, y) : null;
  };
  const stock = (item) => (me() ? me().stock[item] : 0);
  const roadsLeft = () => stock("roads") - (performance.now() - spentAt < 600 ? spent : 0);

  input.setTool = (tool) => { input.tool = tool; drag = null; ML.hud && ML.hud.refreshTools(); };
  input.reset = () => { drag = null; pending = []; input.tool = "road"; };

  input.preview = () => {
    const now = performance.now();
    pending = pending.filter(([a, b, t]) => now - t < 800 && !ML.city.linked(a, b));
    const tile = tileAt(mouse);
    const out = { tile, pending };
    if ((input.tool === "roundabout" || input.tool === "light") && tile !== null) {
      const r = ML.city.road(tile);
      out.ok = !!r && r.k === "r" && !r.f;
    }
    return out;
  };

  function fail(message) {
    showError(message);
    drag = null;
  }

  function send(a, b, cost) {
    lobby.sendGame({ action: "road", a, b });
    pending.push([a, b, performance.now()]);
    if (performance.now() - spentAt > 600) spent = 0;
    spent += cost; spentAt = performance.now();
  }

  // One step of a road stroke from drag.last toward tile `to`. Returns false to stop for now.
  function stepToward(to) {
    const city = ML.city;
    const a = drag.last;
    const ra = city.road(a);
    if (ra && ra.k !== "r") return fail("Bridges and tunnels only connect at their ends.");
    if (!ra && !city.building(a) && city.terrain(a) !== ".") return fail("Start on land.");
    if (!ra && !city.building(a) && !city.inArea(a)) return fail("That's outside the city limits.");
    const [ax, ay] = city.xy(a), [tx, ty] = city.xy(to);
    const sx = Math.sign(tx - ax), sy = Math.sign(ty - ay);
    const candidates = [[sx, sy]];
    if (sx && sy) candidates.push(Math.abs(tx - ax) >= Math.abs(ty - ay) ? [sx, 0] : [0, sy], Math.abs(tx - ax) >= Math.abs(ty - ay) ? [0, sy] : [sx, 0]);
    const blocked = (b) => {
      const bld = city.building(b);
      return (bld && !(bld.node === b && bld.door === a)) || city.terrain(b) !== "." && !city.road(b);
    };
    let dir = candidates[0];
    if (candidates.length > 1 && blocked(city.idx(ax + sx, ay + sy))) dir = candidates.find(([dx, dy]) => !blocked(city.idx(ax + dx, ay + dy))) || dir;
    const b = city.idx(ax + dir[0], ay + dir[1]);

    // Leaving a building: only through its driveway.
    const from = city.building(a);
    if (from) {
      if (from.node !== a || from.door !== b) return fail("Connect buildings at their driveway.");
      if (!city.road(b)) { if (roadsLeft() < 1) return fail("You have no roads left."); send(a, b, 1); }
      drag.last = b;
      return true;
    }
    const into = city.building(b);
    if (into) {
      if (into.node !== b || into.door !== a) return fail("Connect buildings at their driveway.");
      if (!city.road(a)) { if (roadsLeft() < 1) return fail("You have no roads left."); send(a, b, 1); }
      drag = null; // the stroke ends at the building
      return false;
    }
    const road = city.road(b);
    if (road && road.k !== "r") {
      // Ride over an existing bridge/tunnel to the land past it.
      const end = city.spanEnd(a, b);
      if (end === null) return fail("That bridge leads nowhere.");
      drag.last = end;
      return true;
    }
    if (city.terrain(b) !== ".") {
      const span = city.span(a, b);
      if (span.error) return fail(span.error);
      const item = span.kind === "b" ? "bridges" : "tunnels";
      if (stock(item) < 1) return fail(`You need a ${span.kind === "b" ? "bridge" : "tunnel"} to cross there.`);
      for (const t of span.tiles) if (!city.inArea(t)) return fail("That's outside the city limits.");
      send(a, b, (city.road(a) ? 0 : 1) + (city.road(span.land) ? 0 : 1));
      drag.last = span.land;
      return true;
    }
    if (!city.inArea(b)) return fail("That's outside the city limits.");
    if (dir[0] && dir[1] && city.linked(city.idx(ax + dir[0], ay), city.idx(ax, ay + dir[1]))) return fail("Roads can't cross there. Make a junction instead.");
    const cost = (city.road(a) ? 0 : 1) + (road ? 0 : 1);
    if (cost > roadsLeft()) return fail("You have no roads left.");
    if (cost > 0 || !city.linked(a, b)) send(a, b, cost);
    drag.last = b;
    return true;
  }

  function strokeTo(to) {
    let guard = 0;
    while (drag && drag.last !== to && guard++ < 60) if (!stepToward(to)) break;
  }

  function eraseAt(t) {
    if (t === null || drag.erased.has(t)) return;
    const r = ML.city.road(t), you = lobby.state.you;
    if (!r || (r.o !== you && r.fo !== you)) return;
    drag.erased.add(t);
    lobby.sendGame({ action: "erase", t });
  }

  function sendCursor(force) {
    if (!playing()) return;
    const now = performance.now();
    if (!force && now - cursorAt < CURSOR_EVERY) {
      if (!cursorTimer) cursorTimer = setTimeout(() => { cursorTimer = null; sendCursor(true); }, CURSOR_EVERY);
      return;
    }
    cursorAt = now;
    lobby.sendInput({ cur: mouse ? [Math.round(mouse[0] * 10) / 10, Math.round(mouse[1] * 10) / 10] : null });
  }

  input.init = (lobbyRef, showErrorRef) => {
    lobby = lobbyRef; showError = showErrorRef;
    const canvas = $("map");
    canvas.addEventListener("contextmenu", (ev) => ev.preventDefault());
    canvas.addEventListener("mousemove", (ev) => {
      mouse = ML.view.toTile(ev.clientX, ev.clientY);
      sendCursor(false);
      if (!drag || !playing()) return;
      const t = tileAt(mouse);
      if (t === null) return;
      if (drag.button === 2) eraseAt(t);
      else strokeTo(t);
    });
    canvas.addEventListener("mouseleave", () => { mouse = null; sendCursor(true); });
    canvas.addEventListener("mousedown", (ev) => {
      mouse = ML.view.toTile(ev.clientX, ev.clientY);
      const t = tileAt(mouse);
      if (!playing() || t === null) return;
      if (ev.button === 2) {
        drag = { button: 2, erased: new Set() };
        eraseAt(t);
        return;
      }
      if (ev.button !== 0) return;
      const tool = input.tool;
      if (tool === "road") {
        drag = { button: 0, last: t };
      } else {
        const item = tool === "roundabout" ? "roundabouts" : "lights";
        if (stock(item) < 1) return showError(`You have no ${item} left.`);
        lobby.sendGame({ action: "place", t, item: tool });
      }
    });
    window.addEventListener("mouseup", () => { drag = null; });
    window.addEventListener("keydown", (ev) => {
      if (typing(ev) || $("game").hidden || ev.repeat) return;
      const tools = { Digit1: "road", Digit2: "roundabout", Digit3: "light" };
      if (tools[ev.code]) { input.setTool(tools[ev.code]); ev.preventDefault(); }
      else if (ev.code === "Escape") { input.setTool("road"); }
      else if (ev.code === "KeyO") { ML.view.owners = !ML.view.owners; }
    });
    window.addEventListener("blur", () => { drag = null; });
  };
})();
