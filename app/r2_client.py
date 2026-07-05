"""Thin wrapper over the R2 (S3-compatible) bucket.

boto3 is synchronous and blocking — that's fine here because the FastAPI route
that uses it is a plain `def`, so Starlette runs it in a worker threadpool and
the event loop is never blocked.
"""

import threading

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from config import Settings


class R2Client:
    def __init__(self, settings: Settings):
        self._bucket = settings.r2_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",  # R2 ignores the region but boto3 wants one
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def get_object(self, key: str) -> bytes | None:
        """Full object bytes, or None when the key does not exist."""
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read()
        except ClientError as err:
            code = err.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404", "NoSuchBucket"):
                return None
            raise


class WatermarkCache:
    """Caches the watermark bytes for the process.

    The logo changes about never, so re-fetching it from R2 on every request
    would be pure waste. Loaded lazily, thread-safe.
    """

    def __init__(self, client: R2Client, key: str):
        self._client = client
        self._key = key
        self._lock = threading.Lock()
        self._loaded = False
        self._bytes: bytes | None = None

    def get(self) -> bytes | None:
        if self._loaded:
            return self._bytes
        with self._lock:
            if not self._loaded:
                self._bytes = self._client.get_object(self._key)
                self._loaded = True
        return self._bytes
