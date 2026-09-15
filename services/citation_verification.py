from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from markdown_it import MarkdownIt

from schemas.models import (
    EditorialIssue,
    ResearchEvidence,
    Task,
)
from services.markdown_parser import get_headings

# These parameters are commonly used for analytics/tracking and do not identify a different underlying resource.
TRACKING_PARAMETER_PREFIXES = ("utm_",)

TRACKING_PARAMETER_NAMES = {
    "fbclid",
    "gclid",
}


@dataclass(frozen=True)
class ExtractedLink:
    url: str
    section_title: str | None


def normalize_url(url: str) -> str:
    """
    Normalize URLs for deterministic evidence membership comparison.

    Policy:
    - lowercase scheme and host
    - remove fragments
    - treat trailing slash variants as equivalent for non-root paths
    - remove approved tracking parameters
    - preserve path case, query parameter values, ports, and non-tracking
      query parameters
    """

    parsed = urlsplit(url.strip())

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()

    if not hostname:
        return url.strip()

    netloc = hostname

    if parsed.port is not None:
        netloc = f"{hostname}:{parsed.port}"

    path = parsed.path

    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    query_items = parse_qsl(
        parsed.query,
        keep_blank_values=True,
    )

    filtered_query_items = [
        (key, value) for key, value in query_items if not _is_tracking_parameter(key)
    ]

    query = urlencode(
        filtered_query_items,
        doseq=True,
    )

    return urlunsplit(
        (
            scheme,
            netloc,
            path,
            query,
            "",
        )
    )


def _is_tracking_parameter(
    parameter_name: str,
) -> bool:
    normalized_name = parameter_name.lower()

    return normalized_name in TRACKING_PARAMETER_NAMES or normalized_name.startswith(
        TRACKING_PARAMETER_PREFIXES,
    )


def extract_markdown_links(
    markdown: str,
) -> list[ExtractedLink]:
    parser = MarkdownIt()

    links: list[ExtractedLink] = []
    current_section_title: str | None = None
    reading_h2 = False

    for token in parser.parse(markdown):
        if token.type == "heading_open" and token.tag == "h2":
            reading_h2 = True
            continue

        if token.type == "heading_close" and token.tag == "h2":
            reading_h2 = False
            continue

        if token.type != "inline":
            continue

        if reading_h2:
            current_section_title = _extract_text(
                token.children or [],
            )
            continue

        if not token.children:
            continue

        for child in token.children:
            if child.type != "link_open":
                continue

            href = child.attrGet("href")

            if href:
                links.append(
                    ExtractedLink(
                        url=href,
                        section_title=current_section_title,
                    )
                )

    return links


def _extract_text(
    tokens: Iterable,
) -> str:
    return "".join(
        token.content
        for token in tokens
        if token.type
        in {
            "text",
            "code_inline",
        }
    ).strip()


def _task_evidence_urls(
    task: Task,
    evidence_by_id: dict[int, ResearchEvidence],
) -> set[str]:
    return {
        normalize_url(
            evidence_by_id[evidence_id].url,
        )
        for evidence_id in task.evidence_refs
        if evidence_id in evidence_by_id
    }


def _task_evidence_by_url(
    task: Task,
    evidence_by_id: dict[int, ResearchEvidence],
) -> dict[str, ResearchEvidence]:
    return {
        normalize_url(item.url): item
        for evidence_id in task.evidence_refs
        if (item := evidence_by_id.get(evidence_id)) is not None
    }


def verify_evidence_quality(
    *,
    tasks: list[Task],
    evidence: list[ResearchEvidence],
) -> list[EditorialIssue]:
    evidence_by_id = {item.id: item for item in evidence}

    issues: list[EditorialIssue] = []

    for task in tasks:
        for evidence_id in task.evidence_refs:
            item = evidence_by_id.get(evidence_id)

            if item is None:
                continue

            if item.authority_score < 0.5:
                issues.append(
                    EditorialIssue(
                        task_id=task.id,
                        category="citation",
                        severity="medium",
                        problem=("Evidence source has low authority."),
                        correction=(
                            "Prefer official documentation, "
                            "primary sources, or stronger evidence."
                        ),
                    )
                )

            if item.support_strength == "weak":
                issues.append(
                    EditorialIssue(
                        task_id=task.id,
                        category="unsupported_claim",
                        severity="medium",
                        problem=("Evidence only weakly supports the associated claim."),
                        correction=("Narrow the claim or replace the evidence."),
                    )
                )

            if item.freshness_warning:
                issues.append(
                    EditorialIssue(
                        task_id=task.id,
                        category="citation",
                        severity="medium",
                        problem=f"Evidence freshness warning: {item.freshness_warning}",
                        correction=(
                            "Verify claim is still current or soften/qualify "
                            "the statement to reflect its source date."
                        ),
                    )
                )

    return issues


def verify_citations(
    *,
    markdown: str,
    tasks: list[Task],
    evidence: list[ResearchEvidence],
) -> list[EditorialIssue]:
    """
    Verify article citations against task-scoped research evidence and
    the application-owned final ## Sources section.

    Returns editorial issues rather than raising for unsupported or missing
    citations so the existing editorial revision flow can attempt correction.
    """

    evidence_by_id = {item.id: item for item in evidence}
    global_allowed_urls = {
        normalize_url(item.url): item for item in evidence
    }

    headings = get_headings(markdown)
    h2_headings = [h.text.strip() for h in headings if h.level == 2]

    issues: list[EditorialIssue] = []

    research_used = any(bool(task.evidence_refs) for task in tasks)
    sources_count = sum(1 for title in h2_headings if title == "Sources")

    if research_used:
        if sources_count == 0:
            issues.append(
                EditorialIssue(
                    task_id=None,
                    category="citation",
                    severity="high",
                    problem=(
                        "Article uses research evidence but is missing "
                        "a final ## Sources section."
                    ),
                    correction=(
                        "Append a ## Sources section containing links to "
                        "all referenced research evidence."
                    ),
                )
            )
        elif sources_count > 1:
            issues.append(
                EditorialIssue(
                    task_id=None,
                    category="citation",
                    severity="high",
                    problem=f"Expected exactly one ## Sources section, but found {sources_count}.",
                    correction="Ensure there is only one ## Sources section at the end of the article.",
                )
            )
        elif h2_headings and h2_headings[-1] != "Sources":
            issues.append(
                EditorialIssue(
                    task_id=None,
                    category="citation",
                    severity="high",
                    problem="The ## Sources section must be the final H2 section of the article.",
                    correction="Move the ## Sources section to the end of the article.",
                )
            )
    else:
        if sources_count > 0:
            issues.append(
                EditorialIssue(
                    task_id=None,
                    category="citation",
                    severity="high",
                    problem=(
                        "A ## Sources section is not allowed in a closed-book "
                        "article with no research evidence."
                    ),
                    correction="Remove the ## Sources section from closed-book articles.",
                )
            )

    links_by_section: dict[
        str,
        list[str],
    ] = {}

    for link in extract_markdown_links(markdown):
        if link.section_title is None:
            continue

        links_by_section.setdefault(
            link.section_title.strip(),
            [],
        ).append(link.url)

    if "Sources" in links_by_section:
        for url in links_by_section["Sources"]:
            norm_url = normalize_url(url)
            if norm_url not in global_allowed_urls:
                issues.append(
                    EditorialIssue(
                        task_id=None,
                        category="citation",
                        severity="high",
                        problem=(
                            "The Sources section contains a URL not backed "
                            f"by research evidence: {url}"
                        ),
                        correction=(
                            "Remove or replace this URL in the Sources section "
                            "with an evidence-backed URL."
                        ),
                    )
                )

    for task in tasks:
        section_links = links_by_section.get(
            task.title.strip(),
            [],
        )

        allowed_urls = _task_evidence_urls(
            task,
            evidence_by_id,
        )

        if task.requires_citations and not section_links:
            issues.append(
                EditorialIssue(
                    task_id=task.id,
                    category="citation",
                    severity="high",
                    problem=(
                        "This section requires citations but "
                        "contains no citation links."
                    ),
                    correction=(
                        "Add citation links using only URLs from "
                        "the evidence assigned to this task."
                    ),
                )
            )

        for url in section_links:
            normalized_url = normalize_url(url)

            if normalized_url in allowed_urls:
                continue

            issues.append(
                EditorialIssue(
                    task_id=task.id,
                    category="citation",
                    severity="high",
                    problem=(
                        "The citation URL is not backed by evidence "
                        f"assigned to this task: {url}"
                    ),
                    correction=(
                        "Replace or remove this citation. Use only "
                        "evidence-backed URLs assigned to the task."
                    ),
                )
            )

    return issues
