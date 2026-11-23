/*
 * Snowbound view: the full-screen canvas. The camera follows your character (predicted by
 * input.js), or for spectators the player picked in the Team panel (SB.view.spectate = pid).
 *   SB.view.init(lobby, rt)  once; draws every animation frame
 *   SB.view.snap(state)      call on every snapshot (keeps the last two unit positions to interpolate)
 *   SB.view.reset()          new game
 *   SB.view.toLot(clientX, clientY) -> [x, y] lot under a screen point
 *   SB.view.zoomBy(factor), SB.view.puff(x, y, amount)   zoom; a snow puff (+amount) at world x, y
 *   SB.view.drawMinimap(canvas)   the minimap (called by hud.js)
 * Draw order: lots (SB.grid.image scaled up) -> snow bank edges, sparkles, features, road markings ->
 * landmarks (ruins) -> heat glow, cabin, huts, depots, rail stations -> rally flag, golden snowflake -> units (placed ones glow; load bars, processor gauges) -> jet beams -> characters -> aim box -> particles ->
 * weather -> off-screen arrows (snowflake, cabin) -> frost vignette when you're cold.
 */
(() => {
  const SB = (window.SB = window.SB || {});
  const { $ } = AppDom;
  const FEATURE_EMOJI = { t: "🌲", T: "🌲", h: "🏚️", H: "🏚️", g: "⛽", G: "⛽", C: "📦", K: "⛷️" };
  const TEAM = { color: "#d8e2ec" };
  const FACES = { ok: "🙂", frostbite: "🥶", starving: "😫", frenzy: "🤩" };

  const view = (SB.view = { spectate: null });
  const cam = { x: 0, y: 0, zoom: 40 };
  let lobby, rt, canvas, ctx, last = performance.now();
  let prevUnits = null, curUnits = null;
  const particles = [];
  const snowfall = Array.from({ length: 260 }, () => ({ x: Math.random(), y: Math.random(), s: 0.5 + Math.random() }));

  const dpr = () => window.devicePixelRatio || 1;
  const Z = () => cam.zoom * dpr();
  const sx = (x) => (x - cam.x) * Z() + canvas.width / 2;
  const sy = (y) => (y - cam.y) * Z() + canvas.height / 2;

  view.toLot = (clientX, clientY) => {
    const rect = canvas.getBoundingClientRect();
    const px = (clientX - rect.left) * dpr(), py = (clientY - rect.top) * dpr();
    return [Math.floor((px - canvas.width / 2) / Z() + cam.x), Math.floor((py - canvas.height / 2) / Z() + cam.y)];
  };
  view.zoomBy = (f) => { cam.zoom = Math.max(14, Math.min(90, cam.zoom * f)); };
  view.puff = (x, y, amount) => {
    const now = performance.now();
    for (let k = 0; k < 6; k++) particles.push({ kind: "puff", x, y, vx: (Math.random() - 0.5) * 2, vy: -Math.random() * 1.5, t: now });
    if (amount > 0) particles.push({ kind: "text", x, y, text: "+" + SB.fmt(amount), t: now });
  };
  view.snap = (state) => {
    const units = state && state.private && state.private.units;
    if (!units) return;
    if (curUnits && curUnits.units === units) return;
    prevUnits = curUnits;
    curUnits = { t: performance.now(), units };
  };
  view.reset = () => { prevUnits = curUnits = null; particles.length = 0; view.spectate = null; cam.zoom = 40; };

  function unitPositions(now) {
    if (!curUnits) return [];
    const span = prevUnits ? Math.max(30, curUnits.t - prevUnits.t) : 1;
    const a = Math.min(1, (now - curUnits.t) / span);
    return Object.entries(curUnits.units).map(([id, u]) => {
      const p = prevUnits && prevUnits.units[id];
      return p ? { ...u, x: p.x + (u.x - p.x) * a, y: p.y + (u.y - p.y) * a } : u;
    });
  }

  function emoji(text, x, y, size) {
    ctx.font = `${Math.round(size)}px system-ui, "Segoe UI Emoji", "Apple Color Emoji", sans-serif`;
    ctx.fillText(text, x, y);
  }

  function hash(x, y) { let h = (x * 374761393 + y * 668265263) | 0; h = (h ^ (h >>> 13)) * 1274126177; return (h ^ (h >>> 16)) >>> 0; }

  function drawLots(game, now) {
    const z = Z();
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(SB.grid.image, sx(0), sy(0), game.w * z, game.h * z);
    const x0 = Math.max(0, Math.floor(cam.x - canvas.width / 2 / z) - 1), x1 = Math.min(game.w - 1, Math.ceil(cam.x + canvas.width / 2 / z) + 1);
    const y0 = Math.max(0, Math.floor(cam.y - canvas.height / 2 / z) - 1), y1 = Math.min(game.h - 1, Math.ceil(cam.y + canvas.height / 2 / z) + 1);
    const g = SB.grid;
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        const px = sx(x), py = sy(y), level = g.level(x, y), reached = g.reached(x, y);
        if (!g.passable(x, y)) {
          // A snow bank: lit top edge, shadow cast on open ground below and to the right.
          if (g.passable(x, y - 1)) { ctx.fillStyle = "rgba(255,255,255,0.75)"; ctx.fillRect(px, py, z, z * 0.12); }
          if (g.passable(x, y + 1)) {
            ctx.fillStyle = "rgba(120,140,170,0.55)"; ctx.fillRect(px, py + z * 0.82, z, z * 0.18);
            ctx.fillStyle = "rgba(20,30,50,0.25)"; ctx.fillRect(px, py + z, z, z * 0.2);
          }
          if (g.passable(x + 1, y)) { ctx.fillStyle = "rgba(20,30,50,0.16)"; ctx.fillRect(px + z, py, z * 0.14, z); }
        }
        if (level && !reached) {
          const hsh = hash(x, y);
          if (hsh % 5 === 0) {
            ctx.globalAlpha = 0.5 + 0.5 * Math.sin(now / 400 + (hsh % 100));
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(px + ((hsh >> 4) % 100) / 100 * z, py + ((hsh >> 12) % 100) / 100 * z, 1.5 * dpr(), 1.5 * dpr());
            ctx.globalAlpha = 1;
          }
        }
        const road = g.road(x, y);
        if (road >= 3 && !level && z > 18) {
          ctx.fillStyle = road === 4 ? "rgba(255,140,60,0.55)" : "rgba(255,255,255,0.45)";
          if ((x + y) % 2 === 0) ctx.fillRect(px + z * 0.4, py + z * 0.46, z * 0.2, z * 0.08);
        }
        const f = g.feat(x, y);
        if (FEATURE_EMOJI[f]) {
          emoji(FEATURE_EMOJI[f], px + z / 2, py + z / 2, z * (f === "t" ? 0.8 : 0.9));
          if (f === "t" || f === "h" || f === "g") { ctx.fillStyle = "rgba(245,249,255,0.45)"; ctx.fillRect(px, py + z * 0.55, z, z * 0.45); }
        }
      }
    }
  }

  function drawLandmarks(game) {
    const z = Z(), defs = game.defs.landmarks;
    for (const lm of Object.values(game.landmarks || {})) {
      const d = defs[lm.id];
      if (!d) continue;
      const px = sx(lm.x), py = sy(lm.y), size = lm.size * z;
      ctx.lineWidth = Math.max(2, z * 0.06);
      ctx.strokeStyle = lm.found ? "rgba(255,215,0,0.9)" : "rgba(190,160,255,0.85)";
      ctx.setLineDash(lm.found ? [] : [z * 0.25, z * 0.15]);
      ctx.strokeRect(px + 1, py + 1, size - 2, size - 2);
      ctx.setLineDash([]);
      ctx.globalAlpha = lm.found ? 1 : 0.55;
      emoji(d.icon, px + size / 2, py + size / 2, z * Math.min(1.8, lm.size * 0.7));
      ctx.globalAlpha = 1;
      if (!lm.found) {
        ctx.font = `bold ${Math.round(Math.max(10 * dpr(), z * 0.3))}px system-ui, sans-serif`;
        ctx.lineWidth = 3; ctx.strokeStyle = "rgba(0,0,0,0.6)"; ctx.fillStyle = "#fff";
        const label = `${d.name} · ${lm.left} left`;
        ctx.strokeText(label, px + size / 2, py - z * 0.3); ctx.fillText(label, px + size / 2, py - z * 0.3);
      }
    }
  }

  function drawHeat(game, now) {
    const z = Z();
    const glow = (x, y, r) => {
      const g = ctx.createRadialGradient(sx(x), sy(y), 0, sx(x), sy(y), r * z);
      g.addColorStop(0, "rgba(255,160,60,0.25)"); g.addColorStop(1, "rgba(255,160,60,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(sx(x), sy(y), r * z, 0, Math.PI * 2); ctx.fill();
    };
    const [cx, cy] = game.cabin;
    if (game.stove.lit) {
      glow(cx + 0.5, cy + 0.5, game.heat.cabin);
      for (const [hx, hy] of Object.values(game.huts)) glow(hx + 0.5, hy + 0.5, game.heat.hut);
    }
    emoji(game.stove.lit ? "🏠" : "🏚️", sx(cx + 0.5), sy(cy + 0.4), z * 2.6);
    for (const [hx, hy] of Object.values(game.huts)) emoji("🛖", sx(hx + 0.5), sy(hy + 0.5), z * 1.1);
    for (const [dx, dy] of Object.values(game.depots || {})) emoji("🏪", sx(dx + 0.5), sy(dy + 0.5), z * 1.1);
    for (const [mx, my] of Object.values(game.markets || {})) emoji("🚉", sx(mx + 0.5), sy(my + 0.5), z * 1.6);
    if (game.stove.lit) {
      for (let k = 0; k < 3; k++) {
        const a = ((now / 1600 + k / 3) % 1);
        ctx.globalAlpha = 0.5 * (1 - a);
        ctx.fillStyle = "#cfd6de";
        ctx.beginPath(); ctx.arc(sx(cx + 1.1 + a * 0.6), sy(cy - 0.6 - a * 1.5), z * (0.15 + a * 0.3), 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;
    }
  }

  function drawPlaced(u, d, owner, now) {
    // Braziers glow over the ring they melt; stills bubble. Drawn under the icon.
    const z = Z(), x = sx(u.x), y = sy(u.y);
    if (d.kind === "brazier" && u.s !== "unlit") {
      const r = z * (2.3 + 0.1 * Math.sin(now / 200 + u.x));
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, "rgba(255,140,40,0.45)"); g.addColorStop(1, "rgba(255,140,40,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
      if (Math.random() < 0.15) particles.push({ kind: "spark", x: u.x + (Math.random() - 0.5) * 0.4, y: u.y, vx: (Math.random() - 0.5) * 0.4, vy: -1.5, t: now });
    }
    if ((d.kind === "still" || d.kind === "processor" || d.kind === "spring") && u.s === "working" && Math.random() < 0.1) {
      particles.push({ kind: "puff", x: u.x, y: u.y - 0.4, vx: 0, vy: -0.8, t: now });
    }
    ctx.fillStyle = owner.color; ctx.globalAlpha = 0.6;
    ctx.fillRect(x - z * 0.45, y + z * 0.3, z * 0.9, z * 0.12);
    ctx.globalAlpha = 1;
    emoji(u.s === "unlit" ? "🪵" : d.icon, x, y, z * 0.9);
    if (u.f) {
      bar(x, y - z * 0.6, u.f[0], "#9fd8ff");
      if (u.f[1]) {
        ctx.font = `bold ${Math.round(Math.max(9 * dpr(), z * 0.24))}px system-ui, sans-serif`;
        ctx.lineWidth = 3; ctx.strokeStyle = "rgba(0,0,0,0.6)"; ctx.fillStyle = "#fff";
        const label = `${SB.fmt(u.f[1])} ${lobby.state.game.defs.goods[d.recipe.out].icon}`;
        ctx.strokeText(label, x, y + z * 0.62); ctx.fillText(label, x, y + z * 0.62);
      }
      if (u.s === "full") emoji("⏸️", x + z * 0.4, y - z * 0.4, z * 0.35);
    }
    if (u.s === "stalled") emoji("⛽", x + z * 0.4, y - z * 0.4, z * 0.35);
  }

  function bar(x, y, fill, color) {
    const z = Z(), w = z * 0.7, h = Math.max(3, z * 0.09);
    ctx.fillStyle = "rgba(0,0,0,0.45)"; ctx.fillRect(x - w / 2, y, w, h);
    ctx.fillStyle = color; ctx.fillRect(x - w / 2, y, w * Math.min(1, fill), h);
  }

  function drawBeams(game) {
    const z = Z();
    for (const b of Object.values(game.beams || {})) {
      ctx.lineCap = "round";
      ctx.strokeStyle = "rgba(255,255,255,0.6)"; ctx.lineWidth = z * 0.9;
      ctx.beginPath(); ctx.moveTo(sx(b.x0), sy(b.y0)); ctx.lineTo(sx(b.x1), sy(b.y1)); ctx.stroke();
      ctx.strokeStyle = b.c; ctx.lineWidth = z * 0.3;
      ctx.beginPath(); ctx.moveTo(sx(b.x0), sy(b.y0)); ctx.lineTo(sx(b.x1), sy(b.y1)); ctx.stroke();
      ctx.lineCap = "butt";
    }
  }

  function drawUnits(game, now) {
    const z = Z(), defs = game.defs.machines;
    for (const u of unitPositions(now)) {
      const owner = game.players[u.p] || TEAM;  // the team's machines: coloured by who bought them, if still here
      const d = defs[u.m];
      if (!d) continue;
      if (d.placed) { drawPlaced(u, d, owner, now); continue; }
      const big = d.kind === "worker" || d.kind === "dog" || d.kind === "buddy" ? 0.75 : 1.05;
      const bob = u.s === "moving" ? Math.abs(Math.sin(now / 90 + u.x * 3)) * z * 0.08 : 0;
      const x = sx(u.x), y = sy(u.y);
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      ctx.beginPath(); ctx.ellipse(x, y + z * 0.3 * big, z * 0.32 * big, z * 0.12 * big, 0, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = owner.color; ctx.lineWidth = Math.max(2, z * 0.06);
      ctx.beginPath(); ctx.arc(x, y + z * 0.3 * big, z * 0.3 * big, 0, Math.PI * 2); ctx.stroke();
      emoji(d.icon, x, y - bob, z * 0.8 * big);
      if (u.s === "stalled") emoji("⛽", x + z * 0.4, y - z * 0.5, z * 0.4);
      if (u.s === "charging") emoji("⚡", x + z * 0.4, y - z * 0.5, z * 0.35);
      if (u.s === "idle") emoji("💤", x + z * 0.4, y - z * 0.5, z * 0.35);
      if (u.l) {
        bar(x, y - z * 0.62 * big, u.l, d.kind === "sled" ? "#ffd54f" : "#ffffff");
        if (d.kind === "sled") emoji("📦", x - z * 0.4, y - z * 0.45, z * 0.35);
      }
      if (u.s === "working" && Math.random() < 0.08) {
        particles.push({ kind: "puff", x: u.x + (Math.random() - 0.5), y: u.y + (Math.random() - 0.5), vx: (Math.random() - 0.5), vy: -Math.random(), t: now });
      }
    }
  }

  function drawPlayers(game, now, state) {
    const z = Z();
    const others = rt.sample((g) => (g && g.players) || {});
    for (const [pid, p] of Object.entries(game.players)) {
      const pos = pid === state.you && SB.input.me ? SB.input.me : others[pid] || p;
      const x = sx(pos.x), y = sy(pos.y), r = z * 0.32;
      ctx.fillStyle = "rgba(0,0,0,0.22)";
      ctx.beginPath(); ctx.ellipse(x, y + r * 0.9, r, r * 0.4, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = p.color; ctx.strokeStyle = "#fff"; ctx.lineWidth = Math.max(2, z * 0.05);
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      emoji(FACES[p.status] || "🙂", x, y - r * 0.05, r * 1.4);
      if (p.swing) {
        const a = (now / 60) % (Math.PI * 2);
        ctx.strokeStyle = "#8a6a45"; ctx.lineWidth = Math.max(2, z * 0.07);
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + Math.cos(a) * r * 1.8, y + Math.sin(a) * r * 1.8); ctx.stroke();
        if (pid !== state.you && Math.random() < 0.2) particles.push({ kind: "puff", x: pos.x + Math.cos(a), y: pos.y + Math.sin(a), vx: 0, vy: -1, t: now });
      }
      ctx.font = `bold ${Math.round(Math.max(11 * dpr(), z * 0.28))}px system-ui, sans-serif`;
      ctx.lineWidth = 3; ctx.strokeStyle = "rgba(0,0,0,0.6)"; ctx.fillStyle = "#fff";
      ctx.strokeText(p.name, x, y - r * 1.9); ctx.fillText(p.name, x, y - r * 1.9);
    }
  }

  function drawAim(state) {
    const aim = SB.input.aim;
    if (!aim || !SB.input.me) return;
    const [x, y] = aim, z = Z();
    if (SB.input.demolish) {
      ctx.fillStyle = "rgba(255,70,70,0.3)"; ctx.fillRect(sx(x), sy(y), z, z);
      ctx.lineWidth = Math.max(2, z * 0.06); ctx.strokeStyle = "rgba(255,90,90,0.9)";
      ctx.beginPath(); ctx.moveTo(sx(x) + z * 0.2, sy(y) + z * 0.2); ctx.lineTo(sx(x) + z * 0.8, sy(y) + z * 0.8);
      ctx.moveTo(sx(x) + z * 0.8, sy(y) + z * 0.2); ctx.lineTo(sx(x) + z * 0.2, sy(y) + z * 0.8); ctx.stroke();
      return;
    }
    if (SB.input.road) {
      const ok = SB.input.canRoad(x, y);
      ctx.fillStyle = ok ? "rgba(120,220,120,0.35)" : "rgba(255,90,90,0.3)";
      ctx.fillRect(sx(x), sy(y), z, z);
      ctx.lineWidth = Math.max(2, z * 0.05); ctx.strokeStyle = ok ? "#9cf09c" : "rgba(255,90,90,0.8)";
      ctx.strokeRect(sx(x) + 1, sy(y) + 1, z - 2, z - 2);
      return;
    }
    if (!SB.grid.workable(x, y)) return;
    const ok = SB.input.inReach(x, y);
    ctx.lineWidth = Math.max(2, z * 0.06);
    ctx.strokeStyle = ok ? "#ffffff" : "rgba(255,90,90,0.8)";
    ctx.setLineDash(ok ? [] : [z * 0.15, z * 0.1]);
    ctx.strokeRect(sx(x) + 1, sy(y) + 1, z - 2, z - 2);
    ctx.setLineDash([]);
    if (ok && state.private) {
      ctx.font = `${Math.round(11 * dpr())}px system-ui, sans-serif`;
      ctx.fillStyle = "#123"; ctx.fillText(`~${SB.fmt(SB.grid.snowAt(x, y))}`, sx(x) + z / 2, sy(y) + z + 9 * dpr());
    }
  }

  function drawParticles(now, dt) {
    const z = Z();
    for (let k = particles.length - 1; k >= 0; k--) {
      const p = particles[k], age = (now - p.t) / (p.kind === "text" ? 900 : 600);
      if (age >= 1) { particles.splice(k, 1); continue; }
      ctx.globalAlpha = 1 - age;
      if (p.kind === "spark") {
        p.x += p.vx * dt; p.y += p.vy * dt;
        ctx.fillStyle = "#ffb347";
        ctx.fillRect(sx(p.x), sy(p.y), 2 * dpr(), 2 * dpr());
      } else if (p.kind === "puff") {
        p.x += p.vx * dt; p.y += p.vy * dt; p.vy += 2 * dt;
        ctx.fillStyle = "#ffffff";
        ctx.beginPath(); ctx.arc(sx(p.x), sy(p.y), z * 0.08 * (1 + age), 0, Math.PI * 2); ctx.fill();
      } else {
        ctx.font = `bold ${Math.round(14 * dpr())}px system-ui, sans-serif`;
        ctx.lineWidth = 3; ctx.strokeStyle = "#123"; ctx.fillStyle = "#fff";
        const y = sy(p.y) - age * 40 * dpr();
        ctx.strokeText(p.text, sx(p.x), y); ctx.fillText(p.text, sx(p.x), y);
      }
    }
    ctx.globalAlpha = 1;
    if (particles.length > 400) particles.splice(0, particles.length - 400);
  }

  function drawWeather(game, dt) {
    const blizzard = game.weather.kind === "blizzard";
    const n = blizzard ? snowfall.length : 50;
    if (blizzard) { ctx.fillStyle = "rgba(235,242,250,0.22)"; ctx.fillRect(0, 0, canvas.width, canvas.height); }
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    const wind = blizzard ? 0.5 : 0.04;
    for (let k = 0; k < n; k++) {
      const f = snowfall[k];
      f.x = (f.x + wind * f.s * dt + 1) % 1; f.y = (f.y + (blizzard ? 0.35 : 0.06) * f.s * dt) % 1;
      const size = (blizzard ? 2.5 : 2) * f.s * dpr();
      ctx.fillRect(f.x * canvas.width, f.y * canvas.height, size, size);
    }
  }

  function arrow(tx, ty, icon, color) {
    const x = sx(tx), y = sy(ty), m = 50 * dpr();
    if (x > m && y > m && x < canvas.width - m && y < canvas.height - m) return;
    const cx = canvas.width / 2, cy = canvas.height / 2, a = Math.atan2(y - cy, x - cx);
    const k = Math.min((canvas.width / 2 - m) / Math.abs(Math.cos(a) || 1e-6), (canvas.height / 2 - m) / Math.abs(Math.sin(a) || 1e-6));
    const ax = cx + Math.cos(a) * k, ay = cy + Math.sin(a) * k;
    ctx.save(); ctx.translate(ax, ay); ctx.rotate(a);
    ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(22 * dpr(), 0); ctx.lineTo(6 * dpr(), -9 * dpr()); ctx.lineTo(6 * dpr(), 9 * dpr()); ctx.fill();
    ctx.restore();
    emoji(icon, ax - Math.cos(a) * 8 * dpr(), ay - Math.sin(a) * 8 * dpr(), 22 * dpr());
  }

  function drawOverlays(game, state, now) {
    if (game.flake) arrow(game.flake.x + 0.5, game.flake.y + 0.5, "✨", "#ffd700");
    arrow(game.cabin[0] + 0.5, game.cabin[1] + 0.5, "🏠", "#ff9a3c");
    const me = game.players[state.you];
    if (me && me.warmth < 35) {
      const a = (35 - me.warmth) / 35;
      const g = ctx.createRadialGradient(canvas.width / 2, canvas.height / 2, Math.min(canvas.width, canvas.height) * 0.3,
        canvas.width / 2, canvas.height / 2, Math.max(canvas.width, canvas.height) * 0.7);
      g.addColorStop(0, "rgba(150,200,255,0)"); g.addColorStop(1, `rgba(170,215,255,${0.75 * a + 0.1 * a * Math.sin(now / 300)})`);
      ctx.fillStyle = g; ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
  }

  function draw(now) {
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    const state = lobby.state;
    if (!state || state.phase === "lobby" || !state.game || $("game").hidden) return;
    const game = state.game;
    SB.grid.update(game);
    if (!SB.grid.image) return;
    SB.input.frame(dt);
    const rect = canvas.getBoundingClientRect();
    const cw = Math.round(rect.width * dpr()), ch = Math.round(rect.height * dpr());
    if (canvas.width !== cw || canvas.height !== ch) { canvas.width = cw; canvas.height = ch; }

    let focus = SB.input.me;
    if (!focus) {
      const others = rt.sample((g) => (g && g.players) || {});
      const pid = view.spectate && others[view.spectate] ? view.spectate : Object.keys(others)[0];
      focus = pid ? others[pid] : { x: game.cabin[0] + 0.5, y: game.cabin[1] + 0.5 };
    }
    cam.x = focus.x; cam.y = focus.y;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = "#1b232c"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    drawLots(game, now);
    drawLandmarks(game);
    drawHeat(game, now);
    if (Array.isArray(game.rally)) emoji("🚩", sx(game.rally[0] + 0.5), sy(game.rally[1] + 0.3), Z() * 0.9);
    if (game.flake) {
      const fx = sx(game.flake.x + 0.5), fy = sy(game.flake.y + 0.5), r = Z() * (0.9 + 0.15 * Math.sin(now / 150));
      const glow = ctx.createRadialGradient(fx, fy, 0, fx, fy, r * 1.8);
      glow.addColorStop(0, "rgba(255,215,0,0.9)"); glow.addColorStop(1, "rgba(255,215,0,0)");
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(fx, fy, r * 1.8, 0, Math.PI * 2); ctx.fill();
      emoji("❄️", fx, fy, r * 1.4);
    }
    drawUnits(game, now);
    drawBeams(game);
    drawPlayers(game, now, state);
    drawAim(state);
    drawParticles(now, dt);
    drawWeather(game, dt);
    drawOverlays(game, state, now);
  }

  view.drawMinimap = (mini) => {
    const state = lobby.state, game = state && state.game;
    if (!game || !SB.grid.image) return;
    const c = mini.getContext("2d"), size = mini.width, k = size / Math.max(game.w, game.h);
    c.imageSmoothingEnabled = true;
    c.fillStyle = "#1b232c"; c.fillRect(0, 0, size, size);
    c.drawImage(SB.grid.image, 0, 0, game.w * k, game.h * k);
    const dot = (x, y, r, color) => { c.fillStyle = color; c.beginPath(); c.arc(x * k, y * k, r, 0, Math.PI * 2); c.fill(); };
    dot(game.cabin[0] + 0.5, game.cabin[1] + 0.5, 4, "#ff9a3c");
    for (const [hx, hy] of Object.values(game.huts)) dot(hx + 0.5, hy + 0.5, 2.5, "#ffb070");
    for (const [dx, dy] of Object.values(game.depots || {})) dot(dx + 0.5, dy + 0.5, 2.5, "#7fd3ff");
    for (const [mx, my] of Object.values(game.markets || {})) dot(mx + 0.5, my + 0.5, 3.5, "#ffd54f");
    for (const lm of Object.values(game.landmarks || {})) dot(lm.x + lm.size / 2, lm.y + lm.size / 2, 3, lm.found ? "#ffd700" : "#c0a0ff");
    if (game.flake) dot(game.flake.x + 0.5, game.flake.y + 0.5, 4, "#ffd700");
    if (Array.isArray(game.rally)) dot(game.rally[0] + 0.5, game.rally[1] + 0.5, 3, "#ff3b3b");
    for (const [pid, p] of Object.entries(game.players)) {
      const pos = pid === state.you && SB.input.me ? SB.input.me : p;
      c.strokeStyle = "#fff"; c.lineWidth = 1.5;
      dot(pos.x, pos.y, pid === state.you ? 4 : 3, p.color); c.stroke();
    }
    const z = Z();
    c.strokeStyle = "rgba(255,255,255,0.8)"; c.lineWidth = 1;
    c.strokeRect((cam.x - canvas.width / 2 / z) * k, (cam.y - canvas.height / 2 / z) * k, (canvas.width / z) * k, (canvas.height / z) * k);
  };

  view.init = (lobbyRef, rtRef) => {
    lobby = lobbyRef; rt = rtRef;
    canvas = $("map"); ctx = canvas.getContext("2d");
    AppRealtime.loop(draw);
  };
})();
