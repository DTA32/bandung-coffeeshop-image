"""Optional on-disk cache for rendered output.

Keyed by the canonical request string so that param aliases collapse to one
entry and `format=auto` variants (avif vs webp) cache separately. Disabled when
CACHE_DIR is unset — in production you'd typically also put a CDN in front,
which the immutable Cache-Control header lets it cache aggressively.
"""

import hashlib
import os
from pathlib import Path


class DiskCache:
    def __init__(self, directory: str):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        # Shard by the first two hex chars to keep directories small.
        return self.dir / digest[:2] / digest

    def get(self, key: str) -> bytes | None:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            return None

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write so a concurrent reader never sees a half-written file.
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)


class NullCache:
    """No-op cache used when caching is disabled."""

    def get(self, key: str) -> bytes | None:
        return None

    def put(self, key: str, data: bytes) -> None:
        pass
