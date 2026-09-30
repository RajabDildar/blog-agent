"""Core service protocols for article repository and image storage abstractions."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ArticleRepository(Protocol):
    """Abstraction for persisting and reading durable article content and manifests."""

    def save_article(
        self,
        *,
        run_id: str,
        title: str,
        markdown: str,
        excerpt: str,
        assets: list[dict[str, Any]],
    ) -> None:
        """Persists final article Markdown, excerpt, and asset manifest."""
        ...

    def get_article(self, run_id: str) -> dict[str, Any] | None:
        """Retrieves article content and metadata for run_id."""
        ...


@runtime_checkable
class ImageStorage(Protocol):
    """Abstraction for durable image artifact storage and delivery."""

    def upload_image(
        self,
        *,
        run_id: str,
        filename: str,
        image_bytes: bytes,
        alt_text: str | None = None,
    ) -> dict[str, Any]:
        """Uploads an image binary and returns the asset manifest entry."""
        ...

    def verify_image(self, asset: dict[str, Any]) -> bool:
        """Verifies that the uploaded asset exists and is accessible."""
        ...

    def delete_images(self, public_ids: list[str]) -> None:
        """Deletes assets identified by their public IDs."""
        ...
