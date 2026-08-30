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
    "developers.google.com",
    "docs.github.com",
    "developer.mozilla.org",
    "kubernetes.io",
    "docs.docker.com",
}


OFFICIAL_ORGANIZATION_GITHUB = {
    "langchain-ai",
    "google",
    "openai",
    "modelcontextprotocol",
    "microsoft",
    "cloudflare",
}


GOVERNMENT_SUFFIXES = (
    ".gov",
    ".gov.uk",
)


ACADEMIC_SUFFIXES = (".edu",)


STANDARDS_DOMAINS = {
    "ietf.org",
    "w3.org",
    "iso.org",
}


REPUTABLE_INDUSTRY_DOMAINS = {
    "arxiv.org",
    "nature.com",
    "mit.edu",
    "stanford.edu",
}


LOW_QUALITY_DOMAINS = {
    "medium.com",
    "dev.to",
    "towardsdatascience.com",
    "substack.com",
}


VENDOR_BLOG_INDICATORS = (
    "/blog/",
    "/resources/",
    "/insights/",
)


GITHUB_DOMAIN = "github.com"


def _hostname(url: str) -> str:
    parsed = urlparse(url)

    return (parsed.hostname or "").lower()


def _github_owner(url: str) -> str | None:
    parsed = urlparse(url)

    if parsed.hostname != GITHUB_DOMAIN:
        return None

    parts = [part for part in parsed.path.split("/") if part]

    if len(parts) < 1:
        return None

    return parts[0].lower()


def classify_source(url: str) -> SourceQuality:
    """
    Deterministically classify source authority.

    This metadata is used for evidence ranking.
    It does not prove source correctness.
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
        owner = _github_owner(url)

        if owner in OFFICIAL_ORGANIZATION_GITHUB:
            return SourceQuality(
                source_type="github_repository",
                authority_score=0.9,
            )

        return SourceQuality(
            source_type="github_repository",
            authority_score=0.75,
        )

    if hostname in LOW_QUALITY_DOMAINS:
        return SourceQuality(
            source_type="unknown",
            authority_score=0.25,
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
