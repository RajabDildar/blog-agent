import re

from blog_agent.services.markdown_format import (
    normalize_markdown,
)
from blog_agent.services.markdown_parser import (
    get_headings,
)

ATX_HEADING_RE = re.compile(
    r"^(?P<indent> {0,3})"
    r"(?P<marker>#{1,6})"
    r"[ \t]+"
    r"(?P<title>.*?)"
    r"[ \t]*#*[ \t]*$"
)

# Matches  【[Anchor Text](url)】  — full-width bracket around a Markdown link.
_BRACKET_MD_LINK_RE = re.compile(
    r"【\s*(\[[^\]]+\]\([^\)]+\))\s*】"
)

# Matches  【https://...】  — bare URL inside full-width brackets.
_BRACKET_RAW_URL_RE = re.compile(
    r"【\s*(https?://[^\s】\)]+)\s*】"
)

# Matches a footnote definition line at the start of a (possibly stripped) line:
#   [^label]: ...URL...
# Also handles the escaped form  \[^label\]: ...  that some models emit.
_FOOTNOTE_DEF_RE = re.compile(
    r"^\\?\[\^([^\]]+)\\?\]:\s*(.*)$"
)

# Matches a URL inside any surrounding text.
_URL_IN_TEXT_RE = re.compile(r"https?://[^\s\)\>\]\【】]+")


def normalize_citation_artifacts(
    markdown: str,
) -> str:
    """
    Convert common LLM citation formatting artifacts into standard inline
    Markdown links so that `extract_markdown_links()` can detect them.

    Transformations applied in order:

    1. ``【[Anchor Text](url)】`` → ``[Anchor Text](url)``
       (full-width bracket wrapping an already-valid MD link)

    2. ``【https://...】`` → ``[Source](https://...)``
       (bare URL inside full-width brackets)

    3. Section-local footnote definitions + references:
       - Scan lines for ``[^label]: url`` or ``\\[^label\\]: ... url``.
       - Collect label → first URL mapping, then strip those lines.
       - Replace every ``[^label]`` or ``\\[^label\\]`` reference in the
         remaining text with ``[Source](url)``.

    Only section-local footnotes are resolved — definitions that appear in
    the same chunk of text as their references.  This prevents cross-section
    footnote collisions that previously caused MarkdownIt to attribute the
    wrong URL to a section.
    """
    # --- Pass 1: 【[text](url)】 → [text](url) ---
    text = _BRACKET_MD_LINK_RE.sub(r"\1", markdown)

    # --- Pass 2: 【https://...】 → [Source](url) ---
    text = _BRACKET_RAW_URL_RE.sub(
        lambda m: f"[Source]({m.group(1)})", text
    )

    # --- Pass 3: inline footnotes ---
    footnote_urls: dict[str, str] = {}
    kept_lines: list[str] = []

    for line in text.splitlines():
        m = _FOOTNOTE_DEF_RE.match(line.strip())
        if m:
            label = m.group(1)
            content = m.group(2)
            urls = _URL_IN_TEXT_RE.findall(content)
            if urls and label not in footnote_urls:
                footnote_urls[label] = urls[0]
            # Drop the definition line — do not propagate it.
            continue
        kept_lines.append(line)

    text = "\n".join(kept_lines)

    # Replace every in-text reference [^label] or \[^label\] with [Source](url).
    for label, url in footnote_urls.items():
        ref_re = re.compile(
            r"\\?\[\^" + re.escape(label) + r"\\?\]"
        )
        text = ref_re.sub(f"[Source]({url})", text)

    return text


def strip_outer_markdown_fence(
    markdown: str,
) -> str:
    lines = markdown.splitlines()

    if len(lines) < 2:
        return markdown

    first = lines[0].strip().lower()
    last = lines[-1].strip()

    opening_to_closing = {
        "```markdown": "```",
        "```md": "```",
        "~~~markdown": "~~~",
        "~~~md": "~~~",
    }

    expected_closing = opening_to_closing.get(first)

    if expected_closing is None or last != expected_closing:
        return markdown

    return normalize_markdown("\n".join(lines[1:-1]))


def repair_section_structure(
    markdown: str,
    *,
    expected_title: str,
) -> str:
    # First, normalize any LLM citation-formatting artifacts (【url】, footnotes)
    # into standard inline Markdown links so citation_verifier can detect them.
    repaired = normalize_citation_artifacts(markdown)

    repaired = strip_outer_markdown_fence(repaired)

    lines = repaired.splitlines()
    headings = get_headings(repaired)

    first_nonempty_index = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )

    for heading in headings:
        if heading.level > 2:
            continue

        line_index = heading.line - 1

        if line_index < 0 or line_index >= len(lines):
            continue

        match = ATX_HEADING_RE.match(lines[line_index])

        # Leave unusual/setext cases for LLM repair.
        if match is None:
            continue

        is_duplicated_section_heading = (
            line_index == first_nonempty_index
            and heading.text.strip() == expected_title.strip()
        )

        if is_duplicated_section_heading:
            lines[line_index] = ""
            continue

        # Any other H1/H2 inside a section body
        # becomes a subsection.
        lines[line_index] = f"{match.group('indent')}### {heading.text.strip()}"

    return normalize_markdown("\n".join(lines))


def repair_article_structure(
    markdown: str,
) -> str:
    # Article H1/H2 are application-owned.
    # Do not guess their intended structure here.
    return strip_outer_markdown_fence(markdown)
