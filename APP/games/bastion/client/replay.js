/*
 * Bastion: animating a siege replay (game.battle, see logic/battle.py for the format) on the
 * board's overlay. No rules here: the server simulated everything; this only draws it.
 *
 *   const replay = BastionReplay.create({ overlay, bar, banner, onKeep(hp), onEnd() })
 *   replay.play(game, board)   start animating game.battle (board: BastionBoard.build's result;
 *                              walls in the replay hide the board's own wall icons)
 *   replay.attach(board)       after the board was rebuilt mid-replay (re-hides those walls)
 *   replay.stop()              drop the animation and clear the overlay (no onEnd)
 *   replay.playing             true while animating
 *   replay.keep                the keep health shown at the current point of the replay
 */
(() => {
  const { el, svg } = AppDom;
  const TICK_MS = 125; // 8 ticks a second at x1
  const SPEEDS = [1, 2, 4];

  function create({ overlay, bar, banner, onKeep, onEnd }) {
    const self = { playing: false, keep: null };
    let game = null, battle = null, board = null;
    let layer = null, shots = null, raf = 0, last = 0, clock = 0, done = -1, speed = 1, paused = false;
    let sprites = {}, walls = {}, squads = {}, eventsAt = {}, frames = [], stunned = {};
    let bannerTimer = 0, positions = {}, toKeep = {};

    function cellCenter(x, y) { return BastionBoard.center(x, y); }

    function point(uid, p100) {
      const entry = battle.enemies[uid];
      const road = game.map.roads[entry[1]];
      const last = road.length - 1;
      const p = Math.min(Math.max(p100 / 100, 0), last);
      const i = Math.min(Math.floor(p), last - 1);
      const f = p - i;
      const [x1, y1] = road[i], [x2, y2] = road[i + 1];
      return cellCenter(x1 + (x2 - x1) * f, y1 + (y2 - y1) * f);
    }

    function frameMap(i) {
      const map = {};
      const list = frames[i] || [];
      for (let j = 0; j < list.length; j += 3) map[list[j]] = [list[j + 1], list[j + 2]];
      return map;
    }

    function place(node, pos) {
      node.style.left = `${pos.x}px`;
      node.style.top = `${pos.y}px`;
    }

    function effect(pos, text, className = "poof") {
      const node = el("div", { className }, text);
      place(node, pos);
      layer.append(node);
      setTimeout(() => node.remove(), 1000);
    }

    function circle(pos, radius, className) {
      const node = svg("circle", { cx: pos.x, cy: pos.y, r: radius * BastionBoard.CELL, class: className });
      shots.append(node);
      setTimeout(() => node.remove(), 700);
    }

    function enemyPos(uid) {
      return positions[uid] || null;
    }

    function renderBar() {
      const level = game.levels[battle.level - 1];
      const pause = el("button", { className: "plain", textContent: paused ? "▶" : "⏸", title: paused ? "Play" : "Pause" });
      pause.onclick = () => { paused = !paused; renderBar(); };
      const speeds = SPEEDS.map((s) => {
        const b = el("button", { className: "plain" + (s === speed ? " on" : ""), textContent: `×${s}` });
        b.onclick = () => { speed = s; renderBar(); };
        return b;
      });
      const skip = el("button", { className: "plain", textContent: "Skip ⏭" });
      skip.onclick = () => finish();
      bar.replaceChildren(el("span", {}, `⚔ Siege ${battle.level}: ${level ? level.name : ""}`), pause, ...speeds, skip);
      bar.hidden = false;
    }

    function setup() {
      layer = el("div");
      shots = svg("svg", {});
      overlay.replaceChildren(shots, layer);
      sprites = {}; walls = {}; squads = {}; stunned = {}; positions = {}; toKeep = {};
      eventsAt = {};
      for (const event of battle.events) {
        if (!eventsAt[event[0]]) eventsAt[event[0]] = [];
        eventsAt[event[0]].push(event);
      }
      frames = battle.frames;
      for (const event of battle.events) if (event[1] === "k") toKeep[event[2]] = true;
      for (const [k, [card, , hp, max]] of Object.entries(battle.walls)) {
        const [x, y] = k.split(",").map(Number);
        const node = el("div", { className: "wall-live" }, game.cards[card].icon, BastionBoard.hpBar(hp, max));
        node.style.left = `${x * BastionBoard.CELL}px`;
        node.style.top = `${y * BastionBoard.CELL}px`;
        layer.append(node);
        walls[k] = { node, max };
      }
      for (const [sid, [x, y, max]] of Object.entries(battle.squads)) {
        const node = el("div", { className: "squad" }, "⚔️", BastionBoard.hpBar(max, max));
        const pos = cellCenter(x, y);
        place(node, { x: pos.x + 8, y: pos.y - 8 });
        layer.append(node);
        squads[sid] = { node, max };
      }
      self.keep = battle.keep[0];
      onKeep(self.keep);
    }

    function attach(newBoard) {
      board = newBoard;
      if (!self.playing || !board) return;
      board.hide(Object.keys(battle.walls));
      for (const k of Object.keys(stunned)) board.cells[k] && board.cells[k].classList.add("stunned");
    }

    function handle(event, tick) {
      const type = event[1];
      if (type === "s") {
        const [, , x, y, uid, style] = event;
        const from = cellCenter(x, y);
        const to = enemyPos(uid);
        if (style !== "none" && to) {
          const line = svg("line", { x1: from.x, y1: from.y, x2: to.x, y2: to.y, class: `shot ${style}` });
          shots.append(line);
          setTimeout(() => line.remove(), 400);
        }
        if (style === "rock" && to) circle(to, 1.1, "blast");
        if (style === "oil") circle(from, 1.5, "blast");
      } else if (type === "k") {
        const [, , uid, hp] = event;
        const pos = enemyPos(uid);
        const lost = self.keep - hp;
        self.keep = hp;
        onKeep(hp);
        const keepCell = document.getElementById("keep-cell");
        if (keepCell) { keepCell.classList.remove("keep-hit"); void keepCell.offsetWidth; keepCell.classList.add("keep-hit"); }
        const [kx, ky] = game.map.keep;
        effect(cellCenter(kx, ky), `-${lost}`, "float");
        if (sprites[uid]) { sprites[uid].remove(); delete sprites[uid]; }
        if (pos) effect(pos, "💥");
      } else if (type === "w") {
        const [, , k, hp] = event;
        const wall = walls[k];
        if (!wall) return;
        if (hp <= 0) {
          const [x, y] = k.split(",").map(Number);
          effect(cellCenter(x, y), "💥");
          wall.node.remove();
          delete walls[k];
        } else {
          wall.node.querySelector(".hpbar").replaceWith(BastionBoard.hpBar(hp, wall.max));
        }
      } else if (type === "q") {
        const [, , sid, hp] = event;
        const squad = squads[sid];
        if (!squad) return;
        squad.node.hidden = hp <= 0;
        squad.node.querySelector(".hpbar").replaceWith(BastionBoard.hpBar(hp, squad.max));
      } else if (type === "b") {
        const [, , x10, y10, r10, stun] = event;
        const pos = cellCenter(x10 / 10, y10 / 10);
        circle(pos, r10 / 10, "blast");
        effect(pos, "🔥");
        for (const k of Object.keys(battle.towers || {})) {
          const [x, y] = k.split(",").map(Number);
          if (Math.hypot(x - x10 / 10, y - y10 / 10) <= r10 / 10) {
            stunned[k] = tick + (stun || 0);
            board && board.cells[k] && board.cells[k].classList.add("stunned");
          }
        }
      } else if (type === "x") {
        const pos = enemyPos(event[2]);
        if (pos) effect(pos, "💥");
        if (sprites[event[2]]) { sprites[event[2]].remove(); delete sprites[event[2]]; }
      }
    }

    function advanceTo(tick) {
      while (done < tick && done < frames.length - 1) {
        done += 1;
        const now = frameMap(done);
        for (const event of eventsAt[done] || []) handle(event, done);
        for (const uid of Object.keys(sprites)) {
          if (!(uid in now)) {
            if (enemyPos(uid)) effect(enemyPos(uid), "✖");
            sprites[uid].remove();
            delete sprites[uid];
            delete positions[uid];
          }
        }
        for (const [k, until] of Object.entries(stunned)) {
          if (until <= done) {
            delete stunned[k];
            board && board.cells[k] && board.cells[k].classList.remove("stunned");
          }
        }
      }
    }

    function draw() {
      const i = Math.min(Math.floor(clock), frames.length - 1);
      const f = clock - i;
      const now = frameMap(i);
      const next = frameMap(Math.min(i + 1, frames.length - 1));
      for (const [uid, [p, hp]] of Object.entries(now)) {
        let sprite = sprites[uid];
        const entry = battle.enemies[uid];
        if (!entry) continue;
        const info = game.enemies[entry[0]];
        if (!sprite) {
          sprite = el("div", { className: "enemy" + (info.boss ? " boss" : "") + (info.flying ? " flying" : ""), title: info.name },
            info.icon, BastionBoard.hpBar(hp, entry[2]));
          layer.append(sprite);
          sprites[uid] = sprite;
        }
        const end = (game.map.roads[entry[1]].length - 1) * 100;
        const target = next[uid] ? next[uid][0] : toKeep[uid] ? end : p;
        const pos = point(uid, p + (target - p) * f);
        positions[uid] = pos;
        sprite.style.transform = `translate(${pos.x}px, ${pos.y}px)`;
        if (sprite.dataset.hp !== String(hp)) {
          sprite.dataset.hp = String(hp);
          sprite.querySelector(".hpbar").replaceWith(BastionBoard.hpBar(hp, entry[2]));
        }
      }
    }

    function loop(time) {
      if (!self.playing) return;
      const dt = last ? Math.min(100, time - last) : 0;
      last = time;
      if (!paused) clock += (dt * speed) / TICK_MS;
      if (clock >= frames.length) {
        advanceTo(frames.length - 1);
        finish();
        return;
      }
      advanceTo(Math.floor(clock));
      draw();
      raf = requestAnimationFrame(loop);
    }

    function cleanup() {
      cancelAnimationFrame(raf);
      overlay.replaceChildren();
      bar.hidden = true;
      if (board) {
        board.showAll();
        for (const cell of Object.values(board.cells)) cell.classList.remove("stunned");
      }
    }

    function finish() {
      if (!self.playing) return;
      self.playing = false;
      self.keep = battle.keep[1];
      cleanup();
      const s = battle.summary;
      const level = game.levels[battle.level - 1];
      const lines = [`${s.kills} enemies slain`];
      if (s.leaked) lines.push(`${s.leaked} reached the keep (−${s.keepDamage} ♥)`);
      if (s.wallsLost) lines.push(`${s.wallsLost} wall${s.wallsLost > 1 ? "s" : ""} destroyed`);
      banner.replaceChildren(el("b", {}, battle.held ? "The siege is held!" : "The keep has fallen!"),
        el("div", {}, level ? level.name : ""), el("div", { className: "small" }, lines.join(" · ")));
      banner.hidden = false;
      clearTimeout(bannerTimer);
      bannerTimer = setTimeout(() => { banner.hidden = true; }, 3500);
      banner.onclick = () => { banner.hidden = true; };
      onEnd();
    }

    self.play = (newGame, newBoard) => {
      self.stop();
      game = newGame;
      battle = newGame.battle;
      board = newBoard;
      banner.hidden = true;
      clock = 0; done = -1; last = 0; paused = false;
      self.playing = true;
      setup();
      attach(newBoard);
      renderBar();
      raf = requestAnimationFrame(loop);
    };
    self.attach = (newBoard) => attach(newBoard);
    self.update = (newGame) => { if (self.playing) game = newGame; }; // map, cards and enemies never change
    self.stop = () => {
      if (!self.playing) return;
      self.playing = false;
      cleanup();
    };
    return self;
  }

  window.BastionReplay = { create };
})();
