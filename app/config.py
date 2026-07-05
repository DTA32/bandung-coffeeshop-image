"""Runtime configuration, loaded from the environment (or a local .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- R2 (S3-compatible) connection -------------------------------------
    # R2 exposes an S3 API at https://<account_id>.r2.cloudflarestorage.com.
    # Create an R2 API token (Access Key ID + Secret) in the Cloudflare dash.
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "bdgcafe"
    # Override the derived endpoint if you front R2 with something else.
    r2_endpoint: str | None = None

    # --- Image serving ------------------------------------------------------
    # Logo object at the bucket root; also blocked from direct access.
    watermark_key: str = "watermark.png"
    # Comma/newline-separated keys served WITHOUT a watermark.
    #   exact "a/b.jpg" | folder "a/" (prefix) | wildcard "a/b-*" (prefix)
    watermark_bypass: str = ""

    # --- Cache --------------------------------------------------------------
    # Optional on-disk cache for rendered output (keyed by the canonical
    # request). Leave empty to disable and rely on a CDN in front instead.
    cache_dir: str | None = None

    @property
    def endpoint_url(self) -> str:
        if self.r2_endpoint:
            return self.r2_endpoint
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
