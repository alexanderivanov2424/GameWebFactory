"""Find and check the sites in ExternalSites/ (extra pages deployed next to the games site).
deploy-external.sh uses it to know what to deploy, and tools/run_tests.py runs the same checks.

    python3 -I tools/external_sites.py list [ExternalSites folder]

Prints one line per site, "<id> <port> <max body MB>" ("-" for port and size when the site is
static only), or the problems found (exit code 1).

A site is a folder ExternalSites/<id>/ (id: lowercase letters, digits and "-"), served at /<id>/:
    web/          static files (must hold index.html), copied to the web root under /<id>/
    server.py     optional: the site's own Python (standard library) HTTP server for /<id>/api/,
                  listening on 127.0.0.1:$PORT and keeping its data in $SITE_DATA
    site.json     needed with server.py: {"port": 1024-65535, "max_body_mb": 1-20 (default 1)}
    data/         the server's saved data (git-ignored, never deployed)
The id can't clash with anything the games site already serves at the top level.

Paths: reads only the folder given (default: ExternalSites next to tools/) and APP/web; writes stdout.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITES_DIR = ROOT / "ExternalSites"
SITE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
TAKEN_PORTS = {8080, 8765}  # nginx and app-server (deploy.sh)
RESERVED = {"games", "games.json", "ws"}  # added to the web root by deploy.sh / proxied by nginx


def reserved_names():
    names = set(RESERVED)
    web = ROOT / "APP" / "web"
    if web.is_dir():
        names.update(p.name for p in web.iterdir())
    return names


def load_sites(folder=SITES_DIR):
    """Return (sites, problems): sites is a list of {"id", "port", "max_body_mb"} (port None = static)."""
    sites, problems, ports = [], [], {}
    folder = Path(folder)
    if not folder.is_dir():
        return sites, problems
    reserved = reserved_names()
    for path in sorted(p for p in folder.iterdir() if p.is_dir()):
        site_id = path.name
        if site_id.startswith(".") or site_id == "__pycache__":
            continue
        where = f"ExternalSites/{site_id}"
        if not SITE_ID.match(site_id):
            problems.append(f"{where}: folder name must be lowercase letters, digits and '-'")
            continue
        if site_id in reserved:
            problems.append(f"{where}: /{site_id} is already used by the games site")
            continue
        if not (path / "web" / "index.html").is_file():
            problems.append(f"{where}: web/index.html is missing")
            continue
        site = {"id": site_id, "port": None, "max_body_mb": None}
        if (path / "server.py").is_file():
            try:
                config = json.loads((path / "site.json").read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                problems.append(f"{where}: site.json can't be read ({error})")
                continue
            port = config.get("port") if isinstance(config, dict) else None
            body = config.get("max_body_mb", 1) if isinstance(config, dict) else None
            if type(port) is not int or not 1024 <= port <= 65535 or port in TAKEN_PORTS:
                problems.append(f"{where}: site.json needs a free \"port\" from 1024 to 65535 (not 8080 or 8765)")
                continue
            if port in ports:
                problems.append(f"{where}: port {port} is also used by {ports[port]}")
                continue
            if type(body) is not int or not 1 <= body <= 20:
                problems.append(f"{where}: site.json \"max_body_mb\" must be a whole number from 1 to 20")
                continue
            ports[port] = site_id
            site.update(port=port, max_body_mb=body)
        sites.append(site)
    return sites, problems


def main(argv):
    if not argv or argv[0] != "list" or len(argv) > 2:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    sites, problems = load_sites(Path(argv[1]) if len(argv) > 1 else SITES_DIR)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    for site in sites:
        print(site["id"], site["port"] or "-", site["max_body_mb"] or "-")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
