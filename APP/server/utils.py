"""Small helpers shared by the server and by games."""


def clean_text(value, limit):
    """Return value stripped and cut to `limit` characters, or "" if it isn't a string."""
    return value.strip()[:limit] if isinstance(value, str) else ""
