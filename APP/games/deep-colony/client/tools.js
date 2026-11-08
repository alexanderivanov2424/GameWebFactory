/*
 * Tools: current tool / building / priority, mouse on the canvas, hotkeys, and the messages they send.
 *   DC.tools.state {tool, building, prio}   tool: inspect|dig|cancel|deconstruct|priority|build
 *   DC.tools.setTool(name) / setBuilding(id) (also selects the build tool) / setPrio(n)
 *   DC.tools.onChange(fn)    called when the tool, building or priority changes
 *   DC.tools.preview()       what render.js draws for your own tool: {rect, color} | {cells, building} | null
 * DC.view {overlay, hover [x, y] | null, drag {x0, y0, x1, y1} | null} is shared with render/panels.
 * Input sent (only when it changes): lobby.sendInput({cursor, tool, drag?}). Spectators send nothing.
 */
(() => {
  const DC = (window.DC = window.DC || {});
  const AREA = ["dig", "cancel", "deconstruct", "priority"];
  const TOOL_COLORS = { dig: "#ffd54f", cancel: "#ffffff", deconstruct: "#ff5252", priority: "#4fc3f7", inspect: "#ffffff" };
  const state = { tool: "inspect", building: null, prio: 5 };
  const view = (DC.view = { overlay: "none", hover: null, last: null, drag: null });
  const listeners = [];
  let lastInput = "";

  const canvas = document.getElementById("map");
  const game = () => DC.lobby && DC.lobby.state && DC.lobby.state.game;
  const isPlayer = () => Boolean(DC.lobby && DC.lobby.me() && DC.lobby.me().player);
  const playing = () => DC.lobby && DC.lobby.state && DC.lobby.state.phase === "playing";
  const def = (id) => { const g = game(); return g && id ? g.defs.buildings[id] : null; };
  const notify = () => { listeners.forEach((fn) => fn()); sendInput(); };

  function sendInput() {
    if (!DC.lobby || !isPlayer() || !playing()) return;
    const msg = { tool: state.tool };
    if (view.hover) msg.cursor = view.hover.slice();
    if (view.drag) msg.drag = [view.drag.x0, view.drag.y0, view.drag.x1, view.drag.y1];
    const key = JSON.stringify(msg);
    if (key === lastInput) return;
    lastInput = key;
    DC.lobby.sendInput(msg);
  }

  function setTool(name) {
    state.tool = name;
    view.drag = null;
    notify();
  }
  function setBuilding(id) { state.building = id; state.tool = "build"; view.drag = null; notify(); }
  function setPrio(n) { state.prio = n; notify(); }

  // Cells of a 1x1 build drag: pipes/wires along an L path, others fill the rectangle.
  function dragCells(d, drag) {
    const { x0, y0, x1, y1 } = drag;
    const cells = [];
    if (d.layer === "pipe" || d.layer === "wire") {
      const sx = x1 >= x0 ? 1 : -1, sy = y1 >= y0 ? 1 : -1;
      for (let x = x0; x !== x1 + sx; x += sx) cells.push([x, y0]);
      for (let y = y0 + sy; y !== y1 + sy; y += sy) cells.push([x1, y]);
    } else {
      for (let y = Math.min(y0, y1); y <= Math.max(y0, y1); y++)
        for (let x = Math.min(x0, x1); x <= Math.max(x0, x1); x++) cells.push([x, y]);
    }
    return cells;
  }

  function preview() {
    const h = view.hover;
    if (state.tool === "build") {
      const d = def(state.building);
      if (!d) return null;
      if (view.drag && d.w === 1 && d.h === 1) return { cells: dragCells(d, view.drag), building: state.building };
      return h ? { cells: [h], building: state.building } : null;
    }
    if (AREA.includes(state.tool)) {
      const color = TOOL_COLORS[state.tool];
      if (view.drag) return { rect: [view.drag.x0, view.drag.y0, view.drag.x1, view.drag.y1], color };
      return h ? { rect: [h[0], h[1], h[0], h[1]], color } : null;
    }
    return null;
  }

  function cellAt(ev) {
    const g = DC.grid, r = canvas.getBoundingClientRect(), TILE = DC.render.tile();
    if (!g.w) return null;
    const x = Math.floor((ev.clientX - r.left) * (canvas.width / r.width) / TILE);
    const y = Math.floor((ev.clientY - r.top) * (canvas.height / r.height) / TILE);
    if (x < 0 || y < 0 || x >= g.w || y >= g.h) return null;
    return [x, y];
  }

  const send = (msg) => DC.lobby.sendGame(msg);

  function finishDrag() {
    const d = view.drag;
    view.drag = null;
    if (!d) return;
    if (AREA.includes(state.tool)) {
      const msg = { action: state.tool, rect: [d.x0, d.y0, d.x1, d.y1] };
      if (state.tool === "dig" || state.tool === "priority") msg.prio = state.prio;
      send(msg);
    } else if (state.tool === "build") {
      const bd = def(state.building);
      if (bd) send({ action: "build", building: state.building, cells: dragCells(bd, d), prio: state.prio });
    }
    notify();
  }

  canvas.addEventListener("mousemove", (ev) => {
    const c = cellAt(ev);
    const prev = view.hover;
    view.hover = c;
    if (view.drag && c) { view.drag.x1 = c[0]; view.drag.y1 = c[1]; }
    if (JSON.stringify(prev) !== JSON.stringify(c) || view.drag) sendInput();
  });
  canvas.addEventListener("mouseleave", () => {
    if (view.hover) view.last = view.hover; // the hover panel keeps showing it (so its buttons can be clicked)
    view.hover = null;
    sendInput();
  });
  canvas.addEventListener("contextmenu", (ev) => ev.preventDefault());
  canvas.addEventListener("mousedown", (ev) => {
    const c = cellAt(ev);
    if (ev.button === 2) {
      ev.preventDefault();
      if (view.drag) { view.drag = null; notify(); } else if (state.tool !== "inspect") setTool("inspect");
      return;
    }
    if (ev.button !== 0 || !c || !isPlayer() || !playing()) return;
    if (AREA.includes(state.tool)) {
      view.drag = { x0: c[0], y0: c[1], x1: c[0], y1: c[1] };
      sendInput();
    } else if (state.tool === "build") {
      const d = def(state.building);
      if (!d) return;
      if (d.w === 1 && d.h === 1) { view.drag = { x0: c[0], y0: c[1], x1: c[0], y1: c[1] }; sendInput(); }
      else send({ action: "build", building: state.building, cells: [c], prio: state.prio });
    }
  });
  window.addEventListener("mouseup", (ev) => { if (ev.button === 0) finishDrag(); });

  // Space on a focused button would also click it on key release (double pause toggle).
  document.addEventListener("keyup", (ev) => {
    if (ev.code === "Space" && ev.target && ev.target.tagName === "BUTTON" && playing()) ev.preventDefault();
  });
  const KEYS = { KeyG: "dig", KeyC: "cancel", KeyX: "deconstruct", KeyP: "priority", KeyI: "inspect" };
  document.addEventListener("keydown", (ev) => {
    const t = ev.target;
    if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
    if (ev.ctrlKey || ev.metaKey || ev.altKey || !playing()) return;
    if (ev.code === "Escape") {
      if (view.drag) { view.drag = null; notify(); } else setTool("inspect");
      return;
    }
    if (!isPlayer()) return;
    const g = game();
    if (ev.code === "Space") {
      ev.preventDefault();
      if (g) send({ action: "pause", paused: !g.clock.paused });
    } else if (ev.code === "Digit1" || ev.code === "Digit2" || ev.code === "Digit3") {
      send({ action: "speed", speed: Number(ev.code.slice(5)) });
    } else if (KEYS[ev.code]) setTool(KEYS[ev.code]);
  });

  DC.tools = { state, setTool, setBuilding, setPrio, preview, send, onChange: (fn) => listeners.push(fn),
    resetInput: () => { lastInput = ""; }, sendInput, TOOL_COLORS };
})();
