"""bdgcafe image API — a FastAPI service that resizes + watermarks images on the fly.

Serves images from a PRIVATE R2 bucket, resized + watermarked on the fly with
Pillow. The request path IS the R2 object key; transform via query params:

  width  | w       target width  (px, never enlarges past the source)
  height | h       target height (px)
  quality| q       1-100 (default 82)
  fit              scale-down | contain | cover | crop | pad
                   (default: cover when both w & h given, else scale-down)
  format | f       avif | webp | jpeg | png | auto (default webp;
                   auto negotiates from the Accept header)

Designed to sit behind Cloudflare's edge cache: every response carries an
immutable Cache-Control header + ETag, so the CDN serves repeats without ever
hitting this origin (the transform only runs on a cache MISS).
"""

import hashlib
import logging

from fastapi import FastAPI, Request, Response

from cache import DiskCache, NullCache
from config import get_settings
from images import CONTENT_TYPE, MAX_DIM, render
from params import (
    clamp_quality,
    int_param,
    is_watermark_bypassed,
    resolve_fit,
    resolve_format,
)
from r2_client import R2Client, WatermarkCache

CACHE_CONTROL = "public, max-age=31536000, immutable"

settings = get_settings()
r2 = R2Client(settings)
watermark_cache = WatermarkCache(r2, settings.watermark_key)
output_cache = DiskCache(settings.cache_dir) if settings.cache_dir else NullCache()

app = FastAPI(title="bandung-coffeeshop-image", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


def _canonical_key(
    key: str,
    width: int | None,
    height: int | None,
    quality: int,
    fit: str,
    fmt: str,
    bypass: bool,
) -> str:
    """Stable identity for a rendered variant — drives both the disk cache and
    the ETag. Aliases collapse here, and the resolved format/watermark flag are
    baked in so `auto` (avif vs webp) and bypassed copies never collide."""
    parts = [key]
    if width:
        parts.append(f"w={width}")
    if height:
        parts.append(f"h={height}")
    parts.append(f"q={quality}")
    if width or height:
        parts.append(f"fit={fit}")
    parts.append(f"fmt={fmt}")
    if bypass:
        parts.append("wm=0")
    return "|".join(parts)


@app.get("/{key:path}")
def serve(key: str, request: Request) -> Response:
    # Starlette has already percent-decoded the path param. Reject empty,
    # path traversal, and direct access to the bare watermark.
    if not key or ".." in key or key == settings.watermark_key:
        return Response("Not Found", status_code=404)

    params = request.query_params
    req_width = int_param(params, "width", "w")
    req_height = int_param(params, "height", "h")
    quality = clamp_quality(int_param(params, "quality", "q"))
    fit = resolve_fit(req_width, req_height, params.get("fit"))
    fmt_param = params.get("format") or params.get("f")
    fmt = resolve_format(fmt_param, request.headers.get("accept", ""))
    bypass = is_watermark_bypassed(key, settings.watermark_bypass)

    canonical = _canonical_key(key, req_width, req_height, quality, fit, fmt, bypass)
    etag = '"' + hashlib.sha256(canonical.encode()).hexdigest()[:32] + '"'

    headers = {
        "Content-Type": CONTENT_TYPE[fmt],
        "Cache-Control": CACHE_CONTROL,
        "ETag": etag,
    }
    # Only `auto` varies on the request; tell shared caches downstream.
    if (fmt_param or "").lower() == "auto":
        headers["Vary"] = "Accept"

    # Cheap revalidation: if the client/CDN already holds this exact variant,
    # skip the bucket read and the transform entirely.
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    cached = output_cache.get(canonical)
    if cached is not None:
        return Response(cached, headers=headers)

    original = r2.get_object(key)
    if original is None:
        return Response("Not Found", status_code=404)

    watermark = None if bypass else watermark_cache.get()
    if not bypass and watermark is None:
        return Response("Watermark asset missing", status_code=500)

    try:
        output = render(
            original,
            watermark,
            width=min(req_width, MAX_DIM) if req_width else None,
            height=min(req_height, MAX_DIM) if req_height else None,
            quality=quality,
            fit=fit,
            fmt=fmt,
        )
    except Exception:
        logging.getLogger("bandung-coffeeshop-image").exception("image transform failed: %s", key)
        return Response("Image processing failed", status_code=500)

    output_cache.put(canonical, output)
    return Response(output, headers=headers)
