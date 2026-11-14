from __future__ import annotations

import json
import os
import tempfile


class State:
    """What the bot remembers between runs, so no trade is alerted twice."""

    def __init__(self, data: dict | None = None):
        d = data or {}
        self.started: str | None = d.get("started")
        self.etag: str = d.get("etag", "")
        self.seen: dict[str, str] = dict(d.get("seen", {}))     # trade id -> filing date

    @property
    def is_new(self) -> bool:
        return not self.started

    @classmethod
    def load(cls, path: str) -> "State":
        if not os.path.exists(path):
            return cls()
        try:
            with open(path) as f:
                return cls(json.load(f))
        except json.JSONDecodeError as e:
            raise SystemExit(f"State file {path} is corrupt ({e}). "
                             "Delete it deliberately to start fresh.")

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump({"started": self.started, "etag": self.etag, "seen": self.seen},
                      f, separators=(",", ":"), sort_keys=True)
        os.replace(tmp, path)
