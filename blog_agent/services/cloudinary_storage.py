"""Cloudinary image storage service for portfolio-scale durable image management."""

import logging
import os
from pathlib import Path
from typing import Any

import cloudinary
import cloudinary.uploader
import cloudinary.utils

from blog_agent.config.settings import (
    CLOUDINARY_API_KEY,
    CLOUDINARY_API_SECRET,
    CLOUDINARY_CLOUD_NAME,
)

logger = logging.getLogger("blog_agent.cloudinary_storage")


def is_cloudinary_configured() -> bool:
    """Checks if valid Cloudinary credentials are available in environment/settings."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get(
        "FORCE_TEST_CLOUDINARY"
    ):
        return False

    cname = os.environ.get("CLOUDINARY_CLOUD_NAME", CLOUDINARY_CLOUD_NAME) or ""
    ckey = os.environ.get("CLOUDINARY_API_KEY", CLOUDINARY_API_KEY) or ""
    csecret = os.environ.get("CLOUDINARY_API_SECRET", CLOUDINARY_API_SECRET) or ""
    if (
        cname
        and ckey
        and csecret
        and not cname.startswith("your_")
        and not ckey.startswith("your_")
        and not cname.startswith("mock")
    ):
        return True
    c_url = os.environ.get("CLOUDINARY_URL", "")
    return bool(c_url and not c_url.startswith("your_") and "your_" not in c_url)


def _configure_cloudinary() -> None:
    """Initializes Cloudinary SDK configuration from settings or environment."""
    cname = os.environ.get("CLOUDINARY_CLOUD_NAME", CLOUDINARY_CLOUD_NAME)
    ckey = os.environ.get("CLOUDINARY_API_KEY", CLOUDINARY_API_KEY)
    csecret = os.environ.get("CLOUDINARY_API_SECRET", CLOUDINARY_API_SECRET)
    if cname and ckey and csecret:
        cloudinary.config(
            cloud_name=cname,
            api_key=ckey,
            api_secret=csecret,
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
    alt_text: str | None = None,
) -> dict[str, Any]:
    """
    Uploads an image binary to Cloudinary Free using deterministic public ID.
    Verifies that the uploaded asset is non-empty.
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
        raise RuntimeError(
            f"Cloudinary upload failed for public_id {public_id}: {exc}"
        ) from exc

    if not res or not res.get("public_id"):
        raise RuntimeError(
            f"Cloudinary upload verification failed for {public_id}: response missing public_id"
        )

    return {
        "filename": filename,
        "public_id": res.get("public_id", public_id),
        "asset_id": res.get("asset_id", ""),
        "format": res.get("format", Path(filename).suffix.lstrip(".")),
        "width": res.get("width"),
        "height": res.get("height"),
        "bytes": res.get("bytes", len(image_bytes)),
        "alt_text": alt_text,
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


def delete_cloudinary_assets(public_ids: list[str]) -> None:
    """Deletes uploaded Cloudinary assets by public IDs."""
    if not public_ids:
        return
    _configure_cloudinary()
    for pid in public_ids:
        try:
            cloudinary.uploader.destroy(
                pid, type="authenticated", resource_type="image"
            )
        except Exception as exc:  # noqa: BLE001 - Asset deletion is best-effort and logged.
            logger.warning(f"Failed to delete Cloudinary asset '{pid}': {exc}")


class CloudinaryImageStorage:
    """ImageStorage protocol implementation backed by Cloudinary."""

    def upload_image(
        self,
        *,
        run_id: str,
        filename: str,
        image_bytes: bytes,
        alt_text: str | None = None,
    ) -> dict[str, Any]:
        return upload_run_image(
            run_id=run_id,
            filename=filename,
            image_bytes=image_bytes,
            alt_text=alt_text,
        )

    def verify_image(self, asset: dict[str, Any]) -> bool:
        return bool(asset.get("public_id") and asset.get("bytes", 0) > 0)

    def delete_images(self, public_ids: list[str]) -> None:
        delete_cloudinary_assets(public_ids)
