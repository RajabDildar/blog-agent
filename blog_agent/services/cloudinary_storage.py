"""Cloudinary image storage service for portfolio-scale durable image management."""
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import cloudinary
import cloudinary.uploader
import cloudinary.utils

from apps.api.config import get_settings


def is_cloudinary_configured() -> bool:
    """Checks if valid Cloudinary credentials are available in environment/settings."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("FORCE_TEST_CLOUDINARY"):
        return False

    settings = get_settings()
    cname = settings.CLOUDINARY_CLOUD_NAME or ""
    ckey = settings.CLOUDINARY_API_KEY or ""
    csecret = settings.CLOUDINARY_API_SECRET or ""
    if (
        cname and ckey and csecret
        and not cname.startswith("your_")
        and not ckey.startswith("your_")
        and not cname.startswith("mock")
    ):
        return True
    c_url = os.environ.get("CLOUDINARY_URL", "")
    if c_url and not c_url.startswith("your_") and "your_" not in c_url:
        return True
    return False


def _configure_cloudinary() -> None:
    """Initializes Cloudinary SDK configuration from settings or environment."""
    settings = get_settings()
    if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET:
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )


def format_cloudinary_public_id(run_id: str, filename: str) -> str:
    """
    Generates a deterministic, collision-safe Cloudinary public ID.
    Format: blog-agent/runs/{run_id}/images/{filename_stem}
    """
    filename_stem = Path(filename).stem
    return f"blog-agent/runs/{run_id}/images/{filename_stem}"


def upload_run_image(
    *,
    run_id: str,
    filename: str,
    image_bytes: bytes,
) -> Dict[str, Any]:
    """
    Uploads an image binary to Cloudinary Free using deterministic public ID.
    Returns metadata dict for inclusion in article_assets JSON manifest.
    """
    if not image_bytes:
        raise ValueError(f"Cannot upload empty image bytes for {filename}")

    _configure_cloudinary()
    public_id = format_cloudinary_public_id(run_id, filename)

    try:
        res = cloudinary.uploader.upload(
            image_bytes,
            public_id=public_id,
            overwrite=True,
            resource_type="image",
            type="authenticated",
        )
    except Exception as exc:
        raise RuntimeError(f"Cloudinary upload failed for public_id {public_id}: {exc}") from exc

    return {
        "filename": filename,
        "public_id": res.get("public_id", public_id),
        "asset_id": res.get("asset_id", ""),
        "format": res.get("format", Path(filename).suffix.lstrip(".")),
        "width": res.get("width"),
        "height": res.get("height"),
        "bytes": res.get("bytes", len(image_bytes)),
    }


def generate_signed_image_url(public_id: str) -> str:
    """
    Generates a server-side signed delivery URL for private/authenticated Cloudinary image access.
    Does not expose API secrets to the client.
    """
    _configure_cloudinary()
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        type="authenticated",
        sign_url=True,
        secure=True,
        resource_type="image",
    )
    return url


def delete_cloudinary_assets(public_ids: List[str]) -> None:
    """Deletes uploaded Cloudinary assets by public IDs."""
    if not public_ids:
        return
    _configure_cloudinary()
    for pid in public_ids:
        try:
            cloudinary.uploader.destroy(pid, type="authenticated", resource_type="image")
        except Exception:
            # Best-effort deletion
            pass
