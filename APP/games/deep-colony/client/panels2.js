/*
 * DOM panels, part 2 (panels.js calls these): research panel, schedules panel, storage filter
 * editor, debris hover lines, rotation bar and research-locked buildings in the build menu.
 *   DC.panels2.lockedBy(g, buildingId) -> tech id | null   (tech not done that unlocks it)
 *   DC.panels2.refresh(g)         research + schedules + rotation bar + build menu locks
 *   DC.panels2.filterEditor(g, id, b, d, canEdit) -> element    (hover panel, storage buildings)
 *   DC.panels2.itemLines(g, x, y) -> [element]                  (debris at a cell)
 * Same fill/signature pattern as panels.js; only AppDom.el / textContent (no player HTML).
 */
(() => {
  const DC = (window.DC = window.DC || {});
  const { $, el } = AppDom;
  const sigs = new Map();
  const send = (m) => DC.tools.send(m);
  const isPlayer = () => Boolean(DC.lobby.me() && DC.lobby.me().player);
  const bName = (g, id) => (g.defs.buildings[id] ? g.defs.buildings[id].name : id);
  const elName = (g, id) => (g.defs.elements[id] ? g.defs.elements[id].name : id);

  function fill(id, sig, make) {
    const s = JSON.stringify(sig);
    if (sigs.get(id) === s) return;
    sigs.set(id, s);
    $(id).replaceChildren(...make());
  }

  function lockedBy(g, id) {
    const techs = (g.research && g.research.techs) || {};
    for (const [tid, t] of Object.entries(techs)) if (!t.done && (t.unlocks || []).includes(id)) return tid;
    return null;
  }

  function research(g) {
    const r = g.research || { techs: {} };
    const techs = Object.entries(r.techs);
    const can = isPlayer();
    fill("research", [techs, r.current, can], () => techs.map(([id, t]) => {
      const avail = !t.done && (t.requires || []).every((q) => r.techs[q] && r.techs[q].done);
      const f = Math.min(1, t.progress / t.cost);
      return el("div", { className: "tech" + (r.current === id ? " cur" : "") },
        el("div", {}, el("b", {}, t.name), t.done ? " ✓" : "", ` (${Math.round(t.progress)}/${t.cost})`),
        el("div", { className: "muted" }, t.description || ""),
        el("div", { className: "bar", title: `${Math.round(t.progress)} / ${t.cost}` },
          el("div", { style: `width:${f * 100}%;background:#4aa3ff` })),
        (t.unlocks || []).length ? el("div", {}, "Unlocks: " + t.unlocks.map((b) => bName(g, b)).join(", ")) : "",
        (t.requires || []).length ? el("div", { className: "muted" },
          "Needs: " + t.requires.map((q) => (r.techs[q] ? r.techs[q].name : q) + (r.techs[q] && r.techs[q].done ? " ✓" : "")).join(", ")) : "",
        avail && can && r.current !== id ? el("button", { className: "t", textContent: "Research",
          onclick: () => send({ action: "research", tech: id }) }) : r.current === id ? el("div", { className: "muted" }, "Researching…") : "");
    }));
  }

  const BLOCK = { w: ["#d9822b", "Work"], d: ["#3fa7a0", "Downtime"], s: ["#4a5fc1", "Sleep"] };
  function schedules(g) {
    const s = g.schedules || {}, can = isPlayer();
    const dupes = Object.entries(g.dupes).map(([id, d]) => [id, d.name, d.schedule]);
    fill("schedules", [s, g.hour, dupes, can], () => {
      const rows = Object.entries(s).map(([sid, sc]) => el("div", { style: "margin-bottom:4px" },
        el("div", { className: "muted" }, `${sid}: ${sc.name || ""}`),
        el("div", { className: "sched" }, ...[...sc.blocks].map((c, i) => el("span", {
          className: "blk" + (i === g.hour ? " now" : ""), style: `background:${BLOCK[c][0]}`,
          title: `${i}:00 ${BLOCK[c][1]}`,
          onclick: () => {
            if (!can) return;
            const next = "wds"[("wds".indexOf(c) + 1) % 3];
            send({ action: "schedule", schedule: sid, blocks: sc.blocks.slice(0, i) + next + sc.blocks.slice(i + 1) });
          } })))));
      const legend = el("div", { className: "muted" }, "Click a block: work (orange), downtime (teal), sleep (blue). Outlined = now.");
      const who = dupes.map(([id, name, cur]) => el("div", {}, name + " ",
        el("select", { disabled: !can, onchange: (e) => send({ action: "assign", colonist: id, schedule: e.target.value }) },
          ...Object.keys(s).map((sid) => el("option", { value: sid, selected: sid === String(cur) }, sid)))));
      return [...rows, legend, ...who];
    });
  }

  function rotBar(g) {
    const T = DC.tools, id = T.state.tool === "build" ? T.state.building : null;
    const d = id && g.defs.buildings[id], on = Boolean(d && d.rotatable);
    fill("rotbar", [on, T.rot], () => !on ? [] : [
      el("span", { className: "muted" }, `Rotation: ${(T.rot || 0) * 90}° (R) `),
      el("button", { className: "t", textContent: "Rotate", onclick: () => T.rotate && T.rotate() })]);
  }

  function locks(g) {
    for (const b of $("buildmenu").querySelectorAll("[data-building]")) {
      const id = b.dataset.building, tech = lockedBy(g, id);
      if (b.dataset.base === undefined) b.dataset.base = b.title;
      b.style.opacity = tech ? "0.4" : "";
      b.style.cursor = tech ? "not-allowed" : "";
      b.title = tech ? `Research ${g.research.techs[tech].name} first` : b.dataset.base;
    }
  }

  function filterEditor(g, id, b, d, canEdit) {
    const all = !b.filter, set = new Set(b.filter || []);
    const send_ = (els) => send({ action: "filter", building: id, elements: els });
    const ids = g.defs.order.filter((e) => ["solid", "food"].includes((g.defs.elements[e] || {}).phase));
    return el("div", {},
      el("label", {}, el("input", { type: "checkbox", checked: all, disabled: !canEdit,
        onchange: (e) => send_(e.target.checked ? null : ids.slice()) }), " Accept everything"),
      all ? "" : el("div", { className: "filt" }, ...ids.map((e) => el("label", {},
        el("input", { type: "checkbox", checked: set.has(e), disabled: !canEdit,
          onchange: (ev) => { const n = new Set(set); if (ev.target.checked) n.add(e); else n.delete(e); send_([...n]); } }),
        " " + elName(g, e)))));
  }

  function itemLines(g, x, y) {
    const out = [];
    for (const it of Object.values(g.items || {})) {
      if (Math.floor(it.x) !== x || Math.floor(it.y) !== y) continue;
      const by = it.sw && g.players[it.sw];
      out.push(el("div", {}, `Debris: ${elName(g, it.el)} ${it.kg} kg`,
        it.sw ? ` (marked for sweep by ${by ? by.name : it.sw})` : ""));
    }
    return out;
  }

  function refresh(g) {
    research(g); schedules(g); rotBar(g); locks(g);
  }

  DC.panels2 = { lockedBy, refresh, filterEditor, itemLines };
})();
