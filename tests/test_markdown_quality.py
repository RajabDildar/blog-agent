from services.markdown_quality import (
    run_markdown_quality_gate,
)


def test_section_gate_removes_duplicated_h2():
    markdown = """## HTTP Headers

Content.

### Header Example

More content.
"""

    result = run_markdown_quality_gate(
        markdown,
        profile="section",
        expected_title="HTTP Headers",
    )

    assert result.errors == []

    assert "## HTTP Headers" not in result.markdown

    assert "### Header Example" in result.markdown

    assert result.deterministic_repair_applied


def test_section_gate_demotes_unexpected_h2():
    markdown = """Intro.

## Nested Idea

Details.
"""

    result = run_markdown_quality_gate(
        markdown,
        profile="section",
        expected_title="HTTP",
    )

    assert result.errors == []

    assert "### Nested Idea" in result.markdown


def test_article_gate_preserves_h3_and_table():
    markdown = """# HTTP

## Request

### Headers

| Name | Meaning |
| --- | --- |
| Host | Target host |
"""

    result = run_markdown_quality_gate(
        markdown,
        profile="article",
        expected_title="HTTP",
        expected_sections=[
            "Request",
        ],
    )

    assert result.errors == []

    assert "### Headers" in result.markdown

    assert "| Name" in result.markdown
