"""Loading game content from JSON files (cards, units, levels) at import time.

Bad files are logged and skipped, so one broken card never takes the whole game down.
Parsers raise ValueError with a readable reason; these helpers catch and log it.

    from gamekit.data import load_json, load_json_dir, whole, text, DataError

    def parse_card(card_id, data):          # data is the file's JSON object
        return {"id": card_id, "name": text(data, "name", 40, required=True),
                "value": whole(data, "value", 0, 1000, default=0)}

    CARDS = load_json_dir(Path(__file__).parent / "cards", parse_card, log)  # {id: card}
    MARKS = load_json(Path(__file__).parent / "marks.json", parse_marks, log, default=[])

load_json_dir(folder, parse, log, id_pattern=ID)
    Reads every <id>.json in `folder` (sorted by id). The file name (without .json) must
    match id_pattern (default: 1-40 lowercase letters, digits, - or _). The file must hold a
    JSON object. Returns {id: parse(id, data)}; files that fail are logged and left out.
load_json(path, parse, log, default=None)
    Reads one JSON file and returns parse(data), or `default` (logged) if it fails.
whole(data, key, low, high, default=None)   int field in range (default if missing; required if None)
text(data, key, limit, required=False)      string field, stripped and cut to limit ("" if missing)
flag(data, key)                             True only if the field is exactly true
"""

import json
import re

ID = re.compile(r"^[a-z0-9_-]{1,40}$")
DataError = ValueError


def load_json(path, parse, log, default=None):
    try:
        return parse(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        log.error("Can't read %s: %s", path, error)
        return default


def load_json_dir(folder, parse, log, id_pattern=ID):
    items = {}
    for path in sorted(folder.glob("*.json")):
        item_id = path.stem
        try:
            if not id_pattern.match(item_id):
                raise ValueError("file name must be 1-40 lowercase letters, digits, - or _")
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("must be a JSON object")
            items[item_id] = parse(item_id, data)
        except (OSError, ValueError) as error:
            log.error("Skipping %s: %s", path, error)
    return items


def whole(data, key, low, high, default=None):
    value = data.get(key, default)
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{key} must be a whole number from {low} to {high}")
    return value


def text(data, key, limit, required=False):
    value = data.get(key)
    value = value.strip()[:limit] if isinstance(value, str) else ""
    if required and not value:
        raise ValueError(f"needs a {key}")
    return value


def flag(data, key):
    return data.get(key) is True
