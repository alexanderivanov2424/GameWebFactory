/*
 * Hex Realms: the combat replay that plays when a turn resolves. It glides the map to each combat you
 * saw (battles, shots, sieges, tower fire, in the order they happened), shows the dice on the left
 * (you) and right (the other side) of the screen round by round with the hits lit, then the result,
 * and moves on to the next one; at the end the view goes back to where it was. A Skip button (or Esc)
 * stops it. No rules here: everything comes from game.events (logic/combat.py's event shapes).
 *
 *   const replay = HexReplay.create(map, { onChange(playing) })
 *   replay.play(game, you)   start (stops one already playing); false when there's nothing to show or
 *                            the player turned replays off (the caller flashes the cells instead)
 *   replay.skip()            stop now and put the view back
 *   replay.playing           true while it plays
 *   HexReplay.steps(game, you)   one step per combat: {cells, title, left, right, rounds, result}
 *
 * Player settings (Settings -> Hex Realms, AppSettings.addPageSettings): SPEED_KEY (a multiplier:
 * "0.5" slow ... "4" very fast) and SKIP_KEY (true = never play). Durations below are at speed 1.
 * DOM: #replay (with #replay-bar, #replay-left, #replay-right) in index.html; #game gets the
 * "replaying" class while it plays (the side columns hide).
 */
(() => {
  const { $, el, fill } = AppDom;
  const SPEED_KEY = "hex-realms.replaySpeed", SKIP_KEY = "hex-realms.replaySkip";
  const PAN = 900, ROUND = 850, RESULT = 1100, BACK = 700, ZOOM = 1.8;

  AppSettings.addPageSettings("Hex Realms", [
    { key: SPEED_KEY, label: "Combat replay speed", type: "select", default: "1",
      options: [["0.5", "Slow"], ["1", "Normal"], ["2", "Fast"], ["4", "Very fast"]],
      hint: "How fast the end-of-turn combat replay moves from fight to fight." },
    { key: SKIP_KEY, label: "Skip combat replays", type: "checkbox", default: false,
      hint: "Don't play the replay; combat cells just flash and the Report tab lists the dice." },
  ]);

  const HIT = 4;  // structures are hit on 4+ (units' need comes with each event)

  // Who fought in event e, as two sides {owner, name, icon, hp: [before, after] | null, dead, role};
  // `rolls` are [aDice, bDice] per round, with the roll each side needs to hit.
  function describe(e, game) {
    const content = game.content;
    const unit = (s, role) => ({ owner: s.owner, name: content.units[s.type]?.name || s.type, icon: content.units[s.type]?.icon || "",
      max: content.units[s.type]?.hp, hp: [s.hp, s.hp], dead: (e.dead || []).includes(s.unit), role });
    const struct = (stype, owner, role, damage) => ({ owner, name: content.structures[stype]?.name || stype,
      icon: content.structures[stype]?.icon || "", hp: null, damage, dead: false, role });
    const hits = (roll, need) => (roll || []).filter((x) => x >= need).length;
    if (e.t === "battle") {
      const a = unit(e.a, "attacks"), b = unit(e.b, "defends");
      a.hp[1] = e.hp ? e.hp[0] : a.hp[0]; b.hp[1] = e.hp ? e.hp[1] : b.hp[0];
      return { kind: "Battle", at: e.b.at, cells: [e.a.at, e.b.at], a, b, rounds: e.rounds, needA: e.b.need || HIT, needB: e.a.need || HIT };
    }
    if (e.t === "shot" && e.b) {
      const a = unit(e.a, "shoots"), b = unit(e.b, "is shot");
      b.hp[1] = Math.max(0, b.hp[0] - e.hits);
      return { kind: "Shot", at: e.b.at, cells: [e.a.at, e.b.at], a, b, rounds: [[e.roll, []]], needA: e.b.need || HIT, needB: HIT };
    }
    if (e.t === "shot") {
      return { kind: "Shot", at: e.at, cells: [e.a.at, e.at], a: unit(e.a, "shoots"), b: struct(e.stype, e.owner, "is shot", e.damage),
        rounds: [[e.roll, []]], needA: HIT, needB: HIT };
    }
    if (e.t === "siege") {
      const a = unit(e.a, "assaults");
      a.hp[1] = Math.max(0, a.hp[0] - hits(e.back, HIT));
      return { kind: "Siege", at: e.at, cells: [e.a.at, e.at], a, b: struct(e.stype, e.owner, "defends", e.damage),
        rounds: [[e.roll, e.back]], needA: HIT, needB: HIT };
    }
    if (e.t === "tower") {
      const b = unit(e.b, "is shot");
      b.hp[1] = Math.max(0, b.hp[0] - e.hits);
      return { kind: "Tower fire", at: e.b.at, cells: [e.at, e.b.at], a: struct(game.structures[e.structure]?.type || "tower", e.owner, "shoots"), b,
        rounds: [[e.roll, []]], needA: e.b.need || HIT, needB: HIT };
    }
    return null;
  }

  // One step per combat, you on the left when you took part.
  function steps(game, you) {
    const evs = Object.keys(game.events || {}).sort((x, y) => x - y).map((i) => game.events[i]);
    return evs.map((e) => describe(e, game)).filter(Boolean).map((d) => {
      const swap = d.b.owner === you && d.a.owner !== you;
      const [left, right] = swap ? [d.b, d.a] : [d.a, d.b];
      const [needL, needR] = swap ? [d.needB, d.needA] : [d.needA, d.needB];
      const rounds = d.rounds.map(([ra, rb]) => (swap ? [rb, ra] : [ra, rb]));
      return { kind: d.kind, cells: d.cells.filter(Boolean), title: `${d.a.name} ${d.a.role} ${d.b.name}`,
        left, right, needL, needR, rounds };
    });
  }

  function create(map, handlers = {}) {
    let run = 0, saved = null;
    const replay = { playing: false, play, skip };
    const box = $("replay");

    const speed = () => { const s = Number(AppSettings.get(SPEED_KEY) ?? 1); return s > 0 ? s : 1; };
    const wait = (ms) => new Promise((r) => setTimeout(r, ms / speed()));

    function setPlaying(on) {
      replay.playing = on;
      box.hidden = !on;
      $("game").classList.toggle("replaying", on);
      if (!on) { map.mark([]); fill($("replay-left")); fill($("replay-right")); }
      handlers.onChange?.(on);
    }

    // A replay that starts while another plays (or glides back) keeps the first saved view.
    function play(game, you) {
      if (replay.playing) { run++; setPlaying(false); }
      if (AppSettings.get(SKIP_KEY)) { skip(); return false; }
      const list = steps(game, you);
      if (!list.length) { skip(); return false; }
      const token = ++run;
      saved ||= map.getView();
      setPlaying(true);
      (async () => {
        for (let i = 0; i < list.length; i++) {
          await show(game, list[i], i, list.length, token);
          if (token !== run) return;
        }
        finish(token);
      })();
      return true;
    }

    function skip() {
      run++;
      if (replay.playing) setPlaying(false);
      if (saved) map.setView(saved, 0);
      saved = null;
    }

    async function finish(token) {
      setPlaying(false);
      if (saved) await map.setView(saved, BACK / speed());
      if (token === run) saved = null;
    }

    function sidePanel(game, s) {
      const p = game.players[s.owner];
      return [el("div", { className: "hr-rp-who" }, el("span", { className: "hr-dot", style: `background:${p?.color || "#888"}` }), p?.name || s.owner),
        el("div", { className: "hr-rp-unit" }, el("span", { className: "hr-rp-icon" }, s.icon), ` ${s.name}`),
        el("div", { className: "muted small" }, s.role),
        el("div", { className: "hr-rp-rolls" })];
    }

    const dieEl = (x, need) => el("span", { className: `hr-die${x >= need ? " hit" : ""}` }, String(x));

    function outcome(s) {
      if (s.hp) return s.dead ? el("div", { className: "hr-rp-out neg" }, "Killed") : el("div", { className: "hr-rp-out" }, `HP ${s.hp[0]} → ${s.hp[1]}`);
      return el("div", { className: "hr-rp-out" }, s.damage ? `${s.damage} damage` : "No damage");
    }

    async function show(game, st, i, n, token) {
      fill($("replay-bar"), el("b", {}, `${st.kind} ${i + 1} / ${n}`), el("span", { className: "small" }, st.title),
        el("span", { className: "spacer" }), el("button", { className: "hr-btn", onclick: () => skip() }, "Skip (Esc)"));
      const L = $("replay-left"), R = $("replay-right");
      fill(L, sidePanel(game, st.left)); fill(R, sidePanel(game, st.right));
      map.mark(st.cells);
      map.flash([{ at: st.cells[st.cells.length - 1], kind: "battle" }]);
      await map.focus(st.cells, ZOOM, PAN / speed());
      if (token !== run) return;
      for (const [k, [rl, rr]] of st.rounds.entries()) {
        const row = (rolls, need) => el("div", { className: "hr-rp-row" }, el("span", { className: "muted small" }, st.rounds.length > 1 ? `R${k + 1}` : ""),
          (rolls || []).length ? (rolls || []).map((x) => dieEl(x, need)) : el("span", { className: "muted small" }, "—"));
        L.querySelector(".hr-rp-rolls").append(row(rl, st.needL));
        R.querySelector(".hr-rp-rolls").append(row(rr, st.needR));
        await wait(ROUND);
        if (token !== run) return;
      }
      L.append(outcome(st.left)); R.append(outcome(st.right));
      await wait(RESULT);
    }

    return replay;
  }

  window.HexReplay = { create, steps };
})();
