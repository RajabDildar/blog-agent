"""Gallery router for public technical articles."""
from typing import List
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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Returns public, completed articles published to the community gallery."""
    articles = get_gallery(db, limit=limit, offset=offset)
    return [_format_gallery_item(a) for a in articles]


@router.get("/featured", response_model=List[GalleryItemResponse])
def list_featured_articles(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Returns curated featured articles from the gallery."""
    articles = get_featured(db, limit=limit, offset=offset)
    return [_format_gallery_item(a) for a in articles]
