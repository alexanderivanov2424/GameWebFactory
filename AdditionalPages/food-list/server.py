"""Food list: the HTTP API behind the secret /food-list page (Python standard library only).

Run by the site's startup script in the gwf-app container, next to the game server (read-only
code; it writes only $SITE_DATA = ExternalWrite/AdditionalPages/food-list/ on the host). nginx
forwards /food-list/api/ here; it listens on 127.0.0.1:$PORT only.
By hand: `PORT=8771 SITE_DATA=/some/folder python3 server.py` (default data: ./data next to this file).

Routes (all JSON unless noted; errors are {"error": message} with a 4xx status). The data model
(lists, their entries, foods = everything about an item, tags) is described in store.py.
An item as sent: {id, food, name, tags: [tag id], notes, images: [id], global, checked}.
    GET  /food-list/api/lists                          summary: {"lists": [{id, name, count, left}],
                                                                 "foods": [{name, tags, global}],
                                                                 "tags": [{id, name, hue}]}
    GET  /food-list/api/lists/<list>                   summary + {"list": {id, name, items: [item]}}
    GET  /food-list/api/foods                          summary + {"list": {id: "global", name, global: true, items:
                                                                 [global foods as items without checked, id = food]}}
    POST /food-list/api/lists                          {name} -> {id, name}
    POST /food-list/api/lists/<list>/update            {name?} -> {id, name}
    POST /food-list/api/lists/<list>/delete            (refused for the last list)
    POST /food-list/api/lists/<list>/items             {name} -> the new item
    POST /food-list/api/lists/<list>/clear             {"which": "checked" | "all"} -> {"removed": n}
    POST /food-list/api/items/<id>/update              {checked?, and any food field below} -> the item
    POST /food-list/api/items/<id>/delete              takes it off the list (the food stays if it's global or on
                                                       another list)
    POST /food-list/api/foods/<food>/update            {name?, tags?: [tag name], notes?, global? (false refused
                                                       for items with pictures)}
    POST /food-list/api/foods/delete                   {"ids": [food]} -> {"deleted": n} (for good, off every list)
    POST /food-list/api/tags                           {name, hue? (0-359)} -> {id, name, hue}
    POST /food-list/api/tags/<tag>/update              {name?, hue? (0-359)} -> {id, name, hue}
    POST /food-list/api/tags/<tag>/delete              deletes it for good, off every item
    POST /food-list/api/foods/<food>/images            raw RGB (application/octet-stream, see images.py) -> {"image": id}
                                                       (puts the food in the Global list)
    POST /food-list/api/foods/<food>/images/<img>/delete
    GET  /food-list/api/images/<img>.png               the PNG (only pictures some food has)

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
MAX_JSON = 16 * 1024
JSON_TYPE = "application/json"
IMAGE_TYPE = "application/octet-stream"
ID = r"([0-9a-f]{16})"

POST_ROUTES = [
    (re.compile(r"^/lists$"), "add_list", JSON_TYPE),
    (re.compile(rf"^/lists/{ID}/update$"), "update_list", JSON_TYPE),
    (re.compile(rf"^/lists/{ID}/delete$"), "delete_list", JSON_TYPE),
    (re.compile(rf"^/lists/{ID}/items$"), "add", JSON_TYPE),
    (re.compile(rf"^/lists/{ID}/clear$"), "clear", JSON_TYPE),
    (re.compile(rf"^/items/{ID}/update$"), "update", JSON_TYPE),
    (re.compile(rf"^/items/{ID}/delete$"), "delete", JSON_TYPE),
    (re.compile(rf"^/foods/{ID}/update$"), "update_food", JSON_TYPE),
    (re.compile(r"^/foods/delete$"), "delete_foods", JSON_TYPE),
    (re.compile(r"^/tags$"), "add_tag", JSON_TYPE),
    (re.compile(rf"^/tags/{ID}/update$"), "update_tag", JSON_TYPE),
    (re.compile(rf"^/tags/{ID}/delete$"), "delete_tag", JSON_TYPE),
    (re.compile(rf"^/foods/{ID}/images$"), "add_image", IMAGE_TYPE),
    (re.compile(rf"^/foods/{ID}/images/{ID}/delete$"), "delete_image", JSON_TYPE),
]
# action -> how to call the store with (ids, data) and what to answer
ACTIONS = {
    "add_list": lambda store, ids, data: store.add_list(data),
    "update_list": lambda store, ids, data: store.update_list(ids[0], data),
    "delete_list": lambda store, ids, data: store.delete_list(ids[0]) or {"ok": True},
    "add": lambda store, ids, data: store.add(ids[0], data),
    "clear": lambda store, ids, data: {"removed": store.clear(ids[0], data.get("which"))},
    "update": lambda store, ids, data: store.update(ids[0], data),
    "delete": lambda store, ids, data: store.delete(ids[0]) or {"ok": True},
    "update_food": lambda store, ids, data: store.update_food(ids[0], data),
    "delete_foods": lambda store, ids, data: {"deleted": store.delete_foods(data.get("ids"))},
    "add_tag": lambda store, ids, data: store.add_tag(data),
    "update_tag": lambda store, ids, data: store.update_tag(ids[0], data),
    "delete_tag": lambda store, ids, data: store.delete_tag(ids[0]) or {"ok": True},
    "delete_image": lambda store, ids, data: store.delete_image(ids[0], ids[1]) or {"ok": True},
}
LIST_ROUTE = re.compile(rf"^/lists/{ID}$")
IMAGE_ROUTE = re.compile(rf"^/images/{ID}\.png$")

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
        if path == "/lists":
            return self.send_json(200, self.store.summary())
        if path == "/foods":
            return self.send_json(200, self.store.public_foods())
        match = LIST_ROUTE.match(path)
        if match:
            return self.send_json(200, self.store.public_list(match.group(1)))
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
        result = ACTIONS[action](self.store, ids, self.parse_json(body))
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
    log.info("Food list on 127.0.0.1:%d, data in %s (%d lists)", port, data, len(Handler.store.lists))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
