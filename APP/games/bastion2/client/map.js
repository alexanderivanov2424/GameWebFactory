/*
 * Bastion 2: Bastion2Map, the floating grid in the middle of the screen. The world is unbounded;
 * the server sends `bounds` (the box around every structure plus a margin) and only that area is
 * drawn as ground (the rest is the page's empty background). The camera pans by dragging and zooms
 * with the wheel, and is clamped so the point at the centre of the free view (`focus()`) never
 * leaves the ground. No rules here: everything comes from the state.
 *
 *   const map = Bastion2Map.create(viewport, world, {
 *     focus() -> {x, y}            screen point the view centres on (the gap between HUD panels)
 *     onHover(x, y, event)         tile under the mouse (x, y null when off the map or dragging)
 *     onClick(x, y, event)         a click (not a drag) on a tile
 *     onRightClick(x, y, event)    right-click on a tile
 *   })
 *   map.build(game, you)          ground + structures from the state (owner colours, pending
 *                                 builds dashed, yours with a ↶ tag)
 *   map.setSpots(keys)            ["x,y"] tiles that pulse slowly (where you may place now)
 *   map.setGhost(x, y, icon)      the hovered placement preview (x null: hide)
 *   map.setHover(x, y)            outline the hovered tile (x null: hide)
 *   map.centerOn(x, y)            put that tile at the focus point
 *   map.tileRect(x, y)            the tile's viewport rectangle (for tips)
 */
const Bastion2Map = (() => {
  const { el } = AppDom;
  const TILE = 56;
  const ZOOM = [0.4, 2];

  function create(viewport, world, handlers) {
    world.style.setProperty("--tile", `${TILE}px`);
    const ground = el("div", { className: "ground" });
    const buildings = el("div");
    const spots = el("div");
    const hover = el("div", { className: "tile hover", hidden: true });
    const ghost = el("div", { className: "tile ghost", hidden: true });
    world.replaceChildren(ground, spots, buildings, hover, ghost);

    let cam = { tx: 0, ty: 0, z: 1 };
    let bounds = [-7, -5, 7, 5];
    let spotKey = "";
    let drag = null;
    let lastTile = null;

    const place = (node, x, y) => {
      node.style.left = `${x * TILE}px`;
      node.style.top = `${y * TILE}px`;
    };

    function apply() {
      const f = handlers.focus();
      const [x0, y0, x1, y1] = bounds;
      const wx = Math.min(Math.max((f.x - cam.tx) / cam.z, x0 * TILE), (x1 + 1) * TILE);
      const wy = Math.min(Math.max((f.y - cam.ty) / cam.z, y0 * TILE), (y1 + 1) * TILE);
      cam.tx = f.x - wx * cam.z;
      cam.ty = f.y - wy * cam.z;
      world.style.transform = `translate(${cam.tx}px, ${cam.ty}px) scale(${cam.z})`;
    }

    function tileAt(event) {
      const r = viewport.getBoundingClientRect();
      const x = Math.floor((event.clientX - r.left - cam.tx) / cam.z / TILE);
      const y = Math.floor((event.clientY - r.top - cam.ty) / cam.z / TILE);
      const [x0, y0, x1, y1] = bounds;
      return x >= x0 && x <= x1 && y >= y0 && y <= y1 ? [x, y] : null;
    }

    function reportHover(event) {
      const t = drag && drag.moved ? null : tileAt(event);
      const key = t ? `${t[0]},${t[1]}` : "";
      if (key === lastTile) return;
      lastTile = key;
      handlers.onHover(t ? t[0] : null, t ? t[1] : null, event);
    }

    viewport.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      drag = { x: e.clientX, y: e.clientY, tx: cam.tx, ty: cam.ty, moved: false };
    });
    window.addEventListener("mousemove", (e) => {
      if (drag) {
        const dx = e.clientX - drag.x;
        const dy = e.clientY - drag.y;
        if (!drag.moved && Math.hypot(dx, dy) > 5) {
          drag.moved = true;
          viewport.classList.add("dragging");
          reportHover(e);
        }
        if (drag.moved) {
          cam.tx = drag.tx + dx;
          cam.ty = drag.ty + dy;
          apply();
          return;
        }
      }
      if (viewport.contains(e.target)) reportHover(e);
    });
    window.addEventListener("mouseup", (e) => {
      if (!drag) return;
      const wasDrag = drag.moved;
      drag = null;
      viewport.classList.remove("dragging");
      if (!wasDrag && viewport.contains(e.target)) {
        const t = tileAt(e);
        if (t) handlers.onClick(t[0], t[1], e);
      }
      lastTile = null;
      if (viewport.contains(e.target)) reportHover(e);
    });
    viewport.addEventListener("mouseleave", () => {
      if (drag && drag.moved) return;
      lastTile = null;
      handlers.onHover(null, null, null);
    });
    viewport.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      const t = tileAt(e);
      if (t) handlers.onRightClick(t[0], t[1], e);
    });
    viewport.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = viewport.getBoundingClientRect();
      const mx = e.clientX - r.left;
      const my = e.clientY - r.top;
      const z = Math.min(Math.max(cam.z * (e.deltaY < 0 ? 1.12 : 1 / 1.12), ZOOM[0]), ZOOM[1]);
      cam.tx = mx - ((mx - cam.tx) / cam.z) * z;
      cam.ty = my - ((my - cam.ty) / cam.z) * z;
      cam.z = z;
      apply();
    }, { passive: false });
    window.addEventListener("resize", apply);

    function build(game, you) {
      bounds = game.bounds;
      const [x0, y0, x1, y1] = bounds;
      place(ground, x0, y0);
      ground.style.width = `${(x1 - x0 + 1) * TILE}px`;
      ground.style.height = `${(y1 - y0 + 1) * TILE}px`;
      const nodes = [];
      for (const [key, s] of Object.entries(game.structures)) {
        const [x, y] = key.split(",").map(Number);
        const card = game.cards[s.kind] || {};
        const mine = s.owner === you && s.pending;
        const node = el("div", { className: `tile bld${s.pending ? " pending" : ""}${mine ? " mine-pending" : ""}` });
        node.style.borderColor = game.colors[s.owner] || "#888";
        node.append(el("span", { className: "ico", textContent: card.icon || "🏠" }));
        if (mine) node.append(el("span", { className: "tag", textContent: "↶", title: "Right-click to take back" }));
        place(node, x, y);
        nodes.push(node);
      }
      buildings.replaceChildren(...nodes);
      apply();
    }

    function setSpots(keys) {
      const key = keys.join(" ");
      if (key === spotKey) return;
      spotKey = key;
      spots.replaceChildren(...keys.map((k) => {
        const [x, y] = k.split(",").map(Number);
        const node = el("div", { className: "tile spot" });
        place(node, x, y);
        return node;
      }));
    }

    function setGhost(x, y, icon) {
      ghost.hidden = x === null;
      if (x === null) return;
      ghost.textContent = icon || "";
      place(ghost, x, y);
    }

    function setHover(x, y) {
      hover.hidden = x === null;
      if (x !== null) place(hover, x, y);
    }

    function centerOn(x, y) {
      const f = handlers.focus();
      cam.tx = f.x - (x + 0.5) * TILE * cam.z;
      cam.ty = f.y - (y + 0.5) * TILE * cam.z;
      apply();
    }

    function tileRect(x, y) {
      const r = viewport.getBoundingClientRect();
      const size = TILE * cam.z;
      return { left: r.left + cam.tx + x * size, top: r.top + cam.ty + y * size, width: size, height: size };
    }

    return { build, setSpots, setGhost, setHover, centerOn, tileRect };
  }

  return { create };
})();
