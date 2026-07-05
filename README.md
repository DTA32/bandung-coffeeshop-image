# bandung-coffeeshop-image

A small **FastAPI** service that serves images from a private **Cloudflare R2**
bucket, **resized and watermarked on the fly** with
[Pillow](https://python-pillow.org/).

The request path is the R2 object key and the transform is driven by query
params, so a single URL like `/cafes/abc/cover.jpg?w=800&format=auto` returns a
ready-to-use, watermarked image at the size and format you ask for. The bucket
stays private — this service is the only thing that reads it.

It runs on an ordinary server/container (no per-request CPU limit) and is built
to sit behind a CDN, so each image variant is only ever transformed once.

## What it does

- Reads the original from R2 over the S3 API; never exposes the bucket publicly.
- Resizes to the requested width/height, never enlarging past the source.
- Stamps a centered watermark (`watermark.png`), with an opt-out list.
- Encodes to WebP / AVIF / JPEG / PNG, negotiating `auto` from the `Accept` header.
- Returns immutable cache headers + an `ETag` so a CDN/browser caches each variant.

## API

The request path **is** the R2 object key. Transform via query params:

| Param            | Meaning                                                           |
| ---------------- | ---------------------------------------------------------------- |
| `width` \| `w`   | target width (px, never enlarges past the source)                |
| `height` \| `h`  | target height (px)                                               |
| `quality` \| `q` | 1–100 (default 82)                                                |
| `fit`            | `scale-down` \| `contain` \| `cover` \| `crop` \| `pad`          |
|                  | default: `cover` when both w & h given, else `scale-down`        |
| `format` \| `f`  | `avif` \| `webp` \| `jpeg` \| `png` \| `auto` (default `webp`)   |

`format=auto` negotiates `avif` vs `webp` from the `Accept` header. Paths on the
`WATERMARK_BYPASS` list are served without a watermark. The param names line up
with what [`unpic-img`](https://unpic.pics/) emits per srcset width.

Example: `GET /cafes/abc/cover.jpg?w=800&q=80&format=auto`

`GET /healthz` returns liveness.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the R2 credentials
```

Create an **R2 API token** (Cloudflare dashboard → R2 → *Manage R2 API Tokens*,
Object Read is enough) and put the Account ID / Access Key / Secret in `.env`.

## Run

The modules in `app/` are flat top-level modules, so put `app/` on the import
path with uvicorn's `--app-dir`:

```bash
# dev (auto-reload)
uvicorn main:app --app-dir app --reload --port 8000

# prod — one worker per CPU (transforms are CPU-bound)
uvicorn main:app --app-dir app --host 0.0.0.0 --port 8000 --workers 4
```

Or with Docker:

```bash
docker build -t bandung-coffeeshop-image .
docker run -p 8000:8000 --env-file .env bandung-coffeeshop-image
```

## Caching — keep the transform off the hot path

A Pillow transform is exactly the kind of CPU work you don't want to repeat per
request, so two layers keep it to **once per image variant**:

1. **CDN in front (recommended).** Put a CDN/edge cache in front of this origin.
   Every response sends `Cache-Control: public, max-age=31536000, immutable`
   plus an `ETag`, so the edge caches each rendered variant and serves repeats
   **without ever hitting this origin** — the transform only runs on a cache
   *miss*. Conditional `If-None-Match` requests get a cheap `304` (no bucket
   read, no transform).

   > Fronting it with Cloudflare? These URLs have no file extension, so add a
   > Cache Rule (*Eligible for cache*) for the host to be sure variants are
   > cached. The bucket itself stays private — this origin is its only reader.

2. **Local disk cache (optional).** Set `CACHE_DIR` to also cache rendered bytes
   on the origin's disk, keyed by the canonical request, so a restart or a cold
   edge POP doesn't re-transform. Leave it empty to rely on the CDN alone.

## Behaviour notes

- Single-dimension requests fill the other axis from the source aspect ratio.
- The watermark is `watermark.png` at the bucket root, sized to 0.4× the
  rendered width, centered, at 0.35 opacity; the bypass list takes exact
  (`a/b.jpg`), folder (`a/`), or wildcard (`a/b-*`) entries.
- Guards: rejects empty keys, `..` traversal, and direct `watermark.png`.
- EXIF orientation is honored so rotated phone photos display upright.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
