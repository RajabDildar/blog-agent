"""Gallery router for public technical articles."""
from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db
from apps.api.schemas.runs import GalleryItemResponse
from apps.api.services.run_service import get_gallery, get_featured

router = APIRouter(tags=["gallery"])


def _format_gallery_item(run) -> GalleryItemResponse:
    item = GalleryItemResponse.model_validate(run)
    item.article_url = f"/articles/{run.id}"
    return item


@router.get("/gallery", response_model=List[GalleryItemResponse])
def list_gallery_articles(
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    limit: int = 12,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Returns public, completed articles published to the community gallery."""
    calc_limit = min(page_size, 50) if page_size is not None else min(limit, 50)
    calc_offset = (max(page, 1) - 1) * calc_limit if page is not None else offset
    articles = get_gallery(db, limit=calc_limit, offset=calc_offset)
    return [_format_gallery_item(a) for a in articles]


@router.get("/featured", response_model=List[GalleryItemResponse])
def list_featured_articles(
    limit: int = 6,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Returns curated featured articles from the gallery (max 6 for v3)."""
    calc_limit = min(limit, 6)
    articles = get_featured(db, limit=calc_limit, offset=offset)
    return [_format_gallery_item(a) for a in articles]
