"""
Regression tests for services.markdown_repair.normalize_citation_artifacts()
and its integration inside repair_section_structure().

Covers the LLM citation-formatting artifacts that caused sections to fail
citation_verifier with "This section requires citations but contains no
citation links":

1. Full-width bracket raw URL: \u3010https://...\u3011
2. Full-width bracket around a Markdown link: \u3010[Title](url)\u3011
3. Section-local footnote definition + reference: [^1]: url / [^1]
4. Escaped footnote definition: \\[^1\\]: url / \\[^1\\]
5. Multiple footnote labels
6. No-op on clean Markdown (idempotency)
7. Integration via repair_section_structure -- verify that links survive
   the full repair pipeline and are extractable by extract_markdown_links().
"""

from services.citation_verification import extract_markdown_links
from services.markdown_repair import (
    normalize_citation_artifacts,
    repair_section_structure,
)


class TestNormalizeBracketRawUrl:
    """Convert \u3010https://...\u3011 to [Source](https://...)."""

    def test_converts_bracket_raw_url_to_markdown_link(self):
        md = "Data shows a 40% rise\u3010https://example.com/report\u3011."
        result = normalize_citation_artifacts(md)
        assert "[Source](https://example.com/report)" in result
        assert "\u3010" not in result
        assert "\u3011" not in result

    def test_converts_bracket_raw_url_with_surrounding_whitespace(self):
        md = "Something\u3010 https://example.com \u3011happened."
        result = normalize_citation_artifacts(md)
        assert "[Source](https://example.com)" in result
        assert "\u3010" not in result

    def test_converts_multiple_bracket_raw_urls(self):
        md = (
            "First claim\u3010https://a.com\u3011 and "
            "second claim\u3010https://b.com\u3011."
        )
        result = normalize_citation_artifacts(md)
        assert "[Source](https://a.com)" in result
        assert "[Source](https://b.com)" in result


class TestNormalizeBracketMdLink:
    """\u3010[Anchor Text](url)\u3011 strips to [Anchor Text](url)."""

    def test_strips_full_width_brackets_from_md_link(self):
        md = "According to \u3010[Report Title](https://example.com/report)\u3011, X grew."
        result = normalize_citation_artifacts(md)
        assert "[Report Title](https://example.com/report)" in result
        assert "\u3010" not in result
        assert "\u3011" not in result

    def test_strips_bracket_md_link_with_inner_whitespace(self):
        md = "See \u3010 [Title](https://a.com) \u3011 for details."
        result = normalize_citation_artifacts(md)
        assert "[Title](https://a.com)" in result
        assert "\u3010" not in result


class TestNormalizeFootnoteDefinitions:
    """
    [^1]: https://...  /  [^1]  ->  [Source](https://...)
    Footnote definition lines are dropped from the output.
    """

    def test_inline_footnote_ref_replaced_with_link(self):
        md = (
            "The report[^1] found key findings.\n"
            "\n"
            "[^1]: https://example.com/report\n"
        )
        result = normalize_citation_artifacts(md)
        assert "[Source](https://example.com/report)" in result
        assert "[^1]: https://example.com/report" not in result

    def test_footnote_definition_line_is_dropped(self):
        md = "Text[^ref].\n\n[^ref]: https://example.com\n"
        result = normalize_citation_artifacts(md)
        assert "[^ref]: https://example.com" not in result
        assert "[Source](https://example.com)" in result

    def test_escaped_footnote_definition_and_reference(self):
        md = (
            "According to \\[^1\\], this is true.\n"
            "\n"
            "\\[^1\\]: https://example.com/src\n"
        )
        result = normalize_citation_artifacts(md)
        assert "[Source](https://example.com/src)" in result
        assert "\\[^1\\]:" not in result

    def test_multiple_footnote_labels_resolved_independently(self):
        md = (
            "First[^a] and second[^b].\n"
            "\n"
            "[^a]: https://source-a.com\n"
            "[^b]: https://source-b.com\n"
        )
        result = normalize_citation_artifacts(md)
        assert "[Source](https://source-a.com)" in result
        assert "[Source](https://source-b.com)" in result
        assert "[^a]:" not in result
        assert "[^b]:" not in result

    def test_footnote_with_text_before_url_uses_first_url(self):
        md = (
            "Claim[^1].\n"
            "\n"
            "[^1]: Author, Title, 2026. https://example.com/paper\n"
        )
        result = normalize_citation_artifacts(md)
        assert "[Source](https://example.com/paper)" in result

    def test_footnote_definition_without_url_is_dropped_silently(self):
        """Def with no URL: drop def line, leave reference text unchanged."""
        md = "Note[^n].\n\n[^n]: No URL here.\n"
        result = normalize_citation_artifacts(md)
        assert "[^n]: No URL here." not in result


class TestNoopOnCleanMarkdown:
    """Idempotency -- clean sections must not be modified."""

    def test_clean_inline_link_unchanged(self):
        md = "According to [Report](https://example.com), X grew."
        assert normalize_citation_artifacts(md) == md

    def test_plain_text_without_urls_unchanged(self):
        # normalize_citation_artifacts may strip the trailing newline;
        # normalize_markdown() (always called next) restores it.
        # Assert that no content modification occurs, ignoring trailing newline.
        md = "This section has no citations or URLs at all.\n"
        result = normalize_citation_artifacts(md)
        assert result.strip() == md.strip()

    def test_code_block_url_not_spuriously_broken(self):
        """URLs inside fenced code blocks must survive."""
        md = "```\ncurl https://api.example.com\n```\n"
        result = normalize_citation_artifacts(md)
        assert "https://api.example.com" in result


class TestIntegrationWithRepairSectionStructure:
    """
    normalize_citation_artifacts() is invoked first inside
    repair_section_structure(). Verify converted links are visible to
    extract_markdown_links() after the full repair pipeline.
    """

    def test_bracket_url_survives_full_repair_and_is_extractable(self):
        md = "Data shows X\u3010https://example.com/report\u3011 in 2026."
        repaired = repair_section_structure(md, expected_title="My Section")
        links = extract_markdown_links(f"## My Section\n\n{repaired}")
        urls = [lnk.url for lnk in links]
        assert "https://example.com/report" in urls

    def test_footnote_survives_full_repair_and_is_extractable(self):
        md = (
            "The study[^1] found this.\n"
            "\n"
            "[^1]: https://study.example.com\n"
        )
        repaired = repair_section_structure(md, expected_title="Results")
        links = extract_markdown_links(f"## Results\n\n{repaired}")
        urls = [lnk.url for lnk in links]
        assert "https://study.example.com" in urls

    def test_bracket_md_link_survives_full_repair_and_is_extractable(self):
        md = "See \u3010[Study Report](https://study.example.com)\u3011 for details."
        repaired = repair_section_structure(md, expected_title="Analysis")
        links = extract_markdown_links(f"## Analysis\n\n{repaired}")
        urls = [lnk.url for lnk in links]
        assert "https://study.example.com" in urls
