"""A small disk cache for HTTP responses.

Every source here is free, and two of them are rate limited (football-data.org
at 10 requests/minute, API-Football at 100/day). Re-running a chart should not
spend that budget, and a laptop on a train should still render yesterday's
data. So every fetch goes through here.

Entries are plain JSON files under ``.cache/``, named by source and key, and
expire on age. Delete the directory to force a refresh, or pass
``max_age=0``.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import CACHE_DIR

#: Match data stops changing once a match ends; league aggregates change after
#: every fixture. Six hours keeps a day's work off the network without going
#: stale across a matchday.
DEFAULT_MAX_AGE = 6 * 60 * 60

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _path(source: str, key: str) -> Path:
    return CACHE_DIR / source / f"{_UNSAFE.sub('_', key)}.json"


def cached(
    source: str,
    key: str,
    fetch: Callable[[], Any],
    max_age: float = DEFAULT_MAX_AGE,
) -> Any:
    """Return ``fetch()``'s result, reusing a recent copy from disk if there is one.

    If the network call fails but a stale entry exists, the stale entry is
    returned rather than the error: an old chart beats no chart, and these
    sources go down.
    """
    path = _path(source, key)

    if path.exists() and max_age > 0:
        age = time.time() - path.stat().st_mtime
        if age < max_age:
            return json.loads(path.read_text())

    try:
        value = fetch()
    except Exception:
        if path.exists():
            return json.loads(path.read_text())
        raise

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return value


def clear(source: str | None = None) -> int:
    """Delete cached responses. Returns the number of files removed."""
    root = CACHE_DIR / source if source else CACHE_DIR
    if not root.exists():
        return 0
    files = list(root.rglob("*.json"))
    for f in files:
        f.unlink()
    return len(files)
