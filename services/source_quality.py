from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlparse

from schemas.models import (
    OFFICIAL_PRIMARY_SOURCE_TYPES,
    ResearchEvidence,
    SourceType,
)


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


def _path(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path.lower()


def _github_owner(url: str) -> str | None:
    parsed = urlparse(url)

    if parsed.hostname != GITHUB_DOMAIN:
        return None

    parts = [part for part in parsed.path.split("/") if part]

    if len(parts) < 1:
        return None

    return parts[0].lower()


def is_github_official_organization(url: str) -> bool:
    """Return True if the GitHub URL is from an official organization."""
    owner = _github_owner(url)
    return owner is not None and owner in OFFICIAL_ORGANIZATION_GITHUB


def is_official_primary_source(
    *,
    source_type: SourceType,
    url: str,
) -> bool:
    """
    Deterministic check: is this source an official/primary source?

    Separates source-authority classification from claim-support strength.
    Claim support (direct/indirect/weak) is an orthogonal LLM judgement.
    """
    if source_type in OFFICIAL_PRIMARY_SOURCE_TYPES:
        return True

    if source_type == "github_repository" and is_github_official_organization(url):
        return True

    return False


def classify_source(url: str) -> SourceQuality:
    """
    Deterministically classify source authority.

    This metadata is used for evidence ranking.
    It does not prove source correctness.
    It does not describe claim-support strength.
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
            source_type="vendor_blog",
            authority_score=0.25,
        )

    if hostname in REPUTABLE_INDUSTRY_DOMAINS:
        return SourceQuality(
            source_type="reputable_industry_source",
            authority_score=0.85,
        )

    if any(indicator in _path(url) for indicator in VENDOR_BLOG_INDICATORS):
        return SourceQuality(
            source_type="vendor_blog",
            authority_score=0.5,
        )

    return SourceQuality(
        source_type="unknown",
        authority_score=0.3,
    )


@dataclass(frozen=True)
class SourceRatios:
    official_source_ratio: float
    weak_source_ratio: float
    unknown_source_ratio: float
    official_count: int
    weak_count: int
    unknown_count: int
    total_count: int


DEFAULT_WEAK_AUTHORITY_THRESHOLD = 0.5

WEAK_SOURCE_CATEGORIES: frozenset[SourceType] = frozenset({
    "vendor_blog",
    "unknown",
})


def _is_weak_source(
    *,
    source_type: SourceType,
    authority_score: float,
    weak_authority_threshold: float,
) -> bool:
    if source_type in WEAK_SOURCE_CATEGORIES:
        return True

    if authority_score < weak_authority_threshold:
        return True

    return False


def compute_source_ratios(
    evidence_list: list[ResearchEvidence],
    *,
    weak_authority_threshold: float = DEFAULT_WEAK_AUTHORITY_THRESHOLD,
) -> SourceRatios:
    """
    Compute documented deterministic source ratios.

    - official_source_ratio: fraction that is an official/primary source
      (official docs, government, academic papers, standards docs,
      official company announcements, official-org GitHub repos).
    - weak_source_ratio: fraction in explicit weak categories
      (vendor_blog, unknown) OR authority_score below the threshold.
    - unknown_source_ratio: fraction explicitly classified as unknown.
    """
    total = len(evidence_list)

    if total == 0:
        return SourceRatios(
            official_source_ratio=0.0,
            weak_source_ratio=0.0,
            unknown_source_ratio=0.0,
            official_count=0,
            weak_count=0,
            unknown_count=0,
            total_count=0,
        )

    official_count = 0
    weak_count = 0
    unknown_count = 0

    for item in evidence_list:
        if is_official_primary_source(
            source_type=item.source_type,
            url=item.url,
        ):
            official_count += 1

        if _is_weak_source(
            source_type=item.source_type,
            authority_score=item.authority_score,
            weak_authority_threshold=weak_authority_threshold,
        ):
            weak_count += 1

        if item.source_type == "unknown":
            unknown_count += 1

    return SourceRatios(
        official_source_ratio=official_count / total,
        weak_source_ratio=weak_count / total,
        unknown_source_ratio=unknown_count / total,
        official_count=official_count,
        weak_count=weak_count,
        unknown_count=unknown_count,
        total_count=total,
    )


def summarize_source_types(
    evidence_list: list[ResearchEvidence],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in evidence_list:
        counts[item.source_type] += 1
    return dict(counts)
