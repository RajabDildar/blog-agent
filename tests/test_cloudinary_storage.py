"""Unit tests for Cloudinary storage service, URL formatting, and signed delivery URL generation."""
import pytest
from unittest.mock import patch, MagicMock

from blog_agent.services.cloudinary_storage import (
    is_cloudinary_configured,
    format_cloudinary_public_id,
    upload_run_image,
    generate_signed_image_url,
    delete_cloudinary_assets,
)


def test_format_cloudinary_public_id():
    pid = format_cloudinary_public_id("run-1234", "architecture_diagram.png")
    assert pid == "blog-agent/runs/run-1234/images/architecture_diagram"


def test_is_cloudinary_configured_env(monkeypatch):
    monkeypatch.setenv("FORCE_TEST_CLOUDINARY", "1")
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://123:abc@cloud")
    assert is_cloudinary_configured() is True


def test_upload_run_image_empty_bytes():
    with pytest.raises(ValueError, match="Cannot upload empty image bytes"):
        upload_run_image(run_id="run-1", filename="test.png", image_bytes=b"")


@patch("cloudinary.uploader.upload")
def test_upload_run_image_success(mock_upload):
    mock_upload.return_value = {
        "public_id": "blog-agent/runs/run-1/images/test",
        "asset_id": "asset-999",
        "format": "png",
        "width": 800,
        "height": 600,
        "bytes": 1024,
    }

    res = upload_run_image(run_id="run-1", filename="test.png", image_bytes=b"fake-png-data")
    assert res["filename"] == "test.png"
    assert res["public_id"] == "blog-agent/runs/run-1/images/test"
    assert res["asset_id"] == "asset-999"
    assert res["format"] == "png"
    assert res["width"] == 800
    assert res["height"] == 600


@patch("cloudinary.utils.cloudinary_url")
def test_generate_signed_image_url(mock_url):
    mock_url.return_value = ("https://res.cloudinary.com/demo/image/authenticated/s--sig--/v1/test.png", {})
    url = generate_signed_image_url("blog-agent/runs/run-1/images/test")
    assert "https://res.cloudinary.com" in url
    mock_url.assert_called_once_with(
        "blog-agent/runs/run-1/images/test",
        type="authenticated",
        sign_url=True,
        secure=True,
        resource_type="image",
    )


@patch("cloudinary.uploader.destroy")
def test_delete_cloudinary_assets(mock_destroy):
    delete_cloudinary_assets(["pid-1", "pid-2"])
    assert mock_destroy.call_count == 2
