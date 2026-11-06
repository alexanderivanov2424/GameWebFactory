/*
 * Chat component.
 *
 * Self-contained: adds a chat panel docked to the bottom right edge of the screen.
 * Collapsed, it is a small tab with an up chevron; opened, it rises from the bottom edge.
 * Styles live in a shadow root, so page CSS can't break it and it can't affect the page.
 *
 * Connects to the chat server at /ws/chat on the same host. Each message sends only
 * the display name and the text; no other settings leave the browser.
 * Reads the display name from AppSettings (settings.js) if it is loaded.
 */
(() => {
  const MAX_TEXT = 500;

  const STYLE = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }

    .root {
      position: fixed; right: 16px; bottom: 0; z-index: 2147482000;
      display: flex; flex-direction: column; align-items: flex-end;
      font: 15px/1.4 system-ui, sans-serif; color: #222;
    }

    button { font: inherit; cursor: pointer; border: none; border-radius: 6px; }
    .primary { background: #4a5cff; color: #fff; padding: 8px 14px; }
    .primary:hover { background: #3343d6; }
    .icon-btn { background: transparent; color: #444; padding: 6px; line-height: 0; }
    .icon-btn:hover { background: rgba(0, 0, 0, 0.07); }

    .tab {
      width: 56px; height: 28px; padding: 0;
      display: flex; align-items: center; justify-content: center;
      background: #4a5cff; color: #fff;
      border-radius: 8px 8px 0 0;
      box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.15);
    }
    .tab:hover { background: #3343d6; }
    .tab { position: relative; }
    .unread {
      position: absolute; top: -8px; right: -8px;
      background: #e5484d; color: #fff; border-radius: 999px;
      font-size: 0.7rem; line-height: 1; min-width: 18px; padding: 3px 5px; text-align: center;
    }

    .panel {
      width: min(340px, calc(100vw - 32px));
      height: min(440px, calc(100vh - 80px));
      background: #fff; border-radius: 10px 10px 0 0;
      box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.2);
      display: flex; flex-direction: column; overflow: hidden;
    }
    .header {
      display: flex; align-items: center; gap: 8px;
      padding: 8px 8px 8px 14px; border-bottom: 1px solid #e4e4ec; font-weight: 600;
    }
    .status { flex: 1; font-weight: normal; font-size: 0.8rem; color: #888; }

    .log {
      flex: 1; overflow-y: auto; list-style: none; margin: 0; padding: 12px;
      display: flex; flex-direction: column; gap: 10px;
    }
    .empty { color: #999; font-size: 0.9rem; text-align: center; margin: auto; }
    .meta { font-size: 0.75rem; color: #888; }
    .name { font-weight: 600; color: #4a5cff; margin-right: 6px; }
    .mine .name { color: #1a8a4a; }
    .text { white-space: pre-wrap; overflow-wrap: anywhere; }

    form { display: flex; gap: 8px; padding: 10px; border-top: 1px solid #e4e4ec; }
    input {
      font: inherit; flex: 1; min-width: 0; padding: 8px 10px;
      border: 1px solid #c8c8d4; border-radius: 6px;
    }
    input:focus { outline: 2px solid #4a5cff; outline-offset: -1px; }
  `;

  const chevron = (points) => `
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <polyline points="${points}"/>
    </svg>`;
  const CHEVRON_UP = chevron("6 15 12 9 18 15");
  const CHEVRON_DOWN = chevron("6 9 12 15 18 9");

  function currentName() {
    return window.AppSettings?.get("username") || "Anonymous";
  }

  class AppChatElement extends HTMLElement {
    connectedCallback() {
      if (this.shadowRoot) return;
      const root = this.attachShadow({ mode: "open" });
      root.innerHTML = `
        <style>${STYLE}</style>
        <div class="root">
          <div class="panel" hidden>
            <div class="header">
              Chat <span class="status">Connecting…</span>
              <button class="icon-btn close-btn" aria-label="Collapse chat" title="Collapse">${CHEVRON_DOWN}</button>
            </div>
            <ul class="log"></ul>
            <form autocomplete="off">
              <input maxlength="${MAX_TEXT}" placeholder="Type a message…" aria-label="Message">
              <button type="submit" class="primary">Send</button>
            </form>
          </div>
          <button class="tab" aria-label="Open chat" title="Chat">${CHEVRON_UP}<span class="unread" hidden></span></button>
        </div>`;

      this.panel = root.querySelector(".panel");
      this.status = root.querySelector(".status");
      this.log = root.querySelector(".log");
      this.input = root.querySelector("input");
      this.tab = root.querySelector(".tab");
      this.unreadBadge = root.querySelector(".unread");
      this.unread = 0;
      this.retries = 0;

      this.showEmpty();
      this.tab.addEventListener("click", () => this.setOpen(true));
      root.querySelector(".close-btn").addEventListener("click", () => this.setOpen(false));
      root.querySelector("form").addEventListener("submit", (e) => {
        e.preventDefault();
        this.send();
      });

      this.connect();
    }

    connect() {
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      this.socket = new WebSocket(`${protocol}//${location.host}/ws/chat`);
      this.status.textContent = "Connecting…";

      this.socket.addEventListener("open", () => {
        this.retries = 0;
        this.status.textContent = "Online";
      });

      this.socket.addEventListener("message", (event) => {
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        if (data.type === "history") {
          this.log.replaceChildren();
          data.messages.forEach((m) => this.render(m));
          if (!data.messages.length) this.showEmpty();
          this.scrollToBottom();
        } else if (data.type === "chat") {
          this.render(data);
          if (this.panel.hidden) this.setUnread(this.unread + 1);
        }
      });

      this.socket.addEventListener("close", () => {
        const delay = Math.min(1000 * 2 ** this.retries, 15000);
        this.retries++;
        this.status.textContent = "Offline, reconnecting…";
        setTimeout(() => this.connect(), delay);
      });
    }

    send() {
      const text = this.input.value.trim();
      if (!text) return;
      if (this.socket?.readyState !== WebSocket.OPEN) {
        this.status.textContent = "Offline, message not sent";
        return;
      }
      this.socket.send(JSON.stringify({ type: "chat", name: currentName(), text }));
      this.input.value = "";
    }

    render(msg) {
      const atBottom = this.log.scrollHeight - this.log.scrollTop - this.log.clientHeight < 40;
      this.log.querySelector(".empty")?.remove();

      const item = document.createElement("li");
      if (msg.name === currentName()) item.className = "mine";

      const meta = document.createElement("div");
      meta.className = "meta";
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = msg.name;
      const time = document.createElement("span");
      time.textContent = new Date(msg.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      meta.append(name, time);

      const text = document.createElement("div");
      text.className = "text";
      text.textContent = msg.text;

      item.append(meta, text);
      this.log.append(item);
      if (atBottom) this.scrollToBottom();
    }

    showEmpty() {
      const empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = "No messages yet.";
      this.log.replaceChildren(empty);
    }

    setOpen(open) {
      this.panel.hidden = !open;
      this.tab.hidden = open;
      if (open) {
        this.setUnread(0);
        this.scrollToBottom();
        this.input.focus();
      } else {
        this.tab.focus();
      }
    }

    setUnread(count) {
      this.unread = count;
      this.unreadBadge.textContent = count > 99 ? "99+" : count;
      this.unreadBadge.hidden = count === 0;
      this.tab.setAttribute("aria-label", count ? `Open chat (${count} unread)` : "Open chat");
    }

    scrollToBottom() {
      this.log.scrollTop = this.log.scrollHeight;
    }
  }

  customElements.define("app-chat", AppChatElement);
  if (!document.querySelector("app-chat")) {
    document.body.append(document.createElement("app-chat"));
  }
})();
