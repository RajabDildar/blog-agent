from services.section_validation import (
    validate_section_markdown,
)


def test_valid_section():
    markdown = """## The State of the Agentic Stack

Content here.
"""

    errors = validate_section_markdown(
        markdown,
        "The State of the Agentic Stack",
    )

    assert errors == []


def test_rejects_h1():
    markdown = """# The State of the Agentic Stack

Content here.
"""

    errors = validate_section_markdown(
        markdown,
        "The State of the Agentic Stack",
    )

    assert "Section heading must be H2." in errors


def test_rejects_multiple_headings():
    markdown = """## The State of the Agentic Stack

Content.

### Another heading
"""

    errors = validate_section_markdown(
        markdown,
        "The State of the Agentic Stack",
    )

    assert any("exactly one heading" in error for error in errors)


def test_rejects_wrong_title():
    markdown = """## Wrong Heading

Content.
"""

    errors = validate_section_markdown(
        markdown,
        "The State of the Agentic Stack",
    )

    assert any("Expected heading" in error for error in errors)
