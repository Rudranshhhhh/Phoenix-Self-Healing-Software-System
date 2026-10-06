"""Remove incidents from the phoenix-api JSON store.

Usage (from phoenix-api/):
    python scripts/remove_incidents.py INC-102 INC-103 ...

The store path is PHOENIX_DATA_FILE, or data/incidents.json by default. A
copy is saved next to it as <name>.bak before anything changes.

Id numbering is kept: the agent-id -> INC-id mappings of removed incidents
stay in "ids" (under a "removed:" key), so new incidents keep counting up
from the highest number ever handed out.

Stop the API first. It holds the store in memory and rewrites the whole
file on the next ingested event, which would bring the incidents back.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "data" / "incidents.json"


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__.strip())
        return 0 if argv else 2

    path = Path(os.environ.get("PHOENIX_DATA_FILE", str(DEFAULT_FILE)))
    if not path.is_file():
        print(f"error: store not found at {path}; nothing to do", file=sys.stderr)
        return 1

    data = json.loads(path.read_text(encoding="utf-8"))
    incidents: dict = data.get("incidents", {})
    ids: dict = data.get("ids", {})

    wanted = list(dict.fromkeys(argv))
    removed = [i for i in wanted if i in incidents]
    missing = [i for i in wanted if i not in incidents]
    if not removed:
        print(f"No matching incidents in {path} (not found: {', '.join(missing)})")
        return 1

    backup = path.with_name(path.name + ".bak")
    shutil.copy2(path, backup)

    for incident_id in removed:
        del incidents[incident_id]
    gone = set(removed)
    data["ids"] = {
        (f"removed:{key}" if value in gone and not key.startswith("removed:") else key): value
        for key, value in ids.items()
    }
    data["incidents"] = incidents

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)

    print(f"Backup: {backup}")
    for incident_id in removed:
        print(f"Removed {incident_id}")
    if missing:
        print(f"Not found: {', '.join(missing)}")
    print(f"{len(incidents)} incident(s) left in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
