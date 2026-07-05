"""Image transformation: resize + centered watermark + encode.

The Pillow pipeline behind the API. The query-param contract lines up with what
unpic-img emits per srcset width, so it drops straight into an unpic frontend.
"""

from io import BytesIO

from PIL import Image, ImageOps

# AVIF support comes from the pillow-avif-plugin codec (a required dependency).
import pillow_avif  # noqa: F401  registers the AVIF plugin with Pillow

# --- Constants -------------------------------------------------------------
WATERMARK_SCALE = 0.35  # watermark width as a fraction of the rendered width
WATERMARK_OPACITY = 0.35
DEFAULT_FORMAT = "webp"
DEFAULT_QUALITY = 82
MAX_DIM = 4000  # clamp requested + oversized-source dimensions

FITS = {"scale-down", "contain", "cover", "crop", "pad"}
FORMAT_ALIASES = {
    "avif": "avif",
    "webp": "webp",
    "jpeg": "jpeg",
    "jpg": "jpeg",
    "png": "png",
}
CONTENT_TYPE = {
    "avif": "image/avif",
    "webp": "image/webp",
    "jpeg": "image/jpeg",
    "png": "image/png",
}

_RESAMPLE = Image.Resampling.LANCZOS


def _resize(img: Image.Image, w: int | None, h: int | None, fit: str) -> Image.Image:
    """Apply the requested fit, never enlarging past the source."""
    src_w, src_h = img.size

    # No explicit size: only clamp a huge original.
    if not w and not h:
        if src_w > MAX_DIM or src_h > MAX_DIM:
            return ImageOps.contain(img, (MAX_DIM, MAX_DIM), _RESAMPLE)
        return img

    # Fill the missing axis from the source aspect ratio so single-dimension
    # requests behave the same across every fit mode.
    if w and not h:
        h = max(1, round(src_h * w / src_w))
    elif h and not w:
        w = max(1, round(src_w * h / src_h))

    if fit == "contain":
        return ImageOps.contain(img, (w, h), _RESAMPLE)

    if fit == "scale-down":
        if src_w <= w and src_h <= h:
            return img  # already fits — don't upscale
        return ImageOps.contain(img, (w, h), _RESAMPLE)

    if fit == "pad":
        # Transparent padding; flattened to white later if the output is JPEG.
        return ImageOps.pad(img, (w, h), _RESAMPLE, color=(0, 0, 0, 0), centering=(0.5, 0.5))

    if fit == "crop":
        # cover, but never enlarge: shrink the target box to native scale.
        scale = max(w / src_w, h / src_h)
        if scale > 1:
            w = max(1, round(w / scale))
            h = max(1, round(h / scale))
        return ImageOps.fit(img, (w, h), _RESAMPLE, centering=(0.5, 0.5))

    # cover (default when both width & height are given)
    return ImageOps.fit(img, (w, h), _RESAMPLE, centering=(0.5, 0.5))


def _apply_watermark(base: Image.Image, wm_bytes: bytes) -> Image.Image:
    """Composite the logo, centered, sized to WATERMARK_SCALE of the width."""
    base = base.convert("RGBA")
    target_w = max(1, round(base.width * WATERMARK_SCALE))

    wm = ImageOps.exif_transpose(Image.open(BytesIO(wm_bytes))).convert("RGBA")
    # `contain` lets the small logo upscale toward the target width, while the
    # base height keeps it from ever overflowing the canvas.
    wm = ImageOps.contain(wm, (target_w, base.height), _RESAMPLE)

    # Global opacity: scale the existing alpha channel.
    alpha = wm.getchannel("A").point(lambda a: round(a * WATERMARK_OPACITY))
    wm.putalpha(alpha)

    x = max(0, (base.width - wm.width) // 2)
    y = max(0, (base.height - wm.height) // 2)
    base.alpha_composite(wm, (x, y))
    return base


def _encode(img: Image.Image, fmt: str, quality: int) -> bytes:
    buf = BytesIO()
    if fmt == "jpeg":
        # JPEG has no alpha — flatten onto white.
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    elif fmt == "png":
        if img.mode == "P":
            img = img.convert("RGBA")
        img.save(buf, format="PNG", optimize=True)
    elif fmt == "avif":
        if img.mode == "P":
            img = img.convert("RGBA")
        img.save(buf, format="AVIF", quality=quality)
    else:  # webp
        if img.mode == "P":
            img = img.convert("RGBA")
        img.save(buf, format="WEBP", quality=quality, method=6)
    return buf.getvalue()


def render(
    original: bytes,
    watermark: bytes | None,
    *,
    width: int | None,
    height: int | None,
    quality: int,
    fit: str,
    fmt: str,
) -> bytes:
    """Decode -> resize -> watermark -> encode. Returns the output image bytes."""
    img = Image.open(BytesIO(original))
    img = ImageOps.exif_transpose(img)  # honor camera orientation (rotated phone photos)
    img = _resize(img, width, height, fit)
    if watermark is not None:
        img = _apply_watermark(img, watermark)
    return _encode(img, fmt, quality)
