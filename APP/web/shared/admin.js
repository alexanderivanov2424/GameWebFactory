/*
 * Admin view component (view only).
 *
 * Not included by pages: settings.js loads it once the "Enable Admin Mode" setting (Settings ->
 * Settings) holds a password. It keeps a /ws/admin socket open (server/admin.py), sends that
 * password to be checked on the server, and while it's accepted shows an "Admin view" button
 * below the settings gear. The button opens a dialog with four read-only tabs:
 *   Accounts  every account; click one to see its saved data (never its password)
 *   Feedback  feedback files grouped by game; click one to read it
 *   Sessions  every server session (guest or account), its connections and rooms; click for details
 *   Rooms     every active room: game, phase, host, settings, and who is in it
 * Client UUIDs only ever arrive shortened (the server cuts them), since a full one is a seat key.
 *
 * Reports its status to settings.js with a document "app-admin" event, detail {status}:
 * "checking", "on", "wrong" or "offline". Clearing the setting turns it all off.
 * Styles live in a shadow root, like the other shared components.
 */
(() => {
  if (window.AppAdmin) return;
  const KEY = "adminPassword"; // settings.js ADMIN_KEY

  // --- Connection -----------------------------------------------------------

  const state = {
    socket: null,
    status: "",
    retries: 0,
    retryTimer: null,
    handlers: {}, // request "what" -> callback(reply) for the latest request of that kind
  };

  function setStatus(status) {
    state.status = status;
    document.dispatchEvent(new CustomEvent("app-admin", { detail: { status } }));
    if (element) element.draw();
  }

  function password() {
    return AppSettings.get(KEY) || "";
  }

  function connect() {
    clearTimeout(state.retryTimer);
    if (!password() || state.socket) return;
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    let socket;
    try {
      socket = new WebSocket(`${protocol}//${location.host}/ws/admin?client=${encodeURIComponent(AppSettings.clientId)}`);
    } catch {
      setStatus("offline");
      return;
    }
    state.socket = socket;
    setStatus("checking");
    socket.addEventListener("open", () => {
      state.retries = 0;
      sendAuth();
    });
    socket.addEventListener("message", (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      if (data.type === "auth") {
        if (password()) setStatus(data.ok ? "on" : "wrong");
      } else if (data.type === "data" || data.type === "error") {
        const handler = state.handlers[data.what];
        if (handler) handler(data);
      }
    });
    socket.addEventListener("close", (event) => {
      if (state.socket === socket) state.socket = null;
      if (!password()) return;
      setStatus("offline");
      if (event.code === 1008) return;
      const delay = Math.min(1000 * 2 ** state.retries, 15000);
      state.retries++;
      state.retryTimer = setTimeout(connect, delay);
    });
  }

  function sendAuth() {
    if (state.socket?.readyState !== WebSocket.OPEN) return;
    setStatus("checking");
    state.socket.send(JSON.stringify({ type: "auth", password: password() }));
  }

  function request(what, extra, callback) {
    state.handlers[what] = callback;
    if (state.socket?.readyState !== WebSocket.OPEN || state.status !== "on") {
      callback({ type: "error", message: "Not connected to the server." });
      return;
    }
    state.socket.send(JSON.stringify({ type: "get", what, ...extra }));
  }

  AppSettings.onChange((key) => {
    if (key !== KEY) return;
    if (!password()) {
      clearTimeout(state.retryTimer);
      const socket = state.socket;
      state.socket = null;
      socket?.close();
      setStatus("");
    } else if (state.socket) {
      sendAuth();
    } else {
      connect();
    }
  });

  // --- Helpers --------------------------------------------------------------

  function make(tag, props = {}, ...children) {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children.filter((c) => c !== null && c !== undefined).map((c) => (typeof c === "object" ? c : String(c))));
    return node;
  }

  function when(seconds) {
    return seconds ? new Date(seconds * 1000).toLocaleString() : "—";
  }

  function bytes(n) {
    return n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`;
  }

  function yes(flag) {
    return flag ? "yes" : "";
  }

  function json(value) {
    return make("pre", { className: "json" }, JSON.stringify(value, null, 2));
  }

  function table(headers, rows, onPick) {
    const body = make("tbody");
    rows.forEach(({ cells, key }) => {
      const tr = make("tr", {}, ...cells.map((c) => make("td", {}, c ?? "")));
      if (onPick) {
        tr.className = "pick";
        tr.addEventListener("click", () => {
          body.querySelectorAll("tr").forEach((r) => r.classList.toggle("selected", r === tr));
          onPick(key);
        });
      }
      body.append(tr);
    });
    return make("div", { className: "table-wrap" }, make("table", {}, make("thead", {}, make("tr", {}, ...headers.map((h) => make("th", {}, h)))), body));
  }

  function message(text, isError) {
    return make("p", { className: isError ? "error" : "muted" }, text);
  }

  // Each tab: load(list, detail) fills the list pane (and resets the detail pane).
  const TABS = [
    {
      id: "accounts",
      label: "Accounts",
      load(list, detail) {
        request("accounts", {}, (reply) => {
          if (reply.type === "error") return list.replaceChildren(message(reply.message, true));
          if (!reply.data.length) return list.replaceChildren(message("No accounts yet."));
          list.replaceChildren(
            make("p", { className: "muted" }, `${reply.data.length} account(s). Click one to see its saved data.`),
            table(
              ["Name", "Display name", "Created", "Games with data", "Data", "Logged-in tabs"],
              reply.data.map((a) => ({
                key: a.name,
                cells: [a.name, a.displayName ?? "", when(a.created), a.games.join(", "), bytes(a.bytes), a.sessions || ""],
              })),
              (name) => {
                detail.replaceChildren(message("Loading..."));
                request("account", { name }, (r) => {
                  if (r.type === "error") return detail.replaceChildren(message(r.message, true));
                  if (r.name !== name) return;
                  detail.replaceChildren(make("h3", {}, r.data.name), json(r.data));
                });
              }
            )
          );
        });
      },
    },
    {
      id: "feedback",
      label: "Feedback",
      load(list, detail) {
        request("feedback", {}, (reply) => {
          if (reply.type === "error") return list.replaceChildren(message(reply.message, true));
          const games = Object.keys(reply.data);
          if (!games.length) return list.replaceChildren(message("No feedback."));
          const groups = games.map((game) => {
            const files = reply.data[game];
            const entries = files.reduce((n, f) => n + f.entries, 0);
            return make(
              "details",
              { className: "group", open: true },
              make("summary", {}, make("strong", {}, game), ` — ${files.length} player(s), ${entries} entr${entries === 1 ? "y" : "ies"}`),
              table(
                ["Name", "Session", "Entries", "Size", "Last sent"],
                files.map((f) => ({ key: f.file, cells: [f.name, f.client, f.entries, bytes(f.bytes), when(f.modified)] })),
                (file) => {
                  detail.replaceChildren(message("Loading..."));
                  request("feedbackFile", { game, file }, (r) => {
                    if (r.type === "error") return detail.replaceChildren(message(r.message, true));
                    if (r.file !== file) return;
                    detail.replaceChildren(make("h3", {}, `${game} / ${file}`), make("pre", { className: "text" }, r.data));
                  });
                }
              )
            );
          });
          list.replaceChildren(make("p", { className: "muted" }, "Click a file to read it."), ...groups);
        });
      },
    },
    {
      id: "sessions",
      label: "Sessions",
      load(list, detail) {
        request("sessions", {}, (reply) => {
          if (reply.type === "error") return list.replaceChildren(message(reply.message, true));
          if (!reply.data.length) return list.replaceChildren(message("No sessions."));
          list.replaceChildren(
            make("p", { className: "muted" }, `${reply.data.length} session(s) (one per browser tab). Click one for details.`),
            table(
              ["Session", "Account", "Connections", "Rooms", "Playing", "Guest data", "Ending soon"],
              reply.data.map((s) => ({
                key: s.id,
                cells: [s.id, s.account ?? "guest", s.connections, s.rooms.join(", "), yes(s.playing), s.guestGames.join(", "), yes(s.ending)],
              })),
              (id) => {
                detail.replaceChildren(message("Loading..."));
                request("session", { id }, (r) => {
                  if (r.type === "error") return detail.replaceChildren(message(r.message, true));
                  if (r.id !== id) return;
                  detail.replaceChildren(make("h3", {}, `Session ${id}`), json(r.data));
                });
              }
            )
          );
        });
      },
    },
    {
      id: "rooms",
      label: "Rooms",
      load(list, detail) {
        detail.hidden = true;
        request("rooms", {}, (reply) => {
          if (reply.type === "error") return list.replaceChildren(message(reply.message, true));
          if (!reply.data.length) return list.replaceChildren(message("No active rooms."));
          list.replaceChildren(
            ...reply.data.map((room) => {
              const players = room.members.filter((m) => m.playing).length;
              const facts = [room.phase, room.gameNumber ? `game #${room.gameNumber}` : null, `${players} player(s)`, `${room.members.length - players} spectator(s)`];
              return make(
                "section",
                { className: "room" },
                make("h3", {}, `${room.game} / ${room.room}`, make("span", { className: "muted" }, ` — ${facts.filter(Boolean).join(", ")}`)),
                room.settings && Object.keys(room.settings).length
                  ? make("p", { className: "muted small" }, "Settings: " + Object.entries(room.settings).map(([k, v]) => `${k} = ${JSON.stringify(v)}`).join(", "))
                  : null,
                table(
                  ["Id", "Name", "Role", "Ready", "Host", "Online", "Account", "Session"],
                  room.members.map((m) => ({
                    cells: [m.id ?? "", m.name ?? "", m.id === undefined ? "" : m.playing ? "player" : "spectator", yes(m.ready), yes(m.host), m.online ? "yes" : "offline", m.account ?? "guest", m.session],
                  }))
                )
              );
            })
          );
        });
      },
    },
  ];

  // --- UI -------------------------------------------------------------------

  const STYLE = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }
    .root { font: 15px/1.4 system-ui, sans-serif; color: #222; }
    button { font: inherit; cursor: pointer; border: none; border-radius: 6px; }
    .icon-btn { background: transparent; color: #444; padding: 6px; line-height: 0; }
    .icon-btn:hover { background: rgba(0, 0, 0, 0.07); }
    .open-btn { position: fixed; top: 60px; right: 16px; z-index: 2147483000; color: #b00020; }
    .open-btn svg { width: 28px; height: 28px; }
    .backdrop {
      position: fixed; inset: 0; z-index: 2147483001; background: rgba(0, 0, 0, 0.45);
      display: flex; align-items: center; justify-content: center;
    }
    .modal {
      width: 90vw; height: 88vh; background: #fff; border-radius: 10px;
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25); display: flex; flex-direction: column; overflow: hidden;
    }
    .header { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid #e4e4ec; }
    .header h2 { margin: 0; font-size: 1.25rem; flex: 1; }
    .header .badge { font-size: 0.8rem; color: #b00020; font-weight: 600; }
    .body { flex: 1; display: flex; min-height: 0; }
    .tabs { width: 150px; padding: 8px; border-right: 1px solid #e4e4ec; display: flex; flex-direction: column; gap: 4px; }
    .tab { background: transparent; color: #333; text-align: left; padding: 8px 12px; }
    .tab:hover { background: #eef0ff; }
    .tab[aria-selected="true"] { background: #4a5cff; color: #fff; }
    .content { flex: 1; display: flex; flex-direction: column; min-width: 0; }
    .toolbar { padding: 10px 16px; border-bottom: 1px solid #e4e4ec; display: flex; gap: 8px; align-items: center; }
    .secondary { background: #e8e9f3; color: #222; padding: 6px 12px; }
    .secondary:hover { background: #d8daea; }
    .panes { flex: 1; display: flex; min-height: 0; }
    .list { flex: 3; overflow: auto; padding: 12px 16px; }
    .detail { flex: 2; overflow: auto; padding: 12px 16px; border-left: 1px solid #e4e4ec; background: #fafafd; }
    .muted { color: #666; margin: 0 0 10px; }
    .small { font-size: 0.85rem; }
    .error { color: #b00020; margin: 0 0 10px; }
    h3 { margin: 0 0 8px; font-size: 1rem; }
    .table-wrap { overflow-x: auto; margin-bottom: 12px; }
    table { border-collapse: collapse; width: 100%; font-size: 0.88rem; }
    th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid #ececf2; white-space: nowrap; }
    th { background: #f4f4f8; font-weight: 600; }
    tr.pick { cursor: pointer; }
    tr.pick:hover td { background: #eef0ff; }
    tr.selected td { background: #dfe3ff; }
    .group { margin-bottom: 12px; }
    .group summary { cursor: pointer; margin-bottom: 6px; }
    .room { border: 1px solid #e4e4ec; border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; }
    pre { margin: 0; font: 0.82rem/1.45 ui-monospace, monospace; }
    pre.text { white-space: pre-wrap; word-break: break-word; font: 0.9rem/1.5 system-ui, sans-serif; }
  `;

  // A simple eye: "view only".
  const EYE_ICON = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>
    </svg>`;

  const CLOSE_ICON = `
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18"/>
    </svg>`;

  let element = null;

  class AppAdminElement extends HTMLElement {
    connectedCallback() {
      if (this.shadowRoot) return;
      const root = this.attachShadow({ mode: "open" });
      root.innerHTML = `
        <style>${STYLE}</style>
        <div class="root">
          <button class="icon-btn open-btn" aria-label="Admin view" title="Admin view" hidden>${EYE_ICON}</button>
          <div class="backdrop" hidden>
            <div class="modal" role="dialog" aria-modal="true" aria-labelledby="admin-title">
              <div class="header">
                <h2 id="admin-title">Admin view</h2>
                <span class="badge">View only</span>
                <button class="icon-btn close-btn" aria-label="Close admin view" title="Close">${CLOSE_ICON}</button>
              </div>
              <div class="body">
                <nav class="tabs" role="tablist"></nav>
                <div class="content">
                  <div class="toolbar"><button class="secondary refresh">Refresh</button><span class="muted small updated"></span></div>
                  <div class="panes"><div class="list"></div><div class="detail"></div></div>
                </div>
              </div>
            </div>
          </div>
        </div>`;
      this.openBtn = root.querySelector(".open-btn");
      this.backdrop = root.querySelector(".backdrop");
      this.list = root.querySelector(".list");
      this.detail = root.querySelector(".detail");
      this.updated = root.querySelector(".updated");
      const tabList = root.querySelector(".tabs");
      this.tabButtons = TABS.map((tab) => {
        const button = make("button", { className: "tab" }, tab.label);
        button.setAttribute("role", "tab");
        button.addEventListener("click", () => this.select(tab));
        tabList.append(button);
        return button;
      });
      this.tab = TABS[0];

      this.openBtn.addEventListener("click", () => this.open());
      root.querySelector(".close-btn").addEventListener("click", () => this.close());
      root.querySelector(".refresh").addEventListener("click", () => this.select(this.tab));
      this.backdrop.addEventListener("click", (e) => e.target === this.backdrop && this.close());
      // Keys stay in the dialog (game pages listen on document), as in settings.js.
      ["keydown", "keyup", "keypress"].forEach((type) =>
        this.backdrop.addEventListener(type, (e) => {
          if (type === "keydown" && e.key === "Escape") this.close();
          e.stopPropagation();
        })
      );
      this.draw();
    }

    draw() {
      const on = state.status === "on";
      this.openBtn.hidden = !on;
      if (!on && !this.backdrop.hidden) this.close();
    }

    select(tab) {
      this.tab = tab;
      this.tabButtons.forEach((b, i) => b.setAttribute("aria-selected", TABS[i] === tab));
      this.list.replaceChildren(message("Loading..."));
      this.detail.hidden = false;
      this.detail.replaceChildren(message("Select a row to see details."));
      this.updated.textContent = "Updated " + new Date().toLocaleTimeString();
      tab.load(this.list, this.detail);
    }

    open() {
      this.backdrop.hidden = false;
      this.select(this.tab);
    }

    close() {
      this.backdrop.hidden = true;
    }
  }

  customElements.define("app-admin", AppAdminElement);
  element = document.createElement("app-admin");
  document.body.append(element);
  window.AppAdmin = { status: () => state.status };
  connect();
})();
