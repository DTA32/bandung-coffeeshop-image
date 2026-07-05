"""Pure helpers for turning request query params into transform options.

Kept free of FastAPI/Pillow so they can be unit-tested in isolation.
"""

import math

from images import (
    DEFAULT_FORMAT,
    DEFAULT_QUALITY,
    FITS,
    FORMAT_ALIASES,
)


def is_watermark_bypassed(key: str, watermark_list: str | None) -> bool:
    """True if `key` matches any entry in the comma/newline-separated list.

    Entry forms: exact ("a/b.jpg"), folder ("a/" => prefix),
    wildcard ("a/b-*" => prefix).
    """
    if not watermark_list:
        return False
    for raw in watermark_list.replace("\n", ",").split(","):
        entry = raw.strip()
        if not entry:
            continue
        if entry.endswith("*"):
            if key.startswith(entry[:-1]):
                return True
        elif entry.endswith("/"):
            if key.startswith(entry):
                return True
        elif key == entry:
            return True
    return False


def int_param(params, *names: str) -> int | None:
    """First positive integer among the given query aliases, else None."""
    for name in names:
        raw = params.get(name)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            return round(value)
    return None


def resolve_fit(width: int | None, height: int | None, fit_param: str | None) -> str:
    """cover when both dimensions are given, else scale-down (unless overridden)."""
    if fit_param and fit_param in FITS:
        return fit_param
    return "cover" if (width and height) else "scale-down"


def resolve_format(format_param: str | None, accept: str) -> str:
    """Resolve the canonical output format, negotiating `auto` from Accept."""
    fmt_param = (format_param or "").lower()
    if fmt_param == "auto":
        return "avif" if "image/avif" in accept else "webp"
    return FORMAT_ALIASES.get(fmt_param, DEFAULT_FORMAT)


def clamp_quality(requested: int | None) -> int:
    return min(100, requested) if requested else DEFAULT_QUALITY
