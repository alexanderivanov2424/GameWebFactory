/*
 * Room connection helper for games.
 *
 *   const room = AppRoom.connect("my-game", {
 *     onOpen()         { ... },
 *     onMessage(data)  { ... },
 *     onClose(info)    { ... },   // info.replaced: this tab's room was opened elsewhere
 *   });
 *   room.send({ type: "..." });
 *   room.clientId   // this tab's player id, as the server sees it
 *
 * Joins the room named by ?room=<id> in the page URL (default "main").
 * Messages are JSON objects. Reconnects automatically; onOpen runs again after each reconnect.
 *
 * The client id is a random UUID kept for the life of the browser tab, and lets the
 * server recognize the same player when they reconnect. It comes from settings.js
 * (shown there under "UUID"); if settings.js isn't loaded, it is created here the
 * same way, under the same sessionStorage key.
 */
(() => {
  const CLIENT_ID_KEY = "app.clientId";
  const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const CLOSE_INVALID = 1008;
  const CLOSE_REPLACED = 4001;

  function newUuid() {
    // crypto.getRandomValues works over plain HTTP (crypto.randomUUID does not).
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40; // version 4
    b[8] = (b[8] & 0x3f) | 0x80; // variant
    const hex = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function getClientId() {
    if (window.AppSettings?.clientId) return window.AppSettings.clientId;
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

  const clientId = getClientId();

  function connect(gameId, handlers = {}) {
    const roomId = new URLSearchParams(location.search).get("room") || "main";
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const params = new URLSearchParams({ room: roomId, client: clientId });
    const url = `${protocol}//${location.host}/ws/game/${encodeURIComponent(gameId)}?${params}`;
    let socket;
    let retries = 0;
    let stopped = false;

    function open() {
      socket = new WebSocket(url);
      socket.addEventListener("open", () => {
        retries = 0;
        handlers.onOpen?.();
      });
      socket.addEventListener("message", (event) => {
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        handlers.onMessage?.(data);
      });
      socket.addEventListener("close", (event) => {
        const replaced = event.code === CLOSE_REPLACED;
        if (replaced || event.code === CLOSE_INVALID) stopped = true;
        handlers.onClose?.({ replaced });
        if (stopped) return;
        const delay = Math.min(1000 * 2 ** retries, 15000);
        retries++;
        setTimeout(open, delay);
      });
    }

    open();

    return {
      roomId,
      clientId,
      /** Send a JSON message. Returns false if not connected. */
      send(data) {
        if (socket.readyState !== WebSocket.OPEN) return false;
        socket.send(JSON.stringify(data));
        return true;
      },
      close() {
        stopped = true;
        socket.close();
      },
    };
  }

  window.AppRoom = { connect, clientId };
})();
