"""Host settings declared once: validated on the server, drawn by the client.

A game lists its settings in the class attribute SETTINGS; LobbyGame then provides
default_settings() and clean_settings() from it, and sends the list to clients as
state.settingsSpec, which AppLobbyUI.settingsForm (web/gamekit/lobby-ui.js) turns into inputs.

    from gamekit import Choice, Int, LobbyGame, MultiChoice

    class Game(LobbyGame):
        SETTINGS = {
            "boardSize": Int("Board size", default=3, low=3, high=10),
            "winLength": Int("Pieces in a row to win", default=3, low=3, high="boardSize"),
            "wallChance": Int("Wall chance", default=15, low=0, high=100, suffix="%"),
            "mode": Choice("Mode", default="classic", options={"classic": "Classic", "fast": "Fast"}),
            "extras": MultiChoice("Extras", default=["ice"], options={"ice": "Ice", "lava": "Lava"}),
        }

Int(label, default, low, high, suffix="", hint="")
    A whole number. Anything else is rejected with "<label> must be a whole number.";
    out-of-range values are clamped. `low`/`high` may name another setting (a key in
    SETTINGS declared *before* this one), e.g. high="boardSize": the bound follows that
    setting's value, on the server and in the client's input.

Choice(label, default, options, hint="")
    One of a fixed set of strings, drawn as a drop-down. `options` is {value: label} in display
    order; the value is what self.settings holds and the client sends, the label what players
    read. Anything else is rejected with "<label> must be one of: <labels>.".

MultiChoice(label, default, options, low=0, hint="")
    Any set of the options (a list of their values), drawn as checkboxes. The value is a list
    in `options` order without repeats; anything but a list of option values is rejected, and
    so is a list of fewer than `low` (the client also won't untick below `low`).

Settings missing from an update keep their current value. For rules that span several
settings beyond a linked bound, override clean_settings, call super().clean_settings(settings),
then adjust or raise LobbyError.
"""

from gamekit.validate import LobbyError, whole_number


class Int:
    def __init__(self, label, default, low, high, suffix="", hint=""):
        self.label = label
        self.default = default
        self.low = low
        self.high = high
        self.suffix = suffix
        self.hint = hint

    def bounds(self, values):
        def bound(b):
            return values[b] if isinstance(b, str) else b

        return bound(self.low), bound(self.high)

    def clean(self, value, values):
        low, high = self.bounds(values)
        return whole_number(value, self.label, low, high)

    def spec(self, key):
        spec = {"key": key, "type": "int", "label": self.label, "suffix": self.suffix, "hint": self.hint}
        for name, bound in (("min", self.low), ("max", self.high)):
            spec[name + "From" if isinstance(bound, str) else name] = bound
        return spec


class Choice:
    def __init__(self, label, default, options, hint=""):
        if default not in options:
            raise ValueError(f"{label}: default {default!r} is not one of the options")
        self.label = label
        self.default = default
        self.options = dict(options)
        self.hint = hint

    def clean(self, value, values):
        if type(value) is not str or value not in self.options:
            raise LobbyError(f"{self.label} must be one of: {', '.join(self.options.values())}.")
        return value

    def spec(self, key):
        options = [{"value": value, "label": label} for value, label in self.options.items()]
        return {"key": key, "type": "choice", "label": self.label, "hint": self.hint, "options": options}


class MultiChoice:
    def __init__(self, label, default, options, low=0, hint=""):
        self.label = label
        self.options = dict(options)
        self.low = low
        self.hint = hint
        if any(value not in self.options for value in default) or len(set(default)) < low:
            raise ValueError(f"{label}: the default must be at least {low} of the options")
        self.default = list(default)

    def clean(self, value, values):
        if type(value) is not list or any(type(v) is not str or v not in self.options for v in value):
            raise LobbyError(f"{self.label} must be a list of: {', '.join(self.options.values())}.")
        picked = [option for option in self.options if option in value]
        if len(picked) < self.low:
            raise LobbyError(f"{self.label}: pick at least {self.low}.")
        return picked

    def spec(self, key):
        options = [{"value": value, "label": label} for value, label in self.options.items()]
        return {"key": key, "type": "multi", "label": self.label, "hint": self.hint, "options": options, "min": self.low}


def defaults(fields):
    """The default settings: {key: default}, with linked bounds applied."""
    return clean(fields, {}, {})


def clean(fields, settings, current):
    """Validate `settings` (from the host) against `fields`; missing keys keep `current` values."""
    values = {}
    for key, field in fields.items():
        value = settings.get(key, current.get(key, field.default))
        values[key] = field.clean(value, values)
    return values


def spec(fields):
    """JSON-friendly description of the fields, sent to clients as state.settingsSpec."""
    return [field.spec(key) for key, field in fields.items()]
