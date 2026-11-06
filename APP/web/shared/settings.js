/*
 * Settings component.
 *
 * Self-contained: adds a gear button (top right) and a settings dialog to the page.
 * Styles live in a shadow root, so page CSS can't break it and it can't affect the page.
 *
 * Settings are kept in sessionStorage only: they stay in this browser tab and are
 * never sent anywhere.
 *
 * API for other components:
 *   AppSettings.get(key)
 *   AppSettings.set(key, value)
 *   AppSettings.onChange((key, value) => { ... })   // returns an unsubscribe function
 *
 * To add a setting, add a field to TABS. To add a tab, add an entry to TABS.
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
          hint: "Shown next to your chat messages.",
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

  window.AppSettings = {
    clientId,
    get: (key) => values[key],
    set(key, value) {
      if (values[key] === value) return;
      values[key] = value;
      write();
      events.dispatchEvent(new CustomEvent("change", { detail: { key, value } }));
    },
    onChange(callback) {
      const listener = (e) => callback(e.detail.key, e.detail.value);
      events.addEventListener("change", listener);
      return () => events.removeEventListener("change", listener);
    },
  };

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

      this.openBtn.addEventListener("click", () => this.open());
      root.querySelector(".close-btn").addEventListener("click", () => this.close());
      this.backdrop.addEventListener("click", (e) => {
        if (e.target === this.backdrop) this.close();
      });
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !this.backdrop.hidden) this.close();
      });
    }

    buildTabs(tabList, panelContainer) {
      this.inputs = [];
      TABS.forEach((tab, index) => {
        const button = document.createElement("button");
        button.className = "tab";
        button.setAttribute("role", "tab");
        button.textContent = tab.label;

        const panel = document.createElement("section");
        panel.className = "panel";
        panel.setAttribute("role", "tabpanel");

        tab.fields.forEach((field) => panel.append(this.buildField(field)));

        button.addEventListener("click", () => this.selectTab(button, panel));
        tabList.append(button);
        panelContainer.append(panel);
        if (index === 0) this.selectTab(button, panel);
      });
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
