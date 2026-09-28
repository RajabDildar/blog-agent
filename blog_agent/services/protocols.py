"""Core service protocols for article repository and image storage abstractions."""
from typing import Protocol, runtime_checkable, Any, Optional, Dict, List


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
        assets: List[Dict[str, Any]],
    ) -> None:
        """Persists final article Markdown, excerpt, and asset manifest."""
        ...

    def get_article(self, run_id: str) -> Optional[Dict[str, Any]]:
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
        alt_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Uploads an image binary and returns the asset manifest entry."""
        ...

    def verify_image(self, asset: Dict[str, Any]) -> bool:
        """Verifies that the uploaded asset exists and is accessible."""
        ...

    def delete_images(self, public_ids: List[str]) -> None:
        """Deletes assets identified by their public IDs."""
        ...
