# Pytest bootstrap.
#
# The app/ modules import each other as plain top-level modules (flat layout:
# `import images`, `from config import ...`), so app/ must be on the import path
# before any test imports `main` or `params`.
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "app"))

# Hermetic dummy R2 settings, set *before* the app is imported so the boto3
# client constructs with a valid endpoint and tests never touch a real bucket
# (the route tests monkeypatch the R2 calls themselves).
os.environ.setdefault("R2_ENDPOINT", "https://test.r2.cloudflarestorage.com")
os.environ.setdefault("R2_ACCESS_KEY_ID", "test")
os.environ.setdefault("R2_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("R2_BUCKET", "test-bucket")
os.environ.setdefault("WATERMARK_BYPASS", "")
os.environ.setdefault("CACHE_DIR", "")  # NullCache — no disk writes in tests
