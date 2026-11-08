/*
 * Settings component.
 *
 * Self-contained: adds a gear button (top right) and a settings dialog to the page.
 * Styles live in a shadow root, so page CSS can't break it and it can't affect the page.
 *
 * Settings are kept in sessionStorage only: they stay in this browser tab and are
 * never sent anywhere.
 *
 * Account tab: every tab is a guest until it logs in (or creates an account) here. This
 * component keeps one /ws/account socket open on every page (server/sessions.py), which keeps
 * the tab's server session alive; the session is tied to the tab's UUID, so game rooms know
 * the account without the page doing anything. The account name and password are sent to the
 * server only when you press Log in / Create account. Logging in or out is refused while you
 * are playing a game. A server restart (deploy) logs everyone out.
 *
 * API for other components:
 *   AppSettings.get(key)
 *   AppSettings.set(key, value)
 *   AppSettings.onChange((key, value) => { ... })   // returns an unsubscribe function
 *   AppSettings.account()   // logged-in account name, or null for a guest
 *                           // (changes fire onChange("account", name))
 *
 * While logged in, the user name (display name) is saved to the account whenever it changes
 * (debounced), and logging in switches to the name saved there (a new account takes the
 * current one).
 *
 * Feedback tab: a text box sent to the server (server/feedback.py), which saves it as a text file
 * per game and player. It shows the display name and a game picker (starts on the page's game,
 * or "Site" off a game page); the "New game" checkbox (ticked by default off a game page) files it
 * under new_game instead.
 *
 * To add a setting, add a field to TABS. To add a tab, add an entry to TABS: either `fields`
 * (text inputs) or `render(panel)` (builds its own content).
 */
(() => {
  const STORAGE_KEY = "app.settings";

  const TABS = [
    {
      id: "user",
      label: "User",
      fields: [
        {
          key: "username",
          label: "User name",
          maxLength: 32,
          hint: "Shown next to your chat messages. Saved to your account while you're logged in.",
        },
        {
          key: "uuid",
          label: "UUID",
          readOnly: true,
          value: () => clientId,
          hint: "Identifies you in game rooms. Unique to this browser tab.",
        },
      ],
    },
    {
      id: "account",
      label: "Account",
      render: (panel) => renderAccount(panel),
    },
    {
      id: "feedback",
      label: "Feedback",
      render: (panel) => renderFeedback(panel),
    },
  ];

  // --- Player id -----------------------------------------------------------
  // Random UUID for this browser tab, shared with room.js through sessionStorage
  // (same key and format there). Not a setting: it is never edited.

  const CLIENT_ID_KEY = "app.clientId";
  const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

  function newUuid() {
    // crypto.getRandomValues works over plain HTTP (crypto.randomUUID does not).
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40; // version 4
    b[8] = (b[8] & 0x3f) | 0x80; // variant
    const hex = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function loadClientId() {
    try {
      const saved = sessionStorage.getItem(CLIENT_ID_KEY);
      if (UUID_PATTERN.test(saved)) return saved;
    } catch {}
    const id = newUuid();
    try {
      sessionStorage.setItem(CLIENT_ID_KEY, id);
    } catch {}
    return id;
  }

  const clientId = loadClientId();

  // --- Store ---------------------------------------------------------------

  const events = new EventTarget();
  const values = read();
  if (!values.username) {
    values.username = "Guest-" + Math.floor(1000 + Math.random() * 9000);
    write();
  }

  function read() {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY)) || {};
    } catch {
      return {};
    }
  }

  function write() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(values));
    } catch {
      // Storage unavailable (e.g. blocked); settings still work until the page closes.
    }
  }

  function emit(key, value) {
    events.dispatchEvent(new CustomEvent("change", { detail: { key, value } }));
  }

  window.AppSettings = {
    clientId,
    get: (key) => values[key],
    set(key, value) {
      if (values[key] === value) return;
      values[key] = value;
      write();
      emit(key, value);
    },
    account: () => account.user,
    onChange(callback) {
      const listener = (e) => callback(e.detail.key, e.detail.value);
      events.addEventListener("change", listener);
      return () => events.removeEventListener("change", listener);
    },
  };

  function socketUrl(path) {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${location.host}${path}?client=${encodeURIComponent(clientId)}`;
  }

  function make(tag, props = {}, text) {
    const node = Object.assign(document.createElement(tag), props);
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // --- Account -------------------------------------------------------------
  // The server decides who this tab is (guest or account); this only mirrors it.

  const account = {
    user: null, // account name, or null for a guest
    online: false,
    error: "",
    busy: false, // a request is waiting for its answer
    socket: null,
    retries: 0,
    savedName: null, // display name the account has saved, as far as this tab knows
    nameTimer: null,
    listeners: new Set(), // redraw functions of open Account panels
  };

  // Display name: saved to the account while logged in (see sessions.py). Debounced, since the
  // field sends a change per keystroke and the server limits how often anything is saved.
  const NAME_SAVE_DELAY = 1500;

  function saveNameSoon() {
    clearTimeout(account.nameTimer);
    account.nameTimer = setTimeout(() => {
      const name = values.username;
      if (!account.user || !name || name === account.savedName) return;
      if (account.socket?.readyState !== WebSocket.OPEN) return;
      account.socket.send(JSON.stringify({ type: "name", name }));
      account.savedName = name;
    }, NAME_SAVE_DELAY);
  }

  events.addEventListener("change", (e) => {
    if (e.detail.key === "username") saveNameSoon();
  });

  function accountChanged() {
    account.listeners.forEach((fn) => fn());
  }

  function connectAccount() {
    let socket;
    try {
      socket = new WebSocket(socketUrl("/ws/account"));
    } catch {
      return;
    }
    account.socket = socket;
    socket.addEventListener("open", () => {
      account.retries = 0;
      account.online = true;
      accountChanged();
    });
    socket.addEventListener("message", (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      if (data.type === "account") {
        const user = typeof data.user === "string" ? data.user : null;
        const changed = user !== account.user;
        account.user = user;
        account.savedName = user && typeof data.displayName === "string" ? data.displayName : null;
        account.busy = false;
        account.error = "";
        if (changed && user) {
          // Just logged in: use the account's saved name, or give a new account this tab's name.
          if (account.savedName) AppSettings.set("username", account.savedName);
          else saveNameSoon();
        }
        accountChanged();
        if (changed) emit("account", user);
      } else if (data.type === "error") {
        account.busy = false;
        account.error = String(data.message || "Request refused.");
        accountChanged();
      }
    });
    socket.addEventListener("close", (event) => {
      account.online = false;
      account.busy = false;
      accountChanged();
      if (event.code === 1008) return; // invalid client id: retrying won't help
      const delay = Math.min(1000 * 2 ** account.retries, 15000);
      account.retries++;
      setTimeout(connectAccount, delay);
    });
  }

  function sendAccount(data) {
    if (!account.socket || account.socket.readyState !== WebSocket.OPEN) {
      account.error = "Not connected to the server.";
      accountChanged();
      return;
    }
    account.busy = true;
    account.error = "";
    account.socket.send(JSON.stringify(data));
    accountChanged();
  }

  connectAccount();

  function renderAccount(panel) {
    const status = make("p", { className: "status" });

    const form = make("form", { className: "account-form" });
    const nameInput = make("input", { id: "account-name", maxLength: 20, autocomplete: "username", spellcheck: false });
    const passInput = make("input", {
      id: "account-password",
      type: "password",
      maxLength: 128,
      autocomplete: "current-password",
    });
    const loginBtn = make("button", { type: "submit", className: "primary" }, "Log in");
    const registerBtn = make("button", { type: "button", className: "secondary" }, "Create account");
    const nameField = make("div", { className: "field" });
    nameField.append(make("label", { htmlFor: "account-name" }, "Account name"), nameInput);
    const passField = make("div", { className: "field" });
    passField.append(make("label", { htmlFor: "account-password" }, "Password"), passInput);
    const buttons = make("div", { className: "buttons" });
    buttons.append(loginBtn, registerBtn);
    form.append(nameField, passField, buttons);

    const logoutBtn = make("button", { type: "button", className: "secondary" }, "Log out");
    const error = make("p", { className: "error", role: "alert" });
    const hint = make("div", { className: "disclaimer" });
    hint.append(
      make("p", { className: "hint" }, "An account keeps your saved game data across sessions."),
      make(
        "p",
        { className: "hint warning" },
        "Passwords are saved as plain text. Don't use a real or secure password."
      )
    );

    const credentials = () => ({ name: nameInput.value.trim(), password: passInput.value });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      sendAccount({ type: "login", ...credentials() });
    });
    registerBtn.addEventListener("click", () => sendAccount({ type: "register", ...credentials() }));
    logoutBtn.addEventListener("click", () => sendAccount({ type: "logout" }));

    let shownUser;
    function draw() {
      const user = account.user;
      if (user !== shownUser) {
        passInput.value = ""; // never keep a password around after a change
        shownUser = user;
      }
      status.replaceChildren();
      if (!account.online) {
        status.textContent = "Connecting to the server...";
      } else if (user) {
        status.append("Logged in as ", make("strong", {}, user), ".");
      } else {
        status.textContent = "You're playing as a guest.";
      }
      form.hidden = !!user;
      logoutBtn.hidden = !user;
      const disabled = !account.online || account.busy;
      [loginBtn, registerBtn, logoutBtn].forEach((b) => (b.disabled = disabled));
      error.textContent = account.error;
      error.hidden = !account.error;
    }

    account.listeners.add(draw);
    draw();
    panel.append(status, form, logoutBtn, error, hint);
  }

  // --- Feedback ----------------------------------------------------------
  // One short-lived /ws/feedback socket per submission (server/feedback.py). The server turtles
  // the site on text over its limit, so the size is checked here first. The game picker lists
  // /games.json (as the home page does) and starts on the current page's game.

  const FEEDBACK_MAX_BYTES = 50 * 1024; // server/feedback.py MAX_BYTES
  const SITE = { id: "site", name: "Site (no game)" }; // server/feedback.py SITE
  const NEW_GAME = "new_game"; // server/feedback.py NEW_GAME
  const [, section, pageGame] = location.pathname.split("/"); // game pages: /games/<id>/
  const currentGame = section === "games" && pageGame ? pageGame : SITE.id;

  function sendFeedback(game, text, done) {
    let socket;
    let answer = null;
    try {
      socket = new WebSocket(socketUrl("/ws/feedback"));
    } catch {
      done("Couldn't reach the server.");
      return;
    }
    socket.addEventListener("open", () => {
      socket.send(JSON.stringify({ type: "feedback", game, name: values.username, text }));
    });
    socket.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data);
        answer = data.ok ? "" : String(data.message || "Feedback refused.");
      } catch {}
    });
    socket.addEventListener("close", () => done(answer ?? "Couldn't reach the server."));
  }

  function renderFeedback(panel) {
    const name = make("p", { className: "status" });
    const gameSelect = make("select", { id: "feedback-game" });
    const newGame = make("input", { type: "checkbox", checked: currentGame === SITE.id }); // off a game page
    const newGameLabel = make("label", { className: "check" });
    newGameLabel.append(newGame, "New game");
    const pick = make("div", { className: "feedback-pick" });
    pick.append(make("label", { htmlFor: "feedback-game" }, "Game"), gameSelect, newGameLabel);
    const text = make("textarea", { className: "feedback-text", spellcheck: true });
    const submit = make("button", { type: "button", className: "primary" }, "Submit");
    const result = make("p", { className: "hint" });

    const drawName = () => name.replaceChildren("Name: ", make("strong", {}, values.username));
    AppSettings.onChange((key) => key === "username" && drawName());
    drawName();

    function setGames(games) {
      const keep = gameSelect.value || currentGame;
      gameSelect.replaceChildren(...[SITE, ...games].map((g) => make("option", { value: g.id }, g.name)));
      gameSelect.value = keep;
      if (!gameSelect.value) gameSelect.value = SITE.id;
    }
    setGames(currentGame === SITE.id ? [] : [{ id: currentGame, name: document.title }]);
    fetch("/games.json", { cache: "no-cache" })
      .then((response) => (response.ok ? response.json() : []))
      .then((games) => {
        if (!Array.isArray(games)) return;
        setGames(games.filter((g) => g && typeof g.id === "string").map((g) => ({ id: g.id, name: String(g.name || g.id) })));
      })
      .catch(() => {}); // keeps the current game and Site

    gameSelect.disabled = newGame.checked;
    newGame.addEventListener("change", () => (gameSelect.disabled = newGame.checked));

    function show(message, isError) {
      result.textContent = message;
      result.className = isError ? "error" : "hint";
    }

    submit.addEventListener("click", () => {
      const body = text.value.trim();
      if (!body) return show("Write something first.", true);
      if (new TextEncoder().encode(body).length > FEEDBACK_MAX_BYTES) {
        return show("That's too long (50 KB at most).", true);
      }
      submit.disabled = true;
      show("Sending...");
      sendFeedback(newGame.checked ? NEW_GAME : gameSelect.value, body, (error) => {
        submit.disabled = false;
        if (error) return show(error, true);
        text.value = "";
        show("Thanks! Your feedback was sent.");
      });
    });

    panel.append(name, pick, text, submit, result);
  }

  // --- UI ------------------------------------------------------------------

  const STYLE = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }

    .root { font: 15px/1.4 system-ui, sans-serif; color: #222; }

    button { font: inherit; cursor: pointer; border: none; border-radius: 6px; }
    .icon-btn { background: transparent; color: #444; padding: 6px; line-height: 0; }
    .icon-btn:hover { background: rgba(0, 0, 0, 0.07); }

    .open-btn { position: fixed; top: 16px; right: 16px; z-index: 2147483000; }
    .open-btn svg { width: 28px; height: 28px; }

    .backdrop {
      position: fixed; inset: 0; z-index: 2147483001;
      background: rgba(0, 0, 0, 0.45);
      display: flex; align-items: center; justify-content: center;
    }
    .modal {
      width: 80vw; height: 80vh;
      background: #fff; border-radius: 10px;
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25);
      display: flex; flex-direction: column; overflow: hidden;
    }
    .header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 16px; border-bottom: 1px solid #e4e4ec;
    }
    .header h2 { margin: 0; font-size: 1.25rem; }
    .body { flex: 1; display: flex; min-height: 0; }

    .tabs {
      width: 160px; padding: 8px; border-right: 1px solid #e4e4ec;
      display: flex; flex-direction: column; gap: 4px;
    }
    .tab { background: transparent; color: #333; text-align: left; padding: 8px 12px; }
    .tab:hover { background: #eef0ff; }
    .tab[aria-selected="true"] { background: #4a5cff; color: #fff; }

    .panel { flex: 1; padding: 20px; overflow: auto; }
    .field { max-width: 360px; margin-bottom: 20px; }
    label { display: block; font-weight: 600; margin-bottom: 6px; }
    input {
      font: inherit; width: 100%; padding: 8px 10px;
      border: 1px solid #c8c8d4; border-radius: 6px;
    }
    input:focus { outline: 2px solid #4a5cff; outline-offset: -1px; }
    input.readonly { background: #f4f4f8; color: #555; font-family: ui-monospace, monospace; font-size: 0.85rem; }
    .hint { color: #666; font-size: 0.85rem; margin: 6px 0 0; }

    .status { margin: 0 0 20px; }
    .account-form { max-width: 360px; }
    .buttons { display: flex; gap: 8px; margin-bottom: 16px; }
    .primary { background: #4a5cff; color: #fff; padding: 8px 14px; }
    .primary:hover:not(:disabled) { background: #3343d6; }
    .secondary { background: #e8e9f3; color: #222; padding: 8px 14px; }
    .secondary:hover:not(:disabled) { background: #d8daea; }
    button:disabled { opacity: 0.55; cursor: default; }
    .error { color: #b00020; margin: 0 0 16px; }
    .disclaimer { max-width: 480px; }
    .feedback-text {
      display: block; width: 100%; height: 45vh; margin-bottom: 12px; padding: 8px 10px;
      font: inherit; resize: vertical; border: 1px solid #c8c8d4; border-radius: 6px;
    }
    .feedback-pick { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
    .feedback-pick label { margin: 0; }
    .feedback-pick select {
      font: inherit; min-width: 220px; padding: 6px 8px; border: 1px solid #c8c8d4; border-radius: 6px;
    }
    .feedback-pick .check { display: flex; align-items: center; gap: 6px; font-weight: normal; cursor: pointer; }
    .feedback-pick .check input { width: auto; margin: 0; }
    .feedback-text:focus { outline: 2px solid #4a5cff; outline-offset: -1px; }
    .hint.warning { color: #c62828; font-weight: 600; }

    @media (max-width: 600px) {
      .body { flex-direction: column; }
      .tabs { width: auto; flex-direction: row; border-right: none; border-bottom: 1px solid #e4e4ec; }
    }
  `;

  const GEAR_ICON = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>`;

  const CLOSE_ICON = `
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18"/>
    </svg>`;

  class AppSettingsElement extends HTMLElement {
    connectedCallback() {
      if (this.shadowRoot) return;
      const root = this.attachShadow({ mode: "open" });
      root.innerHTML = `
        <style>${STYLE}</style>
        <div class="root">
          <button class="icon-btn open-btn" aria-label="Settings" title="Settings">${GEAR_ICON}</button>
          <div class="backdrop" hidden>
            <div class="modal" role="dialog" aria-modal="true" aria-labelledby="title">
              <div class="header">
                <h2 id="title">Settings</h2>
                <button class="icon-btn close-btn" aria-label="Close settings" title="Close">${CLOSE_ICON}</button>
              </div>
              <div class="body">
                <nav class="tabs" role="tablist"></nav>
                <div class="panels"></div>
              </div>
            </div>
          </div>
        </div>`;

      this.openBtn = root.querySelector(".open-btn");
      this.backdrop = root.querySelector(".backdrop");
      this.buildTabs(root.querySelector(".tabs"), root.querySelector(".panels"));
      // Keep open inputs current when a value changes elsewhere (e.g. logging in restores the name).
      AppSettings.onChange((key, value) => {
        this.inputs.forEach(({ input, field }) => {
          if (field.key === key && root.activeElement !== input) input.value = value ?? "";
        });
      });

      this.openBtn.addEventListener("click", () => this.open());
      root.querySelector(".close-btn").addEventListener("click", () => this.close());
      this.backdrop.addEventListener("click", (e) => {
        if (e.target === this.backdrop) this.close();
      });
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !this.backdrop.hidden) this.close();
      });
      // Keys typed in the dialog stay in it: game pages listen on document/window, and the shadow
      // root hides that the key came from a text box (spaces and arrows would be swallowed).
      ["keydown", "keyup", "keypress"].forEach((type) =>
        this.backdrop.addEventListener(type, (e) => {
          if (type === "keydown" && e.key === "Escape") this.close();
          e.stopPropagation();
        })
      );
    }

    buildTabs(tabList, panelContainer) {
      this.inputs = [];
      let first = null;
      TABS.forEach((tab) => {
        const button = document.createElement("button");
        button.className = "tab";
        button.setAttribute("role", "tab");
        button.textContent = tab.label;

        const panel = document.createElement("section");
        panel.className = "panel";
        panel.setAttribute("role", "tabpanel");

        if (tab.render) tab.render(panel);
        else tab.fields.forEach((field) => panel.append(this.buildField(field)));

        button.addEventListener("click", () => this.selectTab(button, panel));
        tabList.append(button);
        panelContainer.append(panel);
        first ||= [button, panel];
      });
      // Select once every panel exists, so the others are all hidden.
      if (first) this.selectTab(...first);
    }

    buildField(field) {
      const id = "field-" + field.key;
      const wrapper = document.createElement("div");
      wrapper.className = "field";

      const label = document.createElement("label");
      label.htmlFor = id;
      label.textContent = field.label;

      const input = document.createElement("input");
      input.id = id;
      input.autocomplete = "off";
      input.spellcheck = false;
      if (field.maxLength) input.maxLength = field.maxLength;
      if (field.readOnly) {
        input.readOnly = true;
        input.className = "readonly";
      } else {
        input.addEventListener("input", () => {
          const value = input.value.trim();
          if (value) AppSettings.set(field.key, value);
        });
      }
      this.inputs.push({ input, field });

      wrapper.append(label, input);
      if (field.hint) {
        const hint = document.createElement("p");
        hint.className = "hint";
        hint.textContent = field.hint;
        wrapper.append(hint);
      }
      return wrapper;
    }

    selectTab(button, panel) {
      this.shadowRoot.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", t === button));
      this.shadowRoot.querySelectorAll(".panel").forEach((p) => (p.hidden = p !== panel));
    }

    open() {
      this.inputs.forEach(({ input, field }) => {
        input.value = (field.value ? field.value() : AppSettings.get(field.key)) ?? "";
      });
      this.backdrop.hidden = false;
      this.inputs[0]?.input.focus();
    }

    close() {
      this.backdrop.hidden = true;
      this.openBtn.focus();
    }
  }

  customElements.define("app-settings", AppSettingsElement);
  if (!document.querySelector("app-settings")) {
    document.body.append(document.createElement("app-settings"));
  }
})();
