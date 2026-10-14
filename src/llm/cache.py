"""On-disk cache for LLM responses, so re-running a pipeline step costs no API calls."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LLMCache:
    """Stores one JSON file per LLM call, keyed by a hash of everything that affects the output."""

    def __init__(self, directory: Path, enabled: bool = True) -> None:
        self.directory = directory
        self.enabled = enabled

    @staticmethod
    def make_key(**parts: Any) -> str:
        """Hash the call's inputs (provider, model, prompt, schema, ...) into a stable key."""
        payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        # Two-character subfolders keep any single folder from holding thousands of files.
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict | None:
        """Return the cached entry for `key`, or None on a miss (or unreadable file)."""
        if not self.enabled:
            return None
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Ignoring unreadable cache file %s", path)
            return None

    def set(self, key: str, value: dict) -> None:
        """Store `value` under `key`. Writes atomically so a crash can't leave half a file."""
        if not self.enabled:
            return
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
