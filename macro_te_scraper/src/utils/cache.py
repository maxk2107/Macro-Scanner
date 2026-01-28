"""Simple file‑backed cache for macro indicator values.

The cache stores a dictionary keyed by indicator name.  Each entry contains
the scraped values along with the UTC timestamp when they were cached.  If
retrieved within the configured TTL, cached values are returned instead of
scraping again.  The cache is persisted to JSON on disk in the `output/`
directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class CacheEntry:
    data: Dict[str, Any]
    timestamp: datetime


class Cache:
    """File‑based cache with a time‑to‑live for each entry."""

    def __init__(self, cache_file: Path, ttl_minutes: int) -> None:
        self.cache_file = cache_file
        self.ttl = timedelta(minutes=ttl_minutes)
        self._entries: Dict[str, CacheEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.cache_file.exists():
            return
        try:
            with self.cache_file.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            for key, val in raw.items():
                ts_str = val.get("timestamp")
                data = val.get("data")
                if ts_str and data:
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        self._entries[key] = CacheEntry(data=data, timestamp=ts)
                    except Exception:
                        continue
        except Exception:
            # Corrupt cache; ignore
            self._entries = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._entries.get(key)
        if not entry:
            return None
        if datetime.utcnow() - entry.timestamp < self.ttl:
            return entry.data
        return None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        self._entries[key] = CacheEntry(data=value, timestamp=datetime.utcnow())
        self.save()

    def save(self) -> None:
        # Persist all entries to JSON
        serialisable: Dict[str, Any] = {}
        for key, entry in self._entries.items():
            serialisable[key] = {
                "data": entry.data,
                "timestamp": entry.timestamp.isoformat(),
            }
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_file.open("w", encoding="utf-8") as f:
            json.dump(serialisable, f, indent=2)
