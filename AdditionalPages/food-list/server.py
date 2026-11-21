"""Food list: the HTTP API behind the secret /food-list page (Python standard library only).

Run by the site's startup script in the gwf-app container, next to the game server (read-only
code; it writes only $SITE_DATA = ExternalWrite/AdditionalPages/food-list/ on the host). nginx
forwards /food-list/api/ here; it listens on 127.0.0.1:$PORT only.
By hand: `PORT=8771 SITE_DATA=/some/folder python3 server.py` (default data: ./data next to this file).

Routes (all JSON unless noted; errors are {"error": message} with a 4xx status):
    GET  /food-list/api/items                          {"items": [{id, name, notes, checked, images: [id]}]}
    POST /food-list/api/items                          {name, notes?} -> the new item
    POST /food-list/api/items/<id>/update              {name?, notes?, checked?} -> the item
    POST /food-list/api/items/<id>/delete
    POST /food-list/api/items/<id>/images              raw RGB (application/octet-stream, see images.py) -> {"image": id}
    POST /food-list/api/items/<id>/images/<img>/delete
    POST /food-list/api/clear                          {"which": "checked" | "all"} -> {"removed": n}
    GET  /food-list/api/images/<img>.png               the PNG (only pictures that are on the list)

Safety: one request at a time (nginx buffers whole bodies first, so a slow client can't stall
it); every body needs an exact Content-Length within its limit and the right Content-Type (which
also forces a CORS preflight that this server never approves, so other sites can't post here);
an Origin header, when sent, must match the Host. All checking of the data is in store.py.
"""

import json
import logging
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import images
from store import Rejected, Store

PREFIX = "/food-list/api"
MAX_JSON = 8 * 1024
JSON_TYPE = "application/json"
IMAGE_TYPE = "application/octet-stream"
ITEM = r"([0-9a-f]{16})"

POST_ROUTES = [
    (re.compile(r"^/items$"), "add", JSON_TYPE),
    (re.compile(rf"^/items/{ITEM}/update$"), "update", JSON_TYPE),
    (re.compile(rf"^/items/{ITEM}/delete$"), "delete", JSON_TYPE),
    (re.compile(rf"^/items/{ITEM}/images$"), "add_image", IMAGE_TYPE),
    (re.compile(rf"^/items/{ITEM}/images/{ITEM}/delete$"), "delete_image", JSON_TYPE),
    (re.compile(r"^/clear$"), "clear", JSON_TYPE),
]
IMAGE_ROUTE = re.compile(rf"^/images/{ITEM}\.png$")

log = logging.getLogger("food-list")


class Handler(BaseHTTPRequestHandler):
    server_version = "food-list"
    sys_version = ""
    timeout = 20  # seconds per socket read/write

    store = None  # set in main()

    # ---- responses ----

    def send(self, status, body, content_type, extra=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send(status, body, "application/json; charset=utf-8", [("Cache-Control", "no-store")])

    def log_message(self, fmt, *args):
        log.info("%s", (fmt % args)[:300])

    def path_only(self):
        path = urlsplit(self.path).path
        if not path.startswith(PREFIX + "/"):
            raise Rejected("Not found.", 404)
        return path[len(PREFIX):]

    # ---- requests ----

    def do_GET(self):
        self.handle_safely(self.get)

    def do_POST(self):
        self.handle_safely(self.post)

    def handle_safely(self, handler):
        try:
            handler()
        except Rejected as error:
            self.send_json(error.status, {"error": str(error)})
        except Exception:  # never show internals to the browser
            log.exception("Request failed")
            self.send_json(500, {"error": "Something went wrong on the server."})

    def get(self):
        path = self.path_only()
        if path == "/items":
            return self.send_json(200, self.store.public())
        match = IMAGE_ROUTE.match(path)
        file = self.store.image_path(match.group(1)) if match else None
        if file is None or not file.is_file():
            raise Rejected("Not found.", 404)
        self.send(200, file.read_bytes(), "image/png",
                  [("Cache-Control", "private, max-age=604800, immutable")])

    def post(self):
        self.check_origin()
        path = self.path_only()
        for pattern, action, content_type in POST_ROUTES:
            match = pattern.match(path)
            if match:
                break
        else:
            raise Rejected("Not found.", 404)
        body = self.read_body(content_type, images.MAX_BYTES if content_type == IMAGE_TYPE else MAX_JSON)
        ids = match.groups()
        if content_type == IMAGE_TYPE:
            return self.send_json(200, {"image": self.store.add_image(ids[0], body)})
        data = self.parse_json(body)
        store = self.store
        if action == "add":
            result = store.add(data)
        elif action == "update":
            result = store.update(ids[0], data)
        elif action == "delete":
            store.delete(ids[0])
            result = {"ok": True}
        elif action == "delete_image":
            store.delete_image(ids[0], ids[1])
            result = {"ok": True}
        else:
            result = {"removed": store.clear(data.get("which"))}
        self.send_json(200, result)

    def check_origin(self):
        site = self.headers.get("Sec-Fetch-Site")
        if site is not None and site not in ("same-origin", "none"):
            raise Rejected("Requests from other sites aren't allowed.", 403)
        origin = self.headers.get("Origin")
        if origin is not None and urlsplit(origin).netloc != self.headers.get("Host"):
            raise Rejected("Requests from other sites aren't allowed.", 403)

    def read_body(self, content_type, limit):
        if self.headers.get("Transfer-Encoding") is not None:
            raise Rejected("Send a Content-Length.", 411)
        lengths = self.headers.get_all("Content-Length") or []
        if len(lengths) != 1 or not lengths[0].isdigit():
            raise Rejected("Send one Content-Length.", 411)
        length = int(lengths[0])
        if length > limit:
            raise Rejected("That's too much data.", 413)
        sent_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if sent_type != content_type:
            raise Rejected(f"Expected {content_type}.", 415)
        body = self.rfile.read(length)
        if len(body) != length:
            raise Rejected("The request was cut short.")
        return body

    @staticmethod
    def parse_json(body):
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise Rejected("Bad JSON.") from None
        if not isinstance(data, dict):
            raise Rejected("Bad JSON.")
        return data


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    here = Path(__file__).resolve().parent
    port = int(os.environ.get("PORT") or json.loads((here / "site.json").read_text())["port"])
    data = Path(os.environ.get("SITE_DATA") or here / "data")
    Handler.store = Store(data)
    server = HTTPServer(("127.0.0.1", port), Handler)
    log.info("Food list on 127.0.0.1:%d, data in %s (%d items)", port, data, len(Handler.store.items))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
