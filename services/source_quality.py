from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from schemas.models import SourceType


@dataclass(frozen=True)
class SourceQuality:
    source_type: SourceType
    authority_score: float


OFFICIAL_DOC_DOMAINS = {
    "docs.python.org",
    "fastapi.tiangolo.com",
    "docs.langchain.com",
    "ai.google.dev",
    "platform.openai.com",
}


GOVERNMENT_SUFFIXES = (
    ".gov",
    ".gov.uk",
)


ACADEMIC_SUFFIXES = (".edu",)


STANDARDS_DOMAINS = {
    "ietf.org",
    "w3.org",
}


GITHUB_DOMAIN = "github.com"


REPUTABLE_INDUSTRY_DOMAINS = {
    "arxiv.org",
    "nature.com",
    "mit.edu",
    "stanford.edu",
}


VENDOR_BLOG_INDICATORS = (
    "/blog/",
    "/resources/",
    "/insights/",
)


def _hostname(url: str) -> str:
    parsed = urlparse(url)

    return (parsed.hostname or "").lower()


def classify_source(url: str) -> SourceQuality:
    """
    Classify source authority using deterministic URL heuristics.

    This is intentionally conservative.
    It provides metadata for ranking, not final truth.
    """

    hostname = _hostname(url)

    if not hostname:
        return SourceQuality(
            source_type="unknown",
            authority_score=0.2,
        )

    if hostname in OFFICIAL_DOC_DOMAINS:
        return SourceQuality(
            source_type="official_documentation",
            authority_score=0.95,
        )

    if hostname.endswith(GOVERNMENT_SUFFIXES):
        return SourceQuality(
            source_type="government_source",
            authority_score=0.95,
        )

    if hostname.endswith(ACADEMIC_SUFFIXES):
        return SourceQuality(
            source_type="academic_paper",
            authority_score=0.9,
        )

    if hostname in STANDARDS_DOMAINS:
        return SourceQuality(
            source_type="standards_document",
            authority_score=0.95,
        )

    if hostname == GITHUB_DOMAIN:
        return SourceQuality(
            source_type="github_repository",
            authority_score=0.85,
        )

    if hostname in REPUTABLE_INDUSTRY_DOMAINS:
        return SourceQuality(
            source_type="reputable_industry_source",
            authority_score=0.85,
        )

    if any(indicator in url.lower() for indicator in VENDOR_BLOG_INDICATORS):
        return SourceQuality(
            source_type="vendor_blog",
            authority_score=0.5,
        )

    return SourceQuality(
        source_type="unknown",
        authority_score=0.3,
    )
